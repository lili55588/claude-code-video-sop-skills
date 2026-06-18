#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run a validated Phase8 prompt set through the Pippit/XiaoYunque CLI.

The script keeps the video-sop contract intact: Phase8 still produces the
director prompt set, and this runner only submits each Clip, polls optional
results, downloads outputs, and writes a local manifest.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm", ".mkv", ".m4v"}
AUDIO_EXTS = {".mp3", ".wav"}
REF_EXTS = IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS
GENERIC_LABEL_TERMS = ("参考", "素材", "图片", "片段", "即梦", "版", "图")

CLIP_SECTION_RE = re.compile(
    r"^##\s*Clip\s*0*(?P<num>\d+)(?P<title>[^\n]*)\n(?P<body>.*?)(?=^##\s*Clip\s*0*\d+|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
FENCED_RE = re.compile(r"```(?:text|markdown|md)?\s*\n(?P<body>.*?)\n```", re.IGNORECASE | re.DOTALL)
OFFICIAL_HEADER_RE = re.compile(r"生成一个由以下\s*\d+\s*个分镜组成的视频[：:]", re.IGNORECASE)
SHOT_TIME_RE = re.compile(r"分镜\s*\d+\s*[：:]\s*(\d+)\s*-\s*(\d+)\s*s", re.IGNORECASE)
RATIO_RE = re.compile(r"(?:画幅比例|画幅|比例)\s*[：:]\s*([0-9]+\s*:\s*[0-9]+)")
DURATION_RE = re.compile(r"(?:时长|duration)[^0-9]{0,8}(\d+)\s*s?", re.IGNORECASE)
STORYBOARD_MARKER_RE = re.compile(
    r"分镜宫格|故事板|全案分镜图|storyboard[-\s]+grid|STORYBOARD\s+GRID",
    re.IGNORECASE,
)


@dataclass
class Reference:
    kind: str
    num: int
    label: str
    raw: str
    path: Path | None = None

    def cli_flag(self) -> str:
        return {"image": "--image", "video": "--video", "audio": "--audio"}[self.kind]


@dataclass
class ClipTask:
    num: int
    title: str
    duration: int | None
    prompt: str
    references: list[Reference] = field(default_factory=list)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def normalize_ref_kind(kind: str) -> str:
    if kind in ("图片", "image", "img"):
        return "image"
    if kind in ("视频", "video"):
        return "video"
    if kind in ("音频", "audio"):
        return "audio"
    raise ValueError(f"Unsupported reference kind: {kind}")


def strip_inline_code(value: str) -> str:
    value = value.strip()
    if value.startswith("`") and value.endswith("`"):
        return value[1:-1].strip()
    return value


def clean_label(value: str) -> str:
    value = strip_inline_code(value)
    value = re.sub(r"^\d+\.\s*", "", value).strip()
    value = value.replace("->", " ").replace("→", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" ：:=，,；;")


def match_key(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.lower())


def significant_label_terms(label: str) -> list[str]:
    terms: list[str] = []
    for code in re.findall(r"[A-Za-z]+\d+[A-Za-z]?", label):
        terms.append(match_key(code))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]+", label))
    for generic in GENERIC_LABEL_TERMS:
        chinese = chinese.replace(generic, "")
    if chinese:
        terms.append(match_key(chinese))
    return [term for term in terms if term]


def extract_ratio(text: str, fallback: str) -> str:
    match = RATIO_RE.search(text)
    if not match:
        return fallback
    return re.sub(r"\s+", "", match.group(1))


def extract_prompt(section_body: str) -> str:
    fence = FENCED_RE.search(section_body)
    if fence:
        return fence.group("body").strip()

    header = OFFICIAL_HEADER_RE.search(section_body)
    if not header:
        # Legacy "## ClipN Prompt" sections often contain only the prompt body.
        lines = [
            line.rstrip()
            for line in section_body.strip().splitlines()
            if line.strip() and not line.strip().startswith("**")
        ]
        return "\n".join(lines).strip()

    start = section_body.rfind("\n", 0, header.start())
    if start == -1:
        start = 0
    else:
        start += 1
    return section_body[start:].strip()


def extract_duration(title: str, body: str, prompt: str) -> int | None:
    for source in (title, body):
        match = DURATION_RE.search(source)
        if match:
            return int(match.group(1))
    spans = [(int(start), int(end)) for start, end in SHOT_TIME_RE.findall(prompt)]
    if spans:
        return max(end for _, end in spans) - min(start for start, _ in spans)
    return None


def upload_text_for_section(body: str) -> str:
    fence = FENCED_RE.search(body)
    if fence:
        return body[: fence.start()]
    header = OFFICIAL_HEADER_RE.search(body)
    if header:
        return body[: header.start()]
    return body


def parse_ref_line(line: str) -> list[Reference]:
    refs: list[Reference] = []

    # @图片1 = S01 老屋书房　@图片2 = R02 陈默成年
    for match in re.finditer(
        r"@(?P<kind>图片|视频|音频|image|video|audio|img)(?P<num>\d+)\s*=\s*"
        r"(?P<label>.*?)(?=\s*@(?:图片|视频|音频|image|video|audio|img)\d+\s*=|[；;\n]|$)",
        line,
        re.IGNORECASE,
    ):
        refs.append(
            Reference(
                kind=normalize_ref_kind(match.group("kind")),
                num=int(match.group("num")),
                label=clean_label(match.group("label")),
                raw=line.strip(),
            )
        )

    # `R01.png` -> `@图片1`
    for match in re.finditer(
        r"`(?P<label>[^`]+)`\s*(?:->|→)\s*`?@(?P<kind>图片|视频|音频|image|video|audio|img)(?P<num>\d+)`?",
        line,
        re.IGNORECASE,
    ):
        refs.append(
            Reference(
                kind=normalize_ref_kind(match.group("kind")),
                num=int(match.group("num")),
                label=clean_label(match.group("label")),
                raw=line.strip(),
            )
        )

    # `@图片1` R01.png
    for match in re.finditer(
        r"`?@(?P<kind>图片|视频|音频|image|video|audio|img)(?P<num>\d+)`?\s*"
        r"(?P<label>[^；;\n]*?(?:\.(?:jpg|jpeg|png|gif|bmp|webp|svg|mp4|avi|mov|wmv|flv|webm|mkv|m4v|mp3|wav)))",
        line,
        re.IGNORECASE,
    ):
        refs.append(
            Reference(
                kind=normalize_ref_kind(match.group("kind")),
                num=int(match.group("num")),
                label=clean_label(match.group("label")),
                raw=line.strip(),
            )
        )

    # @图片1=asset name; useful for dry-run and unresolved warnings.
    for match in re.finditer(
        r"@(?P<kind>图片|视频|音频|image|video|audio|img)(?P<num>\d+)\s*=\s*(?P<label>[^@；;\n]+)",
        line,
        re.IGNORECASE,
    ):
        label = clean_label(match.group("label"))
        key = (normalize_ref_kind(match.group("kind")), int(match.group("num")))
        if not any((ref.kind, ref.num) == key for ref in refs):
            refs.append(
                Reference(
                    kind=key[0],
                    num=key[1],
                    label=label,
                    raw=line.strip(),
                )
            )

    return refs


def dedupe_refs(refs: list[Reference]) -> list[Reference]:
    by_key: dict[tuple[str, int], Reference] = {}
    for ref in refs:
        key = (ref.kind, ref.num)
        existing = by_key.get(key)
        if existing is None or ("." in ref.label and "." not in existing.label):
            by_key[key] = ref
    return sorted(by_key.values(), key=lambda item: (item.kind, item.num))


def parse_references(upload_text: str) -> list[Reference]:
    refs: list[Reference] = []
    for raw_line in upload_text.splitlines():
        line = raw_line.strip()
        if "@图片" not in line and "@视频" not in line and "@音频" not in line:
            continue
        refs.extend(parse_ref_line(line))
    return dedupe_refs(refs)


def parse_prompt_file(prompt_file: Path, default_ratio: str) -> tuple[str, list[ClipTask]]:
    text = read_text(prompt_file)
    ratio = extract_ratio(text, default_ratio)
    grouped: dict[int, list[tuple[str, str]]] = {}

    for match in CLIP_SECTION_RE.finditer(text):
        clip_num = int(match.group("num"))
        title = match.group("title").strip()
        body = match.group("body")
        grouped.setdefault(clip_num, []).append((title, body))

    tasks: list[ClipTask] = []
    for clip_num in sorted(grouped):
        sections = grouped[clip_num]
        title = sections[0][0]
        upload_parts: list[str] = []
        prompt_parts: list[str] = []

        for section_title, body in sections:
            lowered = section_title.lower()
            if "上传顺序" in section_title:
                upload_parts.append(body)
                continue
            if "prompt" in lowered:
                prompt_parts.append(extract_prompt(body))
                continue

            upload_parts.append(upload_text_for_section(body))
            prompt_parts.append(extract_prompt(body))

        prompt = "\n\n".join(part for part in prompt_parts if part).strip()
        refs = parse_references("\n".join(upload_parts))
        duration = extract_duration(title, "\n".join(body for _, body in sections), prompt)
        tasks.append(ClipTask(clip_num, title, duration, prompt, refs))

    if not tasks:
        raise ValueError("No Clip sections found. Expected headings like '## Clip 01'.")

    return ratio, tasks


def build_file_index(project_dir: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    for path in project_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in REF_EXTS:
            continue
        index.setdefault("__all__", []).append(path)
        for key in {path.name.lower(), path.stem.lower()}:
            index.setdefault(key, []).append(path)
    return index


def candidate_tokens(label: str) -> list[str]:
    label = clean_label(label)
    if label.startswith(("http://", "https://")):
        return []
    tokens = [label]
    for match in re.findall(r"[\w\-\u4e00-\u9fff（）()【】\[\]·]+(?:\.[A-Za-z0-9]+)?", label):
        tokens.append(match)
    return [token.strip().strip("`") for token in tokens if token.strip()]


def resolve_reference(ref: Reference, prompt_dir: Path, project_dir: Path, index: dict[str, list[Path]]) -> None:
    for token in candidate_tokens(ref.label):
        path = Path(token)
        if path.is_absolute() and path.exists():
            ref.path = path
            return

        for base in (prompt_dir, project_dir):
            candidate = base / token
            if candidate.exists():
                ref.path = candidate
                return

        if Path(token).suffix.lower() in REF_EXTS:
            hits = index.get(Path(token).name.lower(), [])
            if len(hits) == 1:
                ref.path = hits[0]
                return
            if len(hits) > 1:
                ref.path = sorted(hits, key=lambda item: len(str(item)))[0]
                return

        stem = Path(token).stem.lower()
        hits = index.get(stem, [])
        if len(hits) == 1:
            ref.path = hits[0]
            return

    all_paths = index.get("__all__", [])
    label_key = match_key(ref.label)
    if label_key:
        hits = [path for path in all_paths if label_key in match_key(path.stem)]
        hits = prefer_current_files(hits)
        if hits:
            ref.path = hits[0]
            return

    terms = significant_label_terms(ref.label)
    if terms:
        hits = [
            path
            for path in all_paths
            if all(term in match_key(path.stem) for term in terms)
        ]
        hits = prefer_current_files(hits)
        if hits:
            ref.path = hits[0]
            return


def prefer_current_files(paths: list[Path]) -> list[Path]:
    if not paths:
        return []
    preferred = [path for path in paths if "FAIL_BLOCKED" not in str(path)]
    return sorted(preferred or paths, key=lambda item: (len(str(item)), str(item)))


def resolve_all_references(tasks: list[ClipTask], prompt_file: Path, project_dir: Path) -> None:
    index = build_file_index(project_dir)
    for task in tasks:
        for ref in task.references:
            resolve_reference(ref, prompt_file.parent, project_dir, index)


def validate_limits(tasks: list[ClipTask], max_duration: int) -> list[str]:
    errors: list[str] = []
    for task in tasks:
        if not task.prompt:
            errors.append(f"Clip {task.num}: prompt is empty.")
        if task.duration is None:
            errors.append(f"Clip {task.num}: duration could not be inferred.")
        elif not 4 <= task.duration <= max_duration:
            errors.append(f"Clip {task.num}: duration {task.duration}s is outside 4-{max_duration}s.")

        counts = {
            "image": sum(1 for ref in task.references if ref.kind == "image"),
            "video": sum(1 for ref in task.references if ref.kind == "video"),
            "audio": sum(1 for ref in task.references if ref.kind == "audio"),
        }
        if counts["image"] > 9:
            errors.append(f"Clip {task.num}: {counts['image']} images exceeds Pippit limit 9.")
        if counts["video"] > 3:
            errors.append(f"Clip {task.num}: {counts['video']} videos exceeds Pippit limit 3.")
        if counts["audio"] > 3:
            errors.append(f"Clip {task.num}: {counts['audio']} audios exceeds Pippit limit 3.")

        missing = [f"@{kind_label(ref.kind)}{ref.num}={ref.label}" for ref in task.references if ref.path is None]
        if missing:
            errors.append(f"Clip {task.num}: unresolved local reference(s): {', '.join(missing)}.")
    return errors


def kind_label(kind: str) -> str:
    return {"image": "图片", "video": "视频", "audio": "音频"}[kind]


def manifest_task(task: ClipTask) -> dict[str, Any]:
    return {
        "clip": task.num,
        "title": task.title,
        "duration": task.duration,
        "prompt_chars": len(task.prompt),
        "references": [
            {
                "kind": ref.kind,
                "slot": ref.num,
                "label": ref.label,
                "path": str(ref.path) if ref.path else None,
            }
            for ref in sorted(task.references, key=lambda item: (item.kind, item.num))
        ],
    }


def run_validator(prompt_file: Path) -> tuple[int, str]:
    validator = Path(__file__).with_name("validate_phase8_prompt.py")
    if not validator.exists():
        return 0, "Validator not found; skipped."
    command = [sys.executable, str(validator), str(prompt_file)]
    text = read_text(prompt_file)
    if STORYBOARD_MARKER_RE.search(text):
        command.append("--require-storyboard-artifact-guard")
    return stable_run(command)


def read_access_key(args: argparse.Namespace) -> str | None:
    if args.access_key_file:
        return Path(args.access_key_file).read_text(encoding="utf-8-sig").strip()
    return os.environ.get("XYQ_ACCESS_KEY")


def build_generate_command(args: argparse.Namespace, ratio: str, task: ClipTask) -> list[str]:
    command = command_prefix(args.pippit_cmd) + [
        "generate-video",
        "--prompt",
        task.prompt,
        "--duration",
        str(task.duration),
        "--ratio",
        ratio,
        "--model",
        args.model,
        "--resolution",
        args.resolution,
    ]
    for ref in sorted(task.references, key=lambda item: (item.kind, item.num)):
        if ref.path is not None:
            command.extend([ref.cli_flag(), str(ref.path)])
    return command


def resolve_command(command: str) -> str:
    if Path(command).exists():
        return command
    resolved = shutil.which(command)
    if resolved:
        return resolved
    return command


def command_prefix(command: str) -> list[str]:
    resolved = resolve_command(command)
    if resolved.lower().endswith((".cmd", ".bat")):
        script = Path(resolved).parent / "node_modules" / "@pippit-dev" / "cli" / "scripts" / "run.js"
        if script.exists():
            return ["node", str(script)]
        return ["cmd.exe", "/d", "/s", "/c", resolved]
    return [resolved]


def decode_process_output(data: bytes) -> str:
    if not data:
        return ""
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def stable_run(command: list[str], env: dict[str, str] | None = None) -> tuple[int, str]:
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    run_env.setdefault("PYTHONUTF8", "1")
    run_env.setdefault("PYTHONIOENCODING", "utf-8")
    run_env.setdefault("LC_ALL", "C.UTF-8")
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=run_env,
        check=False,
    )
    return result.returncode, decode_process_output(result.stdout)


def parse_cli_ids(output: str) -> dict[str, str]:
    ids: dict[str, str] = {}
    try:
        parsed = json.loads(output)
        if isinstance(parsed, dict):
            for key in ("thread_id", "run_id", "web_thread_link"):
                if parsed.get(key):
                    ids[key] = str(parsed[key])
    except json.JSONDecodeError:
        pass

    for key in ("thread_id", "run_id", "web_thread_link"):
        if key in ids:
            continue
        match = re.search(rf"{key}[\"']?\s*[:=]\s*[\"']?([^\"'\s,}}]+)", output)
        if match:
            ids[key] = match.group(1)
    return ids


def run_generate(args: argparse.Namespace, ratio: str, task: ClipTask, env: dict[str, str]) -> dict[str, Any]:
    command = build_generate_command(args, ratio, task)
    returncode, stdout = stable_run(command, env=env)
    return {
        "clip": task.num,
        "returncode": returncode,
        "stdout": stdout,
        "ids": parse_cli_ids(stdout),
    }


def run_query(args: argparse.Namespace, run_info: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    ids = run_info.get("ids", {})
    if not ids.get("thread_id") or not ids.get("run_id"):
        return {"completed": False, "error_message": "Missing thread_id or run_id; cannot query."}

    deadline = time.time() + args.poll_timeout
    after: dict[str, Any] = {}
    while time.time() <= deadline:
        command = command_prefix(args.pippit_cmd) + [
            "query-result",
            "--thread-id",
            ids["thread_id"],
            "--run-id",
            ids["run_id"],
            "--download-dir",
            str(args.download_dir),
        ]
        returncode, stdout = stable_run(command, env=env)
        after = {"returncode": returncode, "stdout": stdout}
        try:
            parsed = json.loads(stdout)
            if isinstance(parsed, dict):
                after["json"] = parsed
                if parsed.get("completed") is True:
                    return after
        except json.JSONDecodeError:
            pass
        time.sleep(args.poll_interval)
    after["error_message"] = "Poll timeout reached."
    return after


def write_manifest(output_dir: Path, manifest: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    manifest_path = output_dir / f"pippit_phase8_{stamp}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def select_tasks(tasks: list[ClipTask], clip_nums: list[int] | None) -> list[ClipTask]:
    if not clip_nums:
        return tasks
    wanted = set(clip_nums)
    selected = [task for task in tasks if task.num in wanted]
    missing = sorted(wanted - {task.num for task in selected})
    if missing:
        raise ValueError(f"Requested clip(s) not found: {missing}")
    return selected


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt_file", help="Path to {project}_视频生成Prompt集.md")
    parser.add_argument("--project-dir", help="Project directory; defaults to prompt file parent.")
    parser.add_argument("--output-dir", help="Manifest directory; defaults to <project>/pippit_runs.")
    parser.add_argument("--download-dir", help="Download directory; defaults to <project>/pippit_outputs.")
    parser.add_argument("--clip", type=int, action="append", help="Submit only this Clip number; repeatable.")
    parser.add_argument("--submit", action="store_true", help="Actually call pippit-tool-cli. Default is dry-run.")
    parser.add_argument("--poll", action="store_true", help="Poll query-result after each submitted Clip.")
    parser.add_argument("--poll-interval", type=int, default=10, help="Seconds between query-result calls.")
    parser.add_argument("--poll-timeout", type=int, default=60 * 60 * 6, help="Seconds before polling gives up.")
    parser.add_argument("--ratio", default="16:9", help="Fallback ratio if the prompt file does not declare one.")
    parser.add_argument("--model", default="seedance2.0_direct")
    parser.add_argument("--resolution", default="720p")
    parser.add_argument("--max-duration", type=int, default=10)
    parser.add_argument("--pippit-cmd", default="pippit-tool-cli")
    parser.add_argument("--skip-validation", action="store_true")
    parser.add_argument("--access-key-file", help="Read XYQ access key from a local file.")
    args = parser.parse_args(argv)

    prompt_file = Path(args.prompt_file).resolve()
    if not prompt_file.exists():
        print(f"[FAIL] Prompt file does not exist: {prompt_file}")
        return 1

    project_dir = Path(args.project_dir).resolve() if args.project_dir else prompt_file.parent
    args.output_dir = Path(args.output_dir).resolve() if args.output_dir else project_dir / "pippit_runs"
    args.download_dir = Path(args.download_dir).resolve() if args.download_dir else project_dir / "pippit_outputs"

    try:
        ratio, tasks = parse_prompt_file(prompt_file, args.ratio)
        tasks = select_tasks(tasks, args.clip)
        resolve_all_references(tasks, prompt_file, project_dir)
    except Exception as exc:  # noqa: BLE001 - user-facing CLI should print exact parser error
        print(f"[FAIL] {exc}")
        return 1

    manifest: dict[str, Any] = {
        "prompt_file": str(prompt_file),
        "project_dir": str(project_dir),
        "ratio": ratio,
        "model": args.model,
        "resolution": args.resolution,
        "submit": args.submit,
        "poll": args.poll,
        "tasks": [manifest_task(task) for task in tasks],
    }

    if not args.skip_validation:
        code, output = run_validator(prompt_file)
        manifest["validation"] = {"returncode": code, "output": output}
        if code != 0:
            manifest_path = write_manifest(args.output_dir, manifest)
            print(output.rstrip())
            print(f"[FAIL] Phase8 validator failed. Manifest: {manifest_path}")
            return 1

    errors = validate_limits(tasks, args.max_duration)
    if errors:
        manifest["errors"] = errors
        manifest_path = write_manifest(args.output_dir, manifest)
        for error in errors:
            print(f"[FAIL] {error}")
        print(f"Manifest: {manifest_path}")
        return 1

    if not args.submit:
        manifest_path = write_manifest(args.output_dir, manifest)
        print(f"[DRY-RUN] Parsed {len(tasks)} Clip task(s). No video submitted.")
        print(f"Manifest: {manifest_path}")
        return 0

    access_key = read_access_key(args)
    if not access_key:
        manifest["errors"] = ["XYQ_ACCESS_KEY is missing. Set env var or pass --access-key-file."]
        manifest_path = write_manifest(args.output_dir, manifest)
        print("[FAIL] XYQ_ACCESS_KEY is missing. Set env var or pass --access-key-file.")
        print(f"Manifest: {manifest_path}")
        return 1

    env = os.environ.copy()
    env["XYQ_ACCESS_KEY"] = access_key

    runs: list[dict[str, Any]] = []
    for task in tasks:
        run_info = run_generate(args, ratio, task, env)
        runs.append(run_info)
        print(f"[SUBMIT] Clip {task.num}: returncode={run_info['returncode']}")
        if run_info["returncode"] != 0:
            break
        if args.poll:
            run_info["query"] = run_query(args, run_info, env)
            completed = run_info["query"].get("json", {}).get("completed")
            print(f"[QUERY] Clip {task.num}: completed={completed}")

    manifest["runs"] = runs
    manifest_path = write_manifest(args.output_dir, manifest)
    failed = any(run["returncode"] != 0 for run in runs)
    print(f"Manifest: {manifest_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
