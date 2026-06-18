#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Validate official Jimeng Phase8 8-A video-prompt Markdown."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


HEADER_RE = re.compile(r"生成一个由以下\s*(\d+)\s*个分镜组成的视频(?P<punc>[：:。\.])")
SHOT_RE = re.compile(r"分镜\s*(\d+)\s*[:：]\s*(\d+)\s*-\s*(\d+)\s*s", re.I)
DECIMAL_TIME_RE = re.compile(
    r"分镜\s*\d+\s*[:：]\s*(?:\d+\.\d+\s*-\s*\d+(?:\.\d+)?|\d+(?:\.\d+)?\s*-\s*\d+\.\d+)\s*s",
    re.I,
)
LINE_RE = re.compile(r"说\s*[:：]\s*「")
LINE_WITH_VOICE_RE = re.compile(r"说\s*[:：]\s*「[^」]*」\s*音色\s*[:：]?")
PRONOUN_RE = re.compile(
    r"(?<![其吉维])他(?:们)?|她(?:们)?|(?<!其)它(?:们)?|女主|男主|女孩|男孩|女人|男人|老人|小孩|两人|二人|几人|一行人|那个人|对方|另一人"
)
POPULATION_RE = re.compile(
    r"无人物|没有人|不出现其他人|不出现任何人|无旁人|空无一人|除[^，。；]*外[^，。；]*(?:无旁人|无其他人|不出现其他人)|除[^，。；]*外不出现其他人|"
    r"只有[^，。；]*(?:@图片\d+|<subject>|一人|两人|二人|独自|自己)|"
    r"只剩[^，。；]*|空镜|空场景|空教室|空房间|空站台|空旷|空着|空座位|大半[^，。；]*空|"
    r"背景(?:有|中有|里有|出现|保持|维持)|背景学生|背景同学|"
    r"学生|同学(?:们)?|路人|行人|乘客|旅客|人流|人群|群众|人来人往|"
    r"宾客|观众|顾客|工作人员|店员|老师|职员|客人",
    re.I,
)
STORYBOARD_REF_RE = re.compile(
    r"@全案分镜图|@故事板|@分镜宫格|@\[?\s*storyboard\s*ref\s*\]?|"
    r"(?:分镜宫格图|全案分镜图|故事板|STORYBOARD\s+GRID|storyboard[-\s]+grid)[^\n。；;]{0,100}@图片\d+|"
    r"@图片\d+[^\n。；;]{0,100}(?:分镜宫格图|全案分镜图|故事板|storyboard[-\s]+grid)",
    re.I,
)
STORYBOARD_PLANNING_RE = re.compile(
    r"ONLY\s+as\s+motion\s+planning\s+reference|motion\s+planning\s+reference|planning\s+reference|"
    r"仅用于|只用于|仅作为|只作为|不得作为|不要把它当作",
    re.I,
)
STORYBOARD_PLANNING_SCOPE_RE = re.compile(
    r"镜头顺序|构图|角色站位|动作调度|转场节奏|结尾状态|调度|顺序|"
    r"panel\s+order|framing|character\s+blocking|camera\s+rhythm|action\s+flow|transition\s+rhythm|"
    r"sequential\s+keyframe|not\s+as\s+a\s+collage",
    re.I,
)
STORYBOARD_ARTIFACT_GROUPS = [
    ("borders", ("panel borders", "storyboard borders", "宫格边框", "分镜边框", "面板边框", "边框")),
    ("numbers", ("panel numbers", "编号", "数字")),
    ("text/labels/headers", ("text labels", "labels", "headers", "文字", "标签", "标题")),
    ("arrows", ("arrows", "箭头")),
    ("timing notes", ("timing notes", "时间标注", "时长标注", "timing")),
    ("grid lines", ("grid lines", "网格线", "宫格线", "分隔线")),
    ("UI", ("ui", "界面")),
    ("watermark", ("watermark", "水印")),
    ("logo", ("logo",)),
]
DEFAULT_COMPLIANCE_WARN = [
    "诺兰",
    "昆汀",
    "斯皮尔伯格",
    "漫威",
    "迪士尼",
    "DC",
    "吉卜力",
    "宫崎骏",
    "今敏",
    "蒂姆波顿",
    "周杰伦",
]


class Report:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.fails = 0

    def add(self, status: str, message: str) -> None:
        self.lines.append(f"[{status}] {message}")
        if status == "FAIL":
            self.fails += 1

    def ok(self, message: str) -> None:
        self.add("PASS", message)

    def fail(self, message: str) -> None:
        self.add("FAIL", message)

    def warn(self, message: str) -> None:
        self.add("WARN", message)

    def info(self, message: str) -> None:
        self.add("INFO", message)


def ref_nums(block: str, label: str, *aliases: str) -> list[int]:
    names = [re.escape(label), *(re.escape(alias) for alias in aliases)]
    pattern = r"@(?:" + "|".join(names) + r")\s*(\d+)"
    return [int(x) for x in re.findall(pattern, block, re.I)]


def check_task_refs(r: Report, idx: int, block: str, label: str, *aliases: str) -> list[int]:
    found = sorted(set(ref_nums(block, label, *aliases)))
    if found and found != list(range(1, max(found) + 1)):
        r.fail(f"Task {idx} @{label}N references are not consecutive: {found}; must start at 1.")
    elif found:
        r.ok(f"Task {idx} @{label}N references are consecutive: 1-{max(found)}.")
    return found


def segment_shots(block: str, shot_matches: list[re.Match[str]]) -> list[tuple[int, str]]:
    segments: list[tuple[int, str]] = []
    for i, match in enumerate(shot_matches):
        start = match.start()
        end = shot_matches[i + 1].start() if i + 1 < len(shot_matches) else len(block)
        segments.append((int(match.group(1)), block[start:end]))
    return segments


def strip_dialogue_text(segment: str) -> str:
    """Keep dialogue structure, but ignore quoted line text for pronoun alias checks."""
    return re.sub(r"「[^」]*」", "「」", segment)


def validate(text: str, args: argparse.Namespace) -> Report:
    r = Report()
    if args.expected_clips is not None:
        r.info("Legacy --expected-clips is treated as --expected-shots. Prefer --expected-shots.")
        if args.expected_shots is None:
            args.expected_shots = args.expected_clips

    if not text.strip():
        r.fail("Output is empty.")
        return r
    r.ok("Output is non-empty.")

    if re.search(r"生成一个由以下\s*\d+\s*个分镜组成的视频[。\.]", text):
        r.fail("Template header uses a period; it must end with colon.")

    headers = list(HEADER_RE.finditer(text))
    n_tasks = len(headers)
    if not headers:
        r.fail("Missing official header: 生成一个由以下N个分镜组成的视频：")
        check_globals(r, text, args)
        return r

    total_shots = 0
    for idx, header in enumerate(headers, 1):
        end = headers[idx].start() if idx < len(headers) else len(text)
        block = text[header.end() : end]
        declared = int(header.group(1))

        if header.group("punc") in ("：", ":"):
            r.ok(f"Task {idx} header uses colon.")
        else:
            r.fail(f"Task {idx} header does not use colon.")

        if DECIMAL_TIME_RE.search(block):
            r.fail(f"Task {idx} contains decimal shot time; Phase8 spans must be integer seconds.")

        shot_matches = list(SHOT_RE.finditer(block))
        shots = [(int(m.group(1)), int(m.group(2)), int(m.group(3))) for m in shot_matches]
        total_shots += len(shots)

        if len(shots) == declared:
            r.ok(f"Task {idx} shot count {len(shots)} equals declared {declared}.")
        else:
            r.fail(f"Task {idx} shot count {len(shots)} != declared {declared}.")

        nums = [shot[0] for shot in shots]
        if nums and nums != list(range(1, len(shots) + 1)):
            r.fail(f"Task {idx} shot numbers are not consecutive: {nums}.")

        if shots:
            if shots[0][1] != 0:
                r.fail(f"Task {idx} first shot does not start at 0s; got {shots[0][1]}s.")
            bad = [f"{a}-{b}s" for _, a, b in shots if a >= b]
            if bad:
                r.fail(f"Task {idx} has invalid ranges: {', '.join(bad)}.")

            gaps = []
            for i in range(1, len(shots)):
                prev_end = shots[i - 1][2]
                cur_start = shots[i][1]
                if cur_start != prev_end:
                    gaps.append(f"shot {shots[i-1][0]} ends {prev_end}s but shot {shots[i][0]} starts {cur_start}s")
            if gaps:
                r.fail(f"Task {idx} time spans are not adjacent: {'; '.join(gaps)}.")
            else:
                r.ok(f"Task {idx} time spans are adjacent from 0s.")

            duration = shots[-1][2] - shots[0][1]
            if 4 <= duration <= args.max_duration:
                r.ok(f"Task {idx} duration {duration}s is within 4-{args.max_duration}s.")
            else:
                r.fail(f"Task {idx} duration {duration}s is outside 4-{args.max_duration}s.")

        check_task_refs(r, idx, block, "图片", "image", "img")
        check_task_refs(r, idx, block, "视频", "video")
        check_task_refs(r, idx, block, "音频", "audio")

        for shot_num, segment in segment_shots(block, shot_matches):
            if "镜头：" not in segment and "镜头:" not in segment:
                r.fail(f"Task {idx} shot {shot_num} is missing 镜头： field.")
            line_count = len(LINE_RE.findall(segment))
            voiced_line_count = len(LINE_WITH_VOICE_RE.findall(segment))
            if line_count > voiced_line_count:
                r.fail(
                    f"Task {idx} shot {shot_num} has {line_count} dialogue line(s) but only "
                    f"{voiced_line_count} line(s) with 音色 immediately after the quoted text."
                )
            segment_images = ref_nums(segment, "图片", "image", "img")
            if not segment_images:
                message = f"Task {idx} shot {shot_num} contains no @图片N reference; check for missing material/scene binding."
                if args.require_image_each_shot:
                    r.fail(message)
                else:
                    r.warn(message)
            if args.scene_image and not (set(args.scene_image) & set(segment_images)):
                expected = ", ".join(f"@图片{n}" for n in args.scene_image)
                r.fail(
                    f"Task {idx} shot {shot_num} does not explicitly embed any declared scene image ({expected}); "
                    "each shot body must include the scene reference to prevent scene drift."
                )
            pronoun_scan = strip_dialogue_text(segment)
            for pronoun in sorted(set(PRONOUN_RE.findall(pronoun_scan))):
                message = f"Task {idx} shot {shot_num} contains possible pronoun/role alias: {pronoun}."
                if args.fail_pronouns:
                    r.fail(message)
                else:
                    r.warn(message)
            if args.require_population_state and not POPULATION_RE.search(pronoun_scan):
                r.fail(
                    f"Task {idx} shot {shot_num} lacks explicit environment population/background-crowd state; "
                    "write no people, only named characters, or background students/passersby/crowds near the scene reference."
                )

    if args.expected_tasks is not None:
        if n_tasks == args.expected_tasks:
            r.ok(f"Task count {n_tasks} matches expected {args.expected_tasks}.")
        else:
            r.fail(f"Task count {n_tasks} != expected {args.expected_tasks}.")

    if args.expected_shots is not None:
        if total_shots == args.expected_shots:
            r.ok(f"Total shot lines {total_shots} match expected {args.expected_shots}.")
        else:
            r.fail(f"Total shot lines {total_shots} != expected {args.expected_shots}.")

    if n_tasks == 1:
        block = text[headers[0].end() :]
        assert_ref_count(r, block, args.ref_images, "图片", "image", "img")
        assert_ref_count(r, block, args.ref_videos, "视频", "video")
        assert_ref_count(r, block, args.ref_audios, "音频", "audio")
    elif any(v is not None for v in (args.ref_images, args.ref_videos, args.ref_audios)):
        r.info("Multi-task output: exact --ref-images/videos/audios assertions are skipped; per-task continuity was checked.")

    check_globals(r, text, args)
    return r


def assert_ref_count(r: Report, block: str, expected: int | None, label: str, *aliases: str) -> None:
    if expected is None:
        return
    found = sorted(set(ref_nums(block, label, *aliases)))
    if expected == 0:
        if found:
            r.fail(f"Expected no @{label}N references, found {found}.")
        else:
            r.ok(f"No @{label}N references, as expected.")
        return
    expected_seq = list(range(1, expected + 1))
    if found == expected_seq:
        r.ok(f"@{label}N references match expected 1-{expected}.")
    else:
        r.fail(f"@{label}N references expected {expected_seq}, found {found}.")


def check_globals(r: Report, text: str, args: argparse.Namespace) -> None:
    has_global = (
        (
            "禁止生成任何台词/旁白字幕" in text
            or ("生成清晰可读的文字" in text and "文字内容严格匹配原文" in text)
        )
        and "禁止生成背景音乐" in text
    )
    if has_global:
        r.ok("Global requirement ending exists.")
    else:
        r.fail("Missing global requirement ending.")

    if args.language_rule:
        if re.search(r"语言\s*[:：]\s*\S+", text):
            r.ok("Language rule exists.")
        else:
            r.fail("Missing language rule.")

    if args.subject_required:
        if re.search(r"<subject>[^<]+</subject>", text):
            r.ok("Subject tag exists.")
        else:
            r.fail("Missing required <subject>...</subject>.")

    if args.negative_required:
        if re.search(r"NEGATIVE\s*[:：]|负向|禁止画面崩坏|禁止人物穿帮", text, re.I):
            r.ok("Negative terms exist.")
        else:
            r.fail("Missing required negative terms.")

    if args.require_storyboard_artifact_guard:
        check_storyboard_artifact_guard(r, text)

    for term in args.banned_term:
        if term.lower() in text.lower():
            r.fail(f"Banned term found: {term}")

    for term in DEFAULT_COMPLIANCE_WARN:
        if term in text:
            r.warn(f"Possible film/director/celebrity/brand/style name: {term}. Replace with neutral description if needed.")


def check_storyboard_artifact_guard(r: Report, text: str) -> None:
    if STORYBOARD_REF_RE.search(text):
        r.ok("Storyboard/grid reference is present.")
    else:
        r.fail("Missing storyboard/grid reference for Phase8.5 guard.")

    if STORYBOARD_PLANNING_RE.search(text) and STORYBOARD_PLANNING_SCOPE_RE.search(text):
        r.ok("Storyboard/grid is constrained to planning, framing, motion, or sequential-keyframe use.")
    else:
        r.fail(
            "Storyboard/grid reference is not clearly limited to motion/composition planning; "
            "add wording such as '仅用于镜头顺序、构图、动作调度...' or 'ONLY as motion planning reference'."
        )

    lower_text = text.lower()
    for label, terms in STORYBOARD_ARTIFACT_GROUPS:
        if any(term.lower() in lower_text for term in terms):
            r.ok(f"Storyboard artifact exclusion includes {label}.")
        else:
            r.fail(f"Storyboard artifact exclusion is missing {label}.")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt_file")
    parser.add_argument("--expected-tasks", type=int, help="Expected generation task/header count.")
    parser.add_argument("--expected-shots", type=int, help="Expected total shot line count.")
    parser.add_argument("--expected-clips", type=int, help="Deprecated alias for --expected-shots.")
    parser.add_argument("--ref-images", type=int)
    parser.add_argument("--ref-videos", type=int)
    parser.add_argument("--ref-audios", type=int)
    parser.add_argument(
        "--scene-image",
        type=int,
        action="append",
        default=None,
        help="Scene image number; may be passed multiple times. Every shot body must contain at least one declared @图片N.",
    )
    parser.add_argument("--require-image-each-shot", action="store_true", help="Fail if any shot body has no @图片N reference.")
    parser.add_argument(
        "--require-population-state",
        action="store_true",
        help="Fail if any shot body lacks explicit no-people/only-named-characters/background-crowd wording.",
    )
    parser.add_argument(
        "--require-storyboard-artifact-guard",
        action="store_true",
        help="Fail unless storyboard/grid references are limited to planning use and artifact rendering is excluded.",
    )
    parser.add_argument("--max-duration", type=int, default=10, help="Maximum task duration in seconds; default is 10.")
    parser.add_argument(
        "--fail-pronouns",
        action="store_true",
        help="Fail on possible role pronouns/aliases outside quoted dialogue instead of warning.",
    )
    parser.add_argument("--language-rule", action="store_true", default=True)
    parser.add_argument("--no-language-rule", dest="language_rule", action="store_false")
    parser.add_argument("--negative-required", action="store_true")
    parser.add_argument("--subject-required", action="store_true")
    parser.add_argument("--banned-term", action="append", default=[])
    args = parser.parse_args(argv)

    path = Path(args.prompt_file)
    if not path.exists():
        print(f"[FAIL] File does not exist: {path}")
        print("RESULT: FAIL (1 FAIL)")
        return 1

    text = path.read_text(encoding="utf-8-sig")
    report = validate(text, args)
    for line in report.lines:
        print(line)
    if report.fails:
        print(f"RESULT: FAIL ({report.fails} FAIL)")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
