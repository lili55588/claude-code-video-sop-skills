#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
确定性校验器：即梦官方 8-A 视频生成 Prompt（{项目名}_视频生成Prompt集.md）。

移植自 Codex 版 validate_phase8_prompt.py，并修复其 4 个 P0：
  1) 单分镜 Clip 4-10s 与"单镜 1-8s"矛盾 —— 本脚本只校验「任务总时长 4-10s」与「分镜段本身合法」，
     不再卡单镜上限（官方计时为整数秒、向上取整；小数时间段由 DECIMAL_TIME_RE 直接 FAIL）。
  2) `--expected-clips` 名实不符 —— 拆成 `--expected-tasks`（生成任务/表头数）与
     `--expected-shots`（分镜行总数），语义清晰。
  3) 不查时间段连贯性 —— 新增「首段起始 0s + 相邻段首尾相接（无间隙/无重叠）」校验。
  4) 引用连续性是全局判定 —— 改为「逐任务」校验：每个生成任务内 @图片N/@视频N/@音频N
     都必须从 1 连续，支持多任务各自从 @图片1 重启。

另补充确定性检查：每个分镜含「镜头：」五段字段；**台词『」』后必须紧邻『音色：』（邻接校验，非计数）**；
**每个分镜显式嵌入场景图 @图片N（--scene-image 可重复传多值，任一命中即过，支持跨场景 Clip；防场景漂移）**；
分镜零引用软告警；代称默认 WARN、--fail-pronouns 升级 FAIL（剔除「」内台词后扫描）；合规名软告警。

用法：
  python validate_phase8_prompt.py "{项目名}_视频生成Prompt集.md"
        [--expected-tasks N] [--expected-shots N]
        [--ref-images N] [--ref-videos N] [--ref-audios N]
        [--scene-image N [--scene-image M ...]] [--fail-pronouns]
        [--subject-required] [--negative-required] [--no-language-rule]
        [--banned-term 诺兰 --banned-term 漫威 ...]

退出码：全 PASS -> 0；存在 FAIL -> 1（WARN/INFO 不阻断）。
"""

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
LINE_RE = re.compile(r"说\s*[:：]\s*「")           # 一句台词（计数用）
DIALOG_RE = re.compile(r"说\s*[:：]\s*「[^」]*」")   # 完整台词（邻接校验用：」后须紧跟 音色：）
QUOTE_RE = re.compile(r"「[^」]*」")                 # 引号内台词（代称扫描前剔除）
# 叙述代称：默认 WARN，--fail-pronouns 升级 FAIL；单字代词带前置排除（其他/吉他/维他命/其它）
# 通用名词（女孩/男人/老人…）也算代称——正文必须写全名（借鉴 Codex 版扩列，2026-06-12）
PRONOUN_RE = re.compile(
    r"(?<![其吉维])他(?:们)?|她(?:们)?|(?<!其)它(?:们)?"
    r"|这个人|那个人|女主|男主|两人|二人|几人|一行人|对方|另一人"
    r"|女孩|男孩|女人|男人|老人|小孩"
)
# Phase8.5 故事板/分镜宫格守卫（--require-storyboard-artifact-guard 用）：
# 上传宫格图时，正文须 ① 出现宫格引用 ② 限定其"仅供构图/调度规划" ③ 逐组排除 artifact 渲染。
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
    ("边框", ("panel borders", "storyboard borders", "宫格边框", "分镜边框", "面板边框", "边框")),
    ("编号", ("panel numbers", "编号", "数字")),
    ("文字/标签/标题", ("text labels", "labels", "headers", "文字", "标签", "标题")),
    ("箭头", ("arrows", "箭头")),
    ("时间标注", ("timing notes", "时间标注", "时长标注", "timing")),
    ("网格线", ("grid lines", "网格线", "宫格线", "分隔线")),
    ("UI", ("ui", "界面")),
    ("水印", ("watermark", "水印")),
    ("logo", ("logo",)),
]

# 合规软告警：电影/导演/名人/品牌/工作室（命中只 WARN，提示替换为中性描述）
DEFAULT_COMPLIANCE_WARN = [
    "诺兰", "昆汀", "斯皮尔伯格", "漫威", "迪士尼", "DC", "吉卜力",
    "宫崎骏", "今敏", "蒂姆波顿", "周杰伦",
]
# 场景人口软告警（闸8兜底，默认开、不阻断）：公共/营业场景关键词命中、但分镜没写背景人群词
# → WARN 提示"是否该有背景群像、别让空场景图生成无人画面"。语义判断仍靠 LLM 闸8，这里只是确定性兜底。
SCENE_PUBLIC_RE = re.compile(
    r"教室|餐厅|饭店|食堂|商场|超市|站台|车站|机场|候机|大厅|宴会|舞池|"
    r"广场|市集|集市|街道|马路|商业街|地铁|公交|课堂|会场|看台|观众席|酒吧|咖啡馆|大堂"
)
SCENE_CROWD_RE = re.compile(
    # ① 有人：群像/各类人群身份词
    r"群像|群众|人群|人流|背景.{0,4}(?:人|学生|同学|旅客|乘客|食客|顾客|宾客|路人|观众)|"
    r"同学|学生|旅客|乘客|食客|顾客|宾客|路人|围观|人来人往|熙攘|攒动|"
    # ② 明确无人/空：各种"空场景"表达
    r"空无一人|无人物|空镜|空荡|空教室|没有人|无人|"
    r"空着|半空|大半.{0,3}空|只剩|翻上桌|空出|空了|驶离|散去|散场|放学后|打烊|歇业|清晨无人|寂静无人"
)


class Report:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.fails = 0

    def add(self, status: str, message: str) -> None:
        self.lines.append(f"[{status}] {message}")
        if status == "FAIL":
            self.fails += 1

    def ok(self, m: str) -> None:
        self.add("PASS", m)

    def fail(self, m: str) -> None:
        self.add("FAIL", m)

    def warn(self, m: str) -> None:
        self.add("WARN", m)

    def info(self, m: str) -> None:
        self.add("INFO", m)


def ref_nums(block: str, label: str, *aliases: str) -> list[int]:
    names = [re.escape(label), *(re.escape(a) for a in aliases)]
    pat = r"@(?:" + "|".join(names) + r")\s*(\d+)"
    return [int(x) for x in re.findall(pat, block, re.I)]


def check_task_refs(r: Report, idx: int, block: str, label: str, *aliases: str) -> list[int]:
    """逐任务：@{label}N 必须从 1 连续。返回去重排序后的编号。"""
    found = sorted(set(ref_nums(block, label, *aliases)))
    if found and found != list(range(1, max(found) + 1)):
        r.fail(f"任务{idx} @{label}N 引用不连续：{found}（须从 1 起、不跳号）。")
    return found


def segment_shots(block: str, shot_matches: list[re.Match]) -> list[tuple[int, str]]:
    """把任务正文按分镜切成 (分镜号, 该分镜文本) 段。"""
    segs: list[tuple[int, str]] = []
    for i, m in enumerate(shot_matches):
        start = m.start()
        end = shot_matches[i + 1].start() if i + 1 < len(shot_matches) else len(block)
        segs.append((int(m.group(1)), block[start:end]))
    return segs


def validate(text: str, args: argparse.Namespace) -> Report:
    r = Report()
    if not text.strip():
        r.fail("文件为空。")
        return r
    r.ok("文件非空。")

    if re.search(r"生成一个由以下\s*\d+\s*个分镜组成的视频[。\.]", text):
        r.fail("黄金结构表头用了句号；『…组成的视频』后必须是冒号『：』。")

    headers = list(HEADER_RE.finditer(text))
    n_tasks = len(headers)
    if not headers:
        r.fail("缺官方表头：生成一个由以下N个分镜组成的视频：")
        _check_globals(r, text, args)
        return r

    total_shots = 0
    for idx, header in enumerate(headers, 1):
        end = headers[idx].start() if idx < len(headers) else len(text)
        block = text[header.end():end]
        declared = int(header.group(1))

        if header.group("punc") in ("：", ":"):
            r.ok(f"任务{idx} 表头用冒号。")
        else:
            r.fail(f"任务{idx} 表头未用冒号。")

        if DECIMAL_TIME_RE.search(block):
            r.fail(f"任务{idx} 出现小数时间段（须整数，如 0-3s）。")

        shot_matches = list(SHOT_RE.finditer(block))
        shots = [(int(m.group(1)), int(m.group(2)), int(m.group(3))) for m in shot_matches]
        total_shots += len(shots)

        if len(shots) == declared:
            r.ok(f"任务{idx} 分镜数 {len(shots)} = 声明 {declared}。")
        else:
            r.fail(f"任务{idx} 分镜数 {len(shots)} ≠ 声明 {declared}。")

        nums = [s[0] for s in shots]
        if nums and nums != list(range(1, len(shots) + 1)):
            r.fail(f"任务{idx} 分镜编号不连续：{nums}。")

        if shots:
            if shots[0][1] != 0:
                r.fail(f"任务{idx} 第一个分镜未从 0s 开始（实为 {shots[0][1]}s）。")
            bad = [f"{a}-{b}s" for _, a, b in shots if a >= b]
            if bad:
                r.fail(f"任务{idx} 存在非法区间（起≥止）：{', '.join(bad)}。")
            gaps = []
            for i in range(1, len(shots)):
                prev_end, cur_start = shots[i - 1][2], shots[i][1]
                if cur_start != prev_end:
                    gaps.append(f"分镜{shots[i-1][0]}止{prev_end}s≠分镜{shots[i][0]}起{cur_start}s")
            if gaps:
                r.fail(f"任务{idx} 时间段不连贯（相邻须首尾相接）：{'; '.join(gaps)}。")
            else:
                r.ok(f"任务{idx} 时间段连贯（0s 起、首尾相接）。")
            duration = shots[-1][2] - shots[0][1]
            # 默认上限 10s：用户实测即梦超 10s 易崩坏，由官方 15s 收紧（2026-06-11），勿改默认值；
            # 仅当用户明示冒险跑原生长段时才传 --max-duration 15（平台上限）
            cap = args.max_duration
            if 4 <= duration <= cap:
                r.ok(f"任务{idx} 总时长 {duration}s ∈ [4,{cap}]。")
            else:
                r.fail(f"任务{idx} 总时长 {duration}s 超出 [4,{cap}]。")

        # 逐任务引用连续性
        imgs = check_task_refs(r, idx, block, "图片", "image", "img")
        check_task_refs(r, idx, block, "视频", "video")
        check_task_refs(r, idx, block, "音频", "audio")
        if imgs:
            r.ok(f"任务{idx} @图片N 连续：1-{max(imgs)}。")

        # 逐分镜：镜头五段字段 + 台词紧邻音色 + 场景嵌入 + 代称检查
        for snum, seg in segment_shots(block, shot_matches):
            if "镜头：" not in seg and "镜头:" not in seg:
                r.fail(f"任务{idx} 分镜{snum} 缺『镜头：』五段字段。")
            # 邻接校验：每句完整台词 …说：「…」 的『」』后必须紧跟『音色：』（允许空白）
            dialogs = list(DIALOG_RE.finditer(seg))
            for d in dialogs:
                if not re.match(r"\s*音色\s*[:：]", seg[d.end():]):
                    snippet = d.group(0)[:24]
                    r.fail(
                        f"任务{idx} 分镜{snum} 台词『{snippet}…』后未紧跟『音色：』"
                        f"（音色必须紧邻台词，不能隔开或集中写在段尾）。"
                    )
            # 兜底：有 说：「 起始但没闭合 」 的畸形台词
            if len(LINE_RE.findall(seg)) > len(dialogs):
                r.fail(f"任务{idx} 分镜{snum} 存在未闭合的台词引号『…说：「』缺『」』。")
            seg_imgs = ref_nums(seg, "图片", "image", "img")
            if not seg_imgs:
                r.warn(f"任务{idx} 分镜{snum} 未含任何 @图片N 引用，确认是否漏嵌素材/场景。")
            # 场景嵌入：--scene-image 可声明多个场景图编号（跨场景 Clip），任一命中即过
            if args.scene_image and not (set(args.scene_image) & set(seg_imgs)):
                declared = "/".join(f"@图片{n}" for n in args.scene_image)
                r.fail(
                    f"任务{idx} 分镜{snum} 未显式嵌入场景图（声明的场景图：{declared}）"
                    f"（8-A：每个分镜正文必须含场景引用，禁靠上下文隐含，防场景漂移）。"
                )
            # 代称：剔除「」内台词后扫描；默认 WARN，--fail-pronouns 升级 FAIL
            narration = QUOTE_RE.sub("「」", seg)
            for p in sorted(set(PRONOUN_RE.findall(narration))):
                msg = f"任务{idx} 分镜{snum} 叙述正文出现代称『{p}』，应改为角色全名。"
                if args.fail_pronouns:
                    r.fail(msg)
                else:
                    r.warn(msg + "（--fail-pronouns 可升级为 FAIL）")
            # 场景人口软告警（闸8兜底）：命中公共场景词但没写人群/空镜词 → WARN 人工复核
            # 先把"下一个 Clip 的标题/参考素材行尾巴"切掉（末分镜段会延伸到下一表头，含下一 Clip 标题），避免误报
            seg_body = re.split(r"\n\s*(?:##\s|\*\*参考素材|生成一个由以下)", seg)[0]
            if args.scene_population and SCENE_PUBLIC_RE.search(seg_body) and not SCENE_CROWD_RE.search(seg_body):
                hit = SCENE_PUBLIC_RE.search(seg_body).group(0)
                r.warn(
                    f"任务{idx} 分镜{snum} 提到公共场景『{hit}』却未写背景人群/空镜状态，"
                    f"请确认是否该有背景群像（闸8：空场景图会生成无人画面，如上课教室生成空教室）。"
                )

    # 任务数 / 分镜总数断言
    if args.expected_tasks is not None:
        if n_tasks == args.expected_tasks:
            r.ok(f"生成任务数 {n_tasks} = 预期 {args.expected_tasks}。")
        else:
            r.fail(f"生成任务数 {n_tasks} ≠ 预期 {args.expected_tasks}。")
    if args.expected_shots is not None:
        if total_shots == args.expected_shots:
            r.ok(f"分镜总数 {total_shots} = 预期 {args.expected_shots}。")
        else:
            r.fail(f"分镜总数 {total_shots} ≠ 预期 {args.expected_shots}。")

    # 引用数量断言（仅单任务时精确断言；多任务只做上面的逐任务连续性）
    if n_tasks == 1:
        block = text[headers[0].end():]
        _assert_ref_count(r, block, args.ref_images, "图片", "image", "img")
        _assert_ref_count(r, block, args.ref_videos, "视频", "video")
        _assert_ref_count(r, block, args.ref_audios, "音频", "audio")
    else:
        if any(v is not None for v in (args.ref_images, args.ref_videos, args.ref_audios)):
            r.info("多任务：--ref-images/videos/audios 数量断言已跳过（仅做逐任务连续性校验）。")

    _check_globals(r, text, args)
    return r


def _assert_ref_count(r: Report, block: str, expected: int | None, label: str, *aliases: str) -> None:
    if expected is None:
        return
    found = sorted(set(ref_nums(block, label, *aliases)))
    if expected == 0:
        if found:
            r.fail(f"预期无 @{label}N，实际 {found}。")
        else:
            r.ok(f"无 @{label}N，符合预期。")
        return
    if found == list(range(1, expected + 1)):
        r.ok(f"@{label}N 匹配预期 1-{expected}。")
    else:
        r.fail(f"@{label}N 预期 1-{expected}，实际 {found}。")


def _check_globals(r: Report, text: str, args: argparse.Namespace) -> None:
    has_global = (
        ("禁止生成任何台词/旁白字幕" in text
         or ("生成清晰可读的文字" in text and "文字内容严格匹配原文" in text))
        and "禁止生成背景音乐" in text
    )
    if has_global:
        r.ok("末尾全局要求段存在。")
    else:
        r.fail("缺末尾全局要求段（禁字幕+禁BGM 或 要文字+禁BGM）。")

    if args.language_rule:
        if re.search(r"语言\s*[:：]\s*\S+", text):
            r.ok("语言规则存在。")
        else:
            r.fail("缺语言规则（如 语言：中文。）。")

    if args.subject_required:
        if re.search(r"<subject>[^<]+</subject>", text):
            r.ok("<subject> 主体标签存在。")
        else:
            r.fail("缺要求的 <subject>主体名</subject>。")

    if args.negative_required:
        if re.search(r"NEGATIVE\s*[:：]|负向|禁止画面崩坏|禁止人物穿帮", text, re.I):
            r.ok("负向词段存在。")
        else:
            r.fail("缺要求的负向词段。")

    if args.require_storyboard_artifact_guard:
        check_storyboard_artifact_guard(r, text)

    for term in args.banned_term:
        if term.lower() in text.lower():
            r.fail(f"命中禁用词：{term}")

    for term in DEFAULT_COMPLIANCE_WARN:
        if term in text:
            r.warn(f"疑似电影/导演/名人/品牌名『{term}』，8-A 要求替换为中性描述。")


def check_storyboard_artifact_guard(r: Report, text: str) -> None:
    """Phase8.5：上传故事板/分镜宫格图时，正文须有引用 + 规划限定 + artifact 排除。"""
    if STORYBOARD_REF_RE.search(text):
        r.ok("故事板/分镜宫格引用存在。")
    else:
        r.fail("缺 Phase8.5 故事板/分镜宫格守卫所需的宫格引用（如『片段分镜宫格图@图片N』）。")

    if STORYBOARD_PLANNING_RE.search(text) and STORYBOARD_PLANNING_SCOPE_RE.search(text):
        r.ok("宫格已限定为镜头顺序/构图/动作调度等规划用途。")
    else:
        r.fail(
            "宫格引用未明确限定为构图/调度规划用途；"
            "需补『仅用于镜头顺序、构图、动作调度…』或 'ONLY as motion planning reference' 等措辞。"
        )

    lower_text = text.lower()
    for label, terms in STORYBOARD_ARTIFACT_GROUPS:
        if any(term.lower() in lower_text for term in terms):
            r.ok(f"artifact 排除含『{label}』。")
        else:
            r.fail(f"artifact 排除缺『{label}』（须禁止把宫格的{label}渲进成片）。")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="校验即梦 8-A 视频生成 Prompt 集")
    p.add_argument("prompt_file")
    p.add_argument("--expected-tasks", type=int, help="预期生成任务/表头数")
    p.add_argument("--expected-shots", type=int, help="预期分镜行总数")
    p.add_argument("--ref-images", type=int)
    p.add_argument("--ref-videos", type=int)
    p.add_argument("--ref-audios", type=int)
    p.add_argument(
        "--scene-image", type=int, action="append", default=None,
        help="场景图编号，可重复传多个（跨场景 Clip）；每个分镜正文必须含任一声明的 @图片{N}（防场景漂移）",
    )
    p.add_argument("--fail-pronouns", action="store_true", help="叙述正文代称从 WARN 升级为 FAIL（已剔除「」内台词）")
    p.add_argument("--max-duration", type=int, default=10,
                   help="任务总时长上限秒（默认10=实测质量线；用户明示冒险原生长段时才设15=平台上限）")
    p.add_argument("--scene-population", action="store_true", default=True,
                   help="闸8场景人口软告警（默认开）：公共场景词命中却没写人群/空镜 → WARN，防空场景图生成无人画面")
    p.add_argument("--no-scene-population", dest="scene_population", action="store_false")
    p.add_argument("--language-rule", action="store_true", default=True)
    p.add_argument("--no-language-rule", dest="language_rule", action="store_false")
    p.add_argument("--negative-required", action="store_true")
    p.add_argument("--require-storyboard-artifact-guard", action="store_true",
                   help="Phase8.5：上传故事板/分镜宫格图时，校验正文有宫格引用+规划限定+artifact排除，缺则 FAIL")
    p.add_argument("--subject-required", action="store_true")
    p.add_argument("--banned-term", action="append", default=[])
    args = p.parse_args(argv)

    path = Path(args.prompt_file)
    if not path.exists():
        print(f"[FAIL] 文件不存在：{path}")
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
