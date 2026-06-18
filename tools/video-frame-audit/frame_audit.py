#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Prepare deterministic evidence for Gate 10 generated-video visual audit.

The tool does not judge whether a generated video is visually correct. It only
extracts frames, measures media facts, maps frames to Phase8 shots, detects
scene/diff spikes, and writes a worksheet for human or model visual review.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from typing import Any


CLIP_SECTION_RE = re.compile(
    r"^##\s*Clip\s*0*(?P<num>\d+)(?P<title>[^\n]*)\n(?P<body>.*?)(?=^##\s*Clip\s*0*\d+|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
FENCED_RE = re.compile(r"```(?:text|markdown|md)?\s*\n(?P<body>.*?)\n```", re.IGNORECASE | re.DOTALL)
OFFICIAL_HEADER_RE = re.compile(r"生成一个由以下\s*\d+\s*个分镜组成的视频[：:]", re.IGNORECASE)
SHOT_RE = re.compile(
    r"分镜\s*(?P<num>\d+)\s*[：:]\s*(?P<start>\d+(?:\.\d+)?)\s*-\s*"
    r"(?P<end>\d+(?:\.\d+)?)\s*s\s*[，,]?\s*(?P<body>.*?)(?=分镜\s*\d+\s*[：:]|\Z)",
    re.DOTALL,
)
RATIO_RE = re.compile(r"(?:画幅比例|画幅|比例)\s*[：:]\s*([0-9]+\s*:\s*[0-9]+)")
DURATION_RE = re.compile(r"(?:时长|duration)[^0-9]{0,8}(\d+)\s*s?", re.IGNORECASE)
REF_RE = re.compile(r"@(?:图片|视频|音频|image|video|audio|img)\d+", re.IGNORECASE)
ORIENTATION_TERMS = (
    "面向",
    "望向",
    "看向",
    "视线",
    "朝向",
    "背对",
    "侧对",
    "侧身",
    "转向",
    "抬头",
    "低头",
    "俯身",
    "仰头",
)
STABLE_ORIENTATION_ANCHOR_TERMS = (
    "窗外",
    "窗户",
    "窗口",
    "窗光",
    "窗",
    "门口",
    "门",
    "书桌",
    "课桌",
    "桌",
    "床",
    "楼梯",
    "货架",
    "书架",
    "柜",
    "墙",
    "讲台",
    "黑板",
    "舞台",
    "车辆",
    "汽车",
    "车",
    "单车",
    "自行车",
    "产品",
    "行李箱",
    "站台",
)
ORIENTATION_ANCHOR_EXCLUDE_TERMS = (
    "镜头",
    "机位",
    "运镜",
    "推镜",
    "拉镜",
    "画面",
    "景别",
    "特写",
    "近景",
    "中景",
    "全景",
    "远景",
    "拍摄",
    "构图",
    "铅笔盒",
    "自动铅笔",
    "铅笔",
    "笔",
    "杯",
    "手机",
    "钥匙",
    "纸",
    "伞",
)
NAMED_TARGET_RE = re.compile(
    r"(?:面向|望向|看向|朝向|转向|背对|侧对|视线(?:落在|移向|投向|看向|望向)?)"
    r"[^，。；;.!?\n@]{0,12}"
    r"(?P<name>[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9·]{1,11})"
    r"@(?:图片|视频|image|video|img)\d+"
)


@dataclass
class Shot:
    num: int
    start: float
    end: float
    text: str
    refs: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class ClipTask:
    num: int
    title: str
    duration: float | None
    prompt: str
    shots: list[Shot]


def decode_process_output(data: bytes) -> str:
    if not data:
        return ""
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def stable_run(command: list[str]) -> tuple[int, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("LC_ALL", "C.UTF-8")
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        check=False,
    )
    return result.returncode, decode_process_output(result.stdout)


def require_tool(name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        raise RuntimeError(f"{name} was not found on PATH.")
    return resolved


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def parse_fps(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    try:
        return float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return None


def parse_ratio_value(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    if ":" in value:
        left, right = value.split(":", 1)
        try:
            denominator = float(right)
            return float(left) / denominator if denominator else None
        except ValueError:
            return None
    try:
        return float(value)
    except ValueError:
        return None


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
        lines = [
            line.rstrip()
            for line in section_body.strip().splitlines()
            if line.strip() and not line.strip().startswith("**")
        ]
        return "\n".join(lines).strip()
    start = section_body.rfind("\n", 0, header.start())
    return section_body[start + 1 if start != -1 else 0 :].strip()


def upload_text_for_section(body: str) -> str:
    fence = FENCED_RE.search(body)
    if fence:
        return body[: fence.start()]
    header = OFFICIAL_HEADER_RE.search(body)
    if header:
        return body[: header.start()]
    return body


def extract_duration(title: str, body: str, prompt: str) -> float | None:
    for source in (title, body):
        match = DURATION_RE.search(source)
        if match:
            return float(match.group(1))
    spans = [(float(match.group("start")), float(match.group("end"))) for match in SHOT_RE.finditer(prompt)]
    if spans:
        return max(end for _, end in spans) - min(start for start, _ in spans)
    return None


def parse_shots(prompt: str) -> list[Shot]:
    shots: list[Shot] = []
    for match in SHOT_RE.finditer(prompt):
        text = re.sub(r"\s+", " ", match.group("body")).strip()
        shots.append(
            Shot(
                num=int(match.group("num")),
                start=float(match.group("start")),
                end=float(match.group("end")),
                text=text,
                refs=REF_RE.findall(text),
            )
        )
    return shots


def unique_in_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def extract_orientation_anchors(text: str) -> dict[str, Any]:
    anchors = unique_in_order([term for term in STABLE_ORIENTATION_ANCHOR_TERMS if term in text])
    anchors.extend(match.group("name") for match in NAMED_TARGET_RE.finditer(text))
    excluded = unique_in_order([term for term in ORIENTATION_ANCHOR_EXCLUDE_TERMS if term in text])
    normalized: list[str] = []
    for anchor in anchors:
        if anchor in {"窗外", "窗户", "窗口", "窗光"}:
            normalized.append("窗")
        elif anchor in {"书桌", "课桌"}:
            normalized.append("桌")
        elif anchor == "门口":
            normalized.append("门")
        elif anchor in {"车辆", "汽车"}:
            normalized.append("车")
        else:
            normalized.append(anchor)

    clauses: list[str] = []
    for clause in re.split(r"[。；;.!?\n]", text):
        stripped = clause.strip()
        if stripped and any(term in stripped for term in ORIENTATION_TERMS):
            clauses.append(stripped)

    return {
        "anchors": unique_in_order(normalized),
        "excluded_non_orientation_anchors": excluded,
        "orientation_clauses": clauses,
        "review_instruction": "Use stable scene landmarks, named targets, or products as geometry anchors. Camera-language terms and hand-held movable props are not orientation anchors. Light/shadow alone is not proof of facing direction.",
    }


def parse_prompt_file(prompt_file: Path, default_ratio: str) -> tuple[str, list[ClipTask]]:
    text = read_text(prompt_file)
    ratio = extract_ratio(text, default_ratio)
    grouped: dict[int, list[tuple[str, str]]] = {}
    for match in CLIP_SECTION_RE.finditer(text):
        clip_num = int(match.group("num"))
        grouped.setdefault(clip_num, []).append((match.group("title").strip(), match.group("body")))
    if not grouped:
        raise ValueError("No Clip sections found. Expected headings like '## Clip 01'.")

    tasks: list[ClipTask] = []
    for clip_num in sorted(grouped):
        sections = grouped[clip_num]
        title = sections[0][0]
        prompt_parts: list[str] = []
        for section_title, body in sections:
            lowered = section_title.lower()
            if "上传顺序" in section_title:
                continue
            if "prompt" in lowered:
                prompt_parts.append(extract_prompt(body))
            else:
                prompt_parts.append(extract_prompt(body))
        prompt = "\n\n".join(part for part in prompt_parts if part).strip()
        shots = parse_shots(prompt)
        duration = extract_duration(title, "\n".join(body for _, body in sections), prompt)
        tasks.append(ClipTask(clip_num, title, duration, prompt, shots))
    return ratio, tasks


def select_clip(tasks: list[ClipTask], clip: int) -> ClipTask:
    for task in tasks:
        if task.num == clip:
            return task
    raise ValueError(f"Requested Clip {clip} was not found in the prompt set.")


def probe_video(video: Path, ffprobe: str) -> dict[str, Any]:
    command = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(video),
    ]
    code, output = stable_run(command)
    if code != 0:
        raise RuntimeError(f"ffprobe failed:\n{output}")
    parsed = json.loads(output)
    video_stream = next((item for item in parsed.get("streams", []) if item.get("codec_type") == "video"), None)
    if not video_stream:
        raise RuntimeError("No video stream found.")
    fmt = parsed.get("format", {})
    fps = parse_fps(video_stream.get("avg_frame_rate")) or parse_fps(video_stream.get("r_frame_rate"))
    duration = float(fmt.get("duration") or video_stream.get("duration") or 0)
    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    display_ratio = parse_ratio_value(video_stream.get("display_aspect_ratio"))
    if display_ratio is None:
        sar = parse_ratio_value(video_stream.get("sample_aspect_ratio")) or 1.0
        display_ratio = (width * sar / height) if width and height else None
    return {
        "format": fmt,
        "video_stream": video_stream,
        "duration": duration,
        "fps": fps,
        "width": width,
        "height": height,
        "codec": video_stream.get("codec_name"),
        "nb_frames": video_stream.get("nb_frames"),
        "sample_aspect_ratio": video_stream.get("sample_aspect_ratio"),
        "display_aspect_ratio": video_stream.get("display_aspect_ratio"),
        "display_ratio_float": display_ratio,
    }


def default_output_dir(video: Path, project_dir: Path, clip: int) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return project_dir / "video_audit" / f"Clip{clip}_{stamp}"


def reset_managed_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def count_images(path: Path) -> int:
    return sum(1 for item in path.glob("*.jpg") if item.is_file())


def extract_full_frames(ffmpeg: str, video: Path, frames_dir: Path, jpeg_quality: int) -> tuple[int, str]:
    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-i",
        str(video),
        "-q:v",
        str(jpeg_quality),
        str(frames_dir / "frame_%06d.jpg"),
    ]
    return stable_run(command)


def make_contact_sheets(ffmpeg: str, video: Path, sheets_dir: Path) -> tuple[int, str, int]:
    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-i",
        str(video),
        "-vf",
        "scale=240:-1,tile=5x5:margin=4:padding=2",
        "-q:v",
        "5",
        str(sheets_dir / "sheet_%03d.jpg"),
    ]
    code, output = stable_run(command)
    return code, output, count_images(sheets_dir)


def frame_index_for_time(time_s: float, fps: float | None, frame_count: int) -> int:
    if not fps or fps <= 0 or frame_count <= 0:
        return 1
    return max(1, min(frame_count, int(math.floor(max(0.0, time_s) * fps)) + 1))


def frame_path(frames_dir: Path, index: int) -> Path:
    return frames_dir / f"frame_{index:06d}.jpg"


def copy_frame(frames_dir: Path, dest: Path, time_s: float, fps: float | None, frame_count: int) -> dict[str, Any]:
    index = frame_index_for_time(time_s, fps, frame_count)
    source = frame_path(frames_dir, index)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source.exists():
        shutil.copy2(source, dest)
    return {"time": round(time_s, 3), "frame_index": index, "path": str(dest), "source": str(source)}


def hstack_pair(ffmpeg: str, left: Path, right: Path, out: Path) -> dict[str, Any]:
    out.parent.mkdir(parents=True, exist_ok=True)
    if not left.exists() or not right.exists():
        return {"path": str(out), "created": False, "error": "missing source frame"}
    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-i",
        str(left),
        "-i",
        str(right),
        "-filter_complex",
        "hstack=inputs=2",
        "-frames:v",
        "1",
        "-update",
        "1",
        "-q:v",
        "3",
        str(out),
    ]
    code, output = stable_run(command)
    return {"path": str(out), "created": code == 0, "returncode": code, "output_tail": output[-1000:]}


def run_scene_scores(ffmpeg: str, video: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    command = [
        ffmpeg,
        "-hide_banner",
        "-i",
        str(video),
        "-vf",
        "scdet=threshold=0,metadata=print",
        "-an",
        "-f",
        "null",
        "-",
    ]
    code, output = stable_run(command)
    records: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in output.splitlines():
        frame_match = re.search(r"frame:\s*(\d+)\s+pts:\s*[-0-9]+\s+pts_time:([0-9.]+)", line)
        if frame_match:
            if current:
                records.append(current)
            current = {"frame": int(frame_match.group(1)), "time": float(frame_match.group(2))}
            continue
        if current is None:
            continue
        mafd = re.search(r"lavfi\.scd\.mafd=([0-9.]+)", line)
        score = re.search(r"lavfi\.scd\.score=([0-9.]+)", line)
        if mafd:
            current["mafd"] = float(mafd.group(1))
        if score:
            current["score"] = float(score.group(1))
    if current:
        records.append(current)
    return records, {"returncode": code, "output_tail": output[-2000:]}


def scene_summary(
    scores: list[dict[str, Any]], shots: list[Shot], threshold: float, boundary_tolerance: float
) -> dict[str, Any]:
    top_spikes = sorted(scores, key=lambda item: item.get("score", 0.0), reverse=True)[:20]
    threshold_spikes = [item for item in scores if item.get("score", 0.0) >= threshold]
    boundaries: list[dict[str, Any]] = []
    for left, right in zip(shots, shots[1:]):
        boundary = left.end
        nearest = min(scores, key=lambda item: abs(item.get("time", 0.0) - boundary), default=None)
        window = [
            item
            for item in scores
            if abs(item.get("time", 0.0) - boundary) <= boundary_tolerance
        ]
        significant_window = [item for item in window if item.get("score", 0.0) >= threshold]
        selected = None
        selected_method = "none"
        if significant_window:
            selected = max(significant_window, key=lambda item: item.get("score", 0.0))
            selected_method = "max_significant_score_in_boundary_window"
        elif nearest:
            selected = nearest
            selected_method = "nearest_fallback_no_significant_peak"
        boundaries.append(
            {
                "from_shot": left.num,
                "to_shot": right.num,
                "declared_time": boundary,
                "nearest_diff_time": nearest.get("time") if nearest else None,
                "nearest_score": nearest.get("score") if nearest else None,
                "selected_diff_time": selected.get("time") if selected else None,
                "selected_score": selected.get("score") if selected else None,
                "selected_method": selected_method,
                "selected_delta": round(selected.get("time", 0.0) - boundary, 3) if selected else None,
                "selected_abs_delta": round(abs(selected.get("time", 0.0) - boundary), 3) if selected else None,
                "candidate_count": len(window),
                "significant_candidate_count": len(significant_window),
                "threshold": threshold,
                "delta": round(abs(selected.get("time", 0.0) - boundary), 3) if selected else None,
                "within_tolerance": bool(selected and abs(selected.get("time", 0.0) - boundary) <= boundary_tolerance),
            }
        )
    shot_motion: list[dict[str, Any]] = []
    for shot in shots:
        inside = [item for item in scores if shot.start <= item.get("time", 0.0) <= shot.end]
        avg = sum(item.get("score", 0.0) for item in inside) / len(inside) if inside else 0.0
        peak = max((item.get("score", 0.0) for item in inside), default=0.0)
        shot_motion.append(
            {
                "shot": shot.num,
                "start": shot.start,
                "end": shot.end,
                "avg_score": round(avg, 6),
                "peak_score": round(peak, 6),
                "sample_count": len(inside),
            }
        )
    return {
        "threshold": threshold,
        "score_source": "ffmpeg scdet lavfi.scd.score",
        "score_units": "raw scdet score points, not a 0-1 probability",
        "score_note": "Use threshold spikes as routing evidence only; visual review still checks the actual frames.",
        "threshold_spikes": threshold_spikes,
        "top_spikes": top_spikes,
        "boundaries": boundaries,
        "shot_motion": shot_motion,
    }


def check_ratio(expected: str, actual: float | None, tolerance: float) -> dict[str, Any]:
    expected_value = parse_ratio_value(expected)
    if expected_value is None or actual is None:
        return {"status": "UNKNOWN", "expected": expected, "actual": actual}
    relative_delta = abs(actual - expected_value) / expected_value
    status = "PASS" if relative_delta <= tolerance else "RISK_OR_FAIL_REVIEW"
    return {
        "status": status,
        "expected": expected,
        "expected_float": expected_value,
        "actual_float": actual,
        "relative_delta": round(relative_delta, 6),
        "tolerance": tolerance,
    }


def check_duration(expected: float | None, actual: float, tolerance: float) -> dict[str, Any]:
    if expected is None:
        return {"status": "UNKNOWN", "expected": expected, "actual": actual}
    delta = abs(actual - expected)
    status = "PASS" if delta <= tolerance else "RISK_OR_FAIL_REVIEW"
    return {"status": status, "expected": expected, "actual": actual, "delta": round(delta, 3), "tolerance": tolerance}


def deterministic_review_policy(checks: dict[str, dict[str, Any]], audit_profile: str) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    unknowns: list[str] = []
    for name in ("duration", "ratio"):
        check = checks.get(name, {})
        status = check.get("status")
        if status == "RISK_OR_FAIL_REVIEW":
            blockers.append(
                {
                    "check": name,
                    "status": status,
                    "required_visual_verdict": "FAIL_BLOCKED",
                    "test_override": "Only if the user explicitly accepts this as a test-only risk.",
                    "details": check,
                }
            )
        elif status == "UNKNOWN":
            unknowns.append(name)

    policy_status = "DETERMINISTIC_PASS"
    visual_verdict_floor = None
    if blockers:
        policy_status = "DETERMINISTIC_FAIL_BLOCKED_REQUIRED"
        visual_verdict_floor = "FAIL_BLOCKED"
    elif unknowns:
        policy_status = "DETERMINISTIC_UNKNOWN_REVIEW_REQUIRED"

    return {
        "status": policy_status,
        "audit_profile": audit_profile,
        "visual_verdict_floor": visual_verdict_floor,
        "blockers": blockers,
        "unknowns": unknowns,
        "note": "This policy is deterministic gate evidence, not a visual-content judgment.",
    }


def deterministic_blocker_summary(policy: dict[str, Any]) -> str:
    blockers = policy.get("blockers", [])
    if not blockers:
        return "NONE"
    parts = []
    for item in blockers:
        check = item.get("check")
        details = item.get("details", {})
        if check == "duration":
            parts.append(
                f"duration actual={details.get('actual')} expected={details.get('expected')} "
                f"delta={details.get('delta')} tolerance={details.get('tolerance')}"
            )
        elif check == "ratio":
            parts.append(
                f"ratio actual={details.get('actual_float')} expected={details.get('expected')} "
                f"relative_delta={details.get('relative_delta')} tolerance={details.get('tolerance')}"
            )
        else:
            parts.append(str(check))
    return "; ".join(parts)


def make_evidence(
    ffmpeg: str,
    frames_dir: Path,
    evidence_dir: Path,
    cuts_dir: Path,
    task: ClipTask,
    scores: list[dict[str, Any]],
    fps: float | None,
    frame_count: int,
    epsilon: float,
    scene_threshold: float,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {"shots": [], "cuts": [], "flags": []}
    for shot in task.shots:
        start_t = min(max(shot.start + epsilon, shot.start), max(shot.start, shot.end - 0.001))
        mid_t = shot.start + shot.duration / 2
        end_t = max(shot.start, shot.end - epsilon)
        shot_dir = evidence_dir / f"shot_{shot.num:02d}"
        records = {
            "in": copy_frame(frames_dir, shot_dir / f"Clip{task.num}_s{shot.num}_in_{start_t:.2f}s.jpg", start_t, fps, frame_count),
            "mid": copy_frame(frames_dir, shot_dir / f"Clip{task.num}_s{shot.num}_mid_{mid_t:.2f}s.jpg", mid_t, fps, frame_count),
            "out": copy_frame(frames_dir, shot_dir / f"Clip{task.num}_s{shot.num}_out_{end_t:.2f}s.jpg", end_t, fps, frame_count),
        }
        evidence["shots"].append(
            {
                "shot": shot.num,
                "start": shot.start,
                "end": shot.end,
                "refs": shot.refs,
                "prompt_text": shot.text,
                "orientation_anchor_review": extract_orientation_anchors(shot.text),
                "frames": records,
            }
        )

    for left, right in zip(task.shots, task.shots[1:]):
        left_index = frame_index_for_time(max(left.start, left.end - epsilon), fps, frame_count)
        right_index = frame_index_for_time(min(right.end, right.start + epsilon), fps, frame_count)
        out = cuts_dir / f"Clip{task.num}_cut_{left.num}-{right.num}_{left.end:.2f}s.jpg"
        pair = hstack_pair(ffmpeg, frame_path(frames_dir, left_index), frame_path(frames_dir, right_index), out)
        pair.update(
            {
                "from_shot": left.num,
                "to_shot": right.num,
                "declared_time": left.end,
                "left_frame_index": left_index,
                "right_frame_index": right_index,
            }
        )
        evidence["cuts"].append(pair)

    flagged = sorted([item for item in scores if item.get("score", 0.0) >= scene_threshold], key=lambda x: x["time"])
    if not flagged:
        flagged = sorted(scores, key=lambda x: x.get("score", 0.0), reverse=True)[:10]
    for item in flagged[:50]:
        t = float(item.get("time", 0.0))
        dest = evidence_dir / "flags" / f"Clip{task.num}_flag_{t:.2f}s_score_{item.get('score', 0.0):.3f}.jpg"
        record = copy_frame(frames_dir, dest, t, fps, frame_count)
        record.update({"score": item.get("score"), "mafd": item.get("mafd")})
        evidence["flags"].append(record)
    return evidence


def write_json(path: Path, data: dict[str, Any]) -> None:
    # Keep JSON ASCII-safe so PowerShell's default decoding cannot corrupt
    # Chinese Windows paths into invalid escape sequences before ConvertFrom-Json.
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")


def write_report_template(path: Path, project_name: str, task: ClipTask, video: Path, manifest: dict[str, Any]) -> None:
    deterministic = manifest.get("deterministic_checks", {})
    deterministic_policy = manifest.get("deterministic_review_policy", {})
    scene = manifest.get("scene_diff", {})
    blocker_summary = deterministic_blocker_summary(deterministic_policy)
    shot_sections: list[str] = []
    for shot in task.shots:
        anchor_review = extract_orientation_anchors(shot.text)
        anchor_list = ", ".join(anchor_review["anchors"]) if anchor_review["anchors"] else "未检出"
        orientation_clauses = " / ".join(anchor_review["orientation_clauses"]) if anchor_review["orientation_clauses"] else "未检出"
        shot_sections.append(
            f"""## 分镜 {shot.num}（{shot.start:g}-{shot.end:g}s）— Prompt原话
- 镜头/画面/动作/朝向/站位/道具：{shot.text}
- 引用：{", ".join(shot.refs) if shot.refs else "未检出"}
- 参照物锚定候选：{anchor_list}
- 朝向/视线原句：{orientation_clauses}
- 审片提醒：先定位参照物在画面方位，再判人物正对/背对/侧对；被光打亮不等于朝向该参照物。

| 维度 | 主判 | 证据(帧@t / 观察 vs 原话) | 复审 | 裁定 |
|---|---|---|---|---|
| 分镜对位 |  |  |  |  |
| 人物朝向（参照物锚定） |  |  |  |  |
| 站位漂移（相对同一参照物） |  |  |  |  |
| 道具漂移 |  |  |  |  |
| 跨镜一致 |  |  |  |  |
| 身份不跑脸 |  |  |  |  |
| 动作节拍/口型/收尾pose |  |  |  |  |
| 场景人口/光向/地标 |  |  |  |  |
| 锚点执行 |  |  |  |  |
"""
        )

    report = f"""# {project_name} 生成视频逐帧审片报告 — Clip{task.num}

**视频**：{video}
**Prompt标注时长**：{task.duration}
**实测**：{manifest.get("metadata", {}).get("duration")}s / {manifest.get("metadata", {}).get("fps")}fps / {manifest.get("metadata", {}).get("width")}x{manifest.get("metadata", {}).get("height")} / {manifest.get("metadata", {}).get("display_aspect_ratio")}
**总帧数**：{manifest.get("frame_count")}
**抽帧目录**：{manifest.get("output_dir")}
**工具有效状态**：{manifest.get("effective_status")}（preflight={manifest.get("status")}）
**确定性核对**：时长 {deterministic.get("duration", {}).get("status")}；比例 {deterministic.get("ratio", {}).get("status")}；黑帧 待视觉审查
**确定性闸最低判定**：{deterministic_policy.get("visual_verdict_floor") or "NONE"}；{deterministic_policy.get("status")}
**确定性硬风险**：{blocker_summary}
**差分疑点**：阈值命中 {len(scene.get("threshold_spikes", []))}；阈值 {scene.get("threshold")} raw scdet score points；Top spikes 见 `frame_audit_manifest.json`
**前置完整性**：全帧 {manifest.get("preflight", {}).get("full_frames")}；contact sheet {manifest.get("preflight", {}).get("contact_sheets")}；差分 {manifest.get("preflight", {}).get("scene_diff")}；分镜映射 {manifest.get("preflight", {}).get("shot_mapping")} → {manifest.get("effective_status")}
**复审方式**：主判 / 独立盲审 / 分歧裁决

> 若“确定性闸最低判定”为 FAIL_BLOCKED，视觉层不得因为工具状态是 AUDIT_READY 而放行；除非用户明确接受测试风险，否则最终结论必须按 FAIL_BLOCKED 处理。

{"\n".join(shot_sections)}

## Clip{task.num} 结论

- 怀疑项穷举：
- 主判 / 复审 / 分歧裁决：
- **状态**：AUDIT_INCOMPLETE / PASS / ACCEPTED_WITH_RISK / FAIL_BLOCKED / REGENERATED_PASS
- 处置建议：补证据 / video-auto-edit剪辑层处理 / 原样重生成 / 修 Prompt / 回 Phase8.5 / 回 Phase7 / 回 Phase5 / 回 Phase4

## 返修决策

> 先证明低成本处理不伤剧情、连续和规格；证明不了就升级。剪辑只能真修复，不能遮盖内容错。若需要重生成，先完成内容定稿，再批量处理水印/比例/裁切等容器问题。

| 位置/问题 | 问题类型(证据/容器/局部可删/内容错误/上游缺失) | 严重度(BLOCKER/EDIT_FIX/REGEN_REQUIRED/ACCEPTABLE_RISK) | 是否承重 | 是否允许剪 | 可剪时间码 | 剪后影响 | 首选处理 | 备用处理 | 最小回退层级(P9/P8/P8.5/P7/P5/P4) | Prompt修正方向 | 重生成重试预算 | 修后复检范围 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|

默认重试预算：同 Prompt 重抽 <=2；Prompt 修版重生成 <=2；仍失败则升级到 Phase5 blocking 修复、拆分分镜或重拆 Clip。
默认复检范围：重生成=该 Clip 全闸10；重剪/换切点=切点对+时长+音画同步；跨镜成对=两 Clip+边界；容器批量=全片 ffprobe+抽样视觉复核。
"""
    path.write_text(report, encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt_file", help="Path to Phase8 prompt set markdown.")
    parser.add_argument("--clip", type=int, required=True)
    parser.add_argument("--video", action="append", required=True, help="Generated video path. Repeatable; first is audited.")
    parser.add_argument("--project-dir", help="Project directory; defaults to prompt file parent.")
    parser.add_argument("--out-dir", help="Audit output directory.")
    parser.add_argument("--anchor-pack")
    parser.add_argument("--ref-dir")
    parser.add_argument("--ratio", default="16:9", help="Fallback expected ratio if prompt file does not declare one.")
    parser.add_argument(
        "--audit-profile",
        choices=("final", "test"),
        default="final",
        help="final uses stricter release tolerances; test keeps low-res platform tolerance explicit.",
    )
    parser.add_argument(
        "--ratio-tolerance",
        type=float,
        default=None,
        help="Relative display-aspect tolerance. Defaults: final=0.01, test=0.03.",
    )
    parser.add_argument("--duration-tolerance", type=float, default=0.3)
    parser.add_argument(
        "--scene-threshold",
        type=float,
        default=5.0,
        help="Raw ffmpeg scdet score threshold; this is not a 0-1 probability.",
    )
    parser.add_argument("--boundary-tolerance", type=float, default=0.5)
    parser.add_argument("--epsilon", type=float, default=0.08)
    parser.add_argument("--jpeg-quality", type=int, default=2)
    args = parser.parse_args(argv)
    ratio_tolerance = args.ratio_tolerance
    if ratio_tolerance is None:
        ratio_tolerance = 0.03 if args.audit_profile == "test" else 0.01

    prompt_file = Path(args.prompt_file).resolve()
    if not prompt_file.exists():
        print(f"[AUDIT_INCOMPLETE] Prompt file does not exist: {prompt_file}")
        return 1
    videos = [Path(item).resolve() for item in args.video]
    missing_videos = [str(item) for item in videos if not item.exists()]
    if missing_videos:
        print(f"[AUDIT_INCOMPLETE] Missing video(s): {', '.join(missing_videos)}")
        return 1

    project_dir = Path(args.project_dir).resolve() if args.project_dir else prompt_file.parent
    video = videos[0]

    try:
        ffmpeg = require_tool("ffmpeg")
        ffprobe = require_tool("ffprobe")
        ratio, tasks = parse_prompt_file(prompt_file, args.ratio)
        task = select_clip(tasks, args.clip)
        metadata = probe_video(video, ffprobe)
    except Exception as exc:  # noqa: BLE001 - CLI must surface exact setup issue
        print(f"[AUDIT_INCOMPLETE] {exc}")
        return 1

    output_dir = Path(args.out_dir).resolve() if args.out_dir else default_output_dir(video, project_dir, task.num)
    frames_dir = output_dir / "frames"
    evidence_dir = output_dir / "evidence"
    cuts_dir = output_dir / "cut_pairs"
    sheets_dir = output_dir / "sheets"
    for directory in (frames_dir, evidence_dir, cuts_dir, sheets_dir):
        reset_managed_dir(directory)

    preflight = {
        "full_frames": "FAIL",
        "contact_sheets": "FAIL",
        "scene_diff": "FAIL",
        "shot_mapping": "PASS" if task.shots else "FAIL",
    }
    code, full_output = extract_full_frames(ffmpeg, video, frames_dir, args.jpeg_quality)
    frame_count = count_images(frames_dir)
    if code == 0 and frame_count > 0:
        preflight["full_frames"] = "PASS"

    sheets_code, sheets_output, sheet_count = make_contact_sheets(ffmpeg, video, sheets_dir)
    if sheets_code == 0 and sheet_count > 0:
        preflight["contact_sheets"] = "PASS"

    scene_scores, scene_status = run_scene_scores(ffmpeg, video)
    if scene_status.get("returncode") == 0 and scene_scores:
        preflight["scene_diff"] = "PASS"

    scene = scene_summary(scene_scores, task.shots, args.scene_threshold, args.boundary_tolerance)
    evidence = make_evidence(
        ffmpeg,
        frames_dir,
        evidence_dir,
        cuts_dir,
        task,
        scene_scores,
        metadata.get("fps"),
        frame_count,
        args.epsilon,
        args.scene_threshold,
    )

    deterministic_checks = {
        "duration": check_duration(task.duration, metadata["duration"], args.duration_tolerance),
        "ratio": check_ratio(ratio, metadata.get("display_ratio_float"), ratio_tolerance),
    }
    deterministic_policy = deterministic_review_policy(deterministic_checks, args.audit_profile)

    status = "AUDIT_READY" if all(value == "PASS" for value in preflight.values()) else "AUDIT_INCOMPLETE"
    deterministic_block = bool(deterministic_policy.get("blockers"))
    effective_status = "AUDIT_READY_WITH_DETERMINISTIC_RISK" if status == "AUDIT_READY" and deterministic_block else status
    manifest: dict[str, Any] = {
        "status": status,
        "effective_status": effective_status,
        "deterministic_block": deterministic_block,
        "visual_verdict_floor": deterministic_policy.get("visual_verdict_floor"),
        "note": "This tool prepares deterministic evidence only. Visual verdict must be filled in the audit report.",
        "prompt_file": str(prompt_file),
        "project_dir": str(project_dir),
        "source_videos": [str(item) for item in videos],
        "clip": task.num,
        "ratio": ratio,
        "audit_profile": args.audit_profile,
        "output_dir": str(output_dir),
        "frames_dir": str(frames_dir),
        "evidence_dir": str(evidence_dir),
        "cut_pairs_dir": str(cuts_dir),
        "sheets_dir": str(sheets_dir),
        "metadata": metadata,
        "frame_count": frame_count,
        "sheet_count": sheet_count,
        "preflight": preflight,
        "deterministic_checks": deterministic_checks,
        "deterministic_review_policy": deterministic_policy,
        "scene_diff_status": scene_status,
        "scene_diff": scene,
        "shots": [
            {
                "shot": shot.num,
                "start": shot.start,
                "end": shot.end,
                "refs": shot.refs,
                "prompt_text": shot.text,
                "orientation_anchor_review": extract_orientation_anchors(shot.text),
            }
            for shot in task.shots
        ],
        "evidence": evidence,
        "full_frame_extraction": {"returncode": code, "output_tail": full_output[-2000:]},
        "contact_sheets": {"returncode": sheets_code, "output_tail": sheets_output[-2000:]},
        "anchor_pack": str(Path(args.anchor_pack).resolve()) if args.anchor_pack else None,
        "ref_dir": str(Path(args.ref_dir).resolve()) if args.ref_dir else None,
    }
    manifest_path = output_dir / "frame_audit_manifest.json"
    write_json(manifest_path, manifest)
    report_path = output_dir / f"{project_dir.name}_生成视频逐帧审片报告_Clip{task.num}_模板.md"
    write_report_template(report_path, project_dir.name, task, video, manifest)

    print(
        f"[{effective_status}] Clip {task.num}: frames={frame_count}, shots={len(task.shots)}, "
        f"deterministic={deterministic_policy.get('status')}"
    )
    if deterministic_policy.get("blockers"):
        print(f"[DETERMINISTIC_FAIL_BLOCKED_REQUIRED] {deterministic_blocker_summary(deterministic_policy)}")
    print(f"Audit directory: {output_dir}")
    print(f"Manifest: {manifest_path}")
    print(f"Report template: {report_path}")
    return 0 if status == "AUDIT_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
