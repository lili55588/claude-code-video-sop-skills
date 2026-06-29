# 机读校验契约 + 确定性校验器（Phase8 兜底闸）

> 自检闸（`self-check-gates.md`）是「LLM 自己跑的清单」；这一层是**确定性脚本**，对 Phase8 产物 `{项目名}_视频生成Prompt集.md` 做机检兜底。两层都过才算交付。移植自 Codex 版并修了它的 4 个 P0（连贯性/逐任务引用/任务·分镜计数语义/镜头·音色检查）。

## 校验器位置与用法
脚本：`scripts/validate_phase8_prompt.py`。回报 Phase8「已完成」前必须跑、且 `RESULT: PASS`。

```powershell
python {SKILL_ROOT}/scripts/validate_phase8_prompt.py "{ARCHIVE_ROOT}{项目名}\{项目名}_视频生成Prompt集.md" --expected-tasks 1 --expected-shots 3 --ref-images 3 --scene-image 1
```

**Phase8.5 上传宫格后重跑**（该 Clip 加了故事板/分镜宫格图引用时）：
```powershell
python {SKILL_ROOT}/scripts/validate_phase8_prompt.py "{ARCHIVE_ROOT}{项目名}\{项目名}_视频生成Prompt集.md" --expected-tasks 1 --expected-shots 3 --scene-image 1 --require-storyboard-artifact-guard
```

参数：
- `--expected-tasks N`：预期**生成任务/表头数**（`生成一个由以下N个分镜组成的视频：` 的条数）。≤10s 应为 1。
- `--expected-shots N`：预期**分镜行总数**（所有任务的 `分镜k：a-bs` 行数之和）。
- `--ref-images/--ref-videos/--ref-audios N`：单任务时精确断言 `@图片/视频/音频N` = 1..N；多任务时自动跳过数量断言，只逐任务校验连续性。
- `--scene-image N`：声明哪张 `@图片N` 是场景图；脚本逐分镜检查**每个分镜正文都含声明的场景图引用**，漏则 FAIL（目标平台官方必填：每个分镜必须显式嵌场景引用、禁靠上下文隐含，防场景漂移）。**可重复传多个**（跨场景 Clip：`--scene-image 1 --scene-image 2`，分镜含任一声明编号即过；"各分镜嵌的是否为自己所在场景"由 LLM 闸 7 语义复核）。强烈建议每次 Phase8 都带上。
- `--fail-pronouns`：叙述正文代称（他/她/它/这个人/那个人/女主/男主/两人…，**含通用名词 女孩/男孩/女人/男人/老人/小孩**——正文必须写全名）从默认 WARN 升级为 FAIL；扫描前已剔除 `「」` 内台词，台词里的"他来了"不会误杀；"其他/吉他/维他命/其它"等已做前置排除。
- `--max-duration N`：任务总时长上限秒（**默认 10**=用户实测质量线，勿改默认）；仅当用户明确要求冒险跑原生长段时设 `15`（平台上限），并在交付时明示质量风险。
- `--scene-population`：**闸 8 场景人口软告警（默认开启）**。命中公共/营业场景词（教室/餐厅/站台/街道/宴会…）但该分镜没写背景人群词或空场景词 → WARN 提示人工复核（防"空场景图生成无人画面"，如上课教室生成空教室）。**不阻断**（WARN 非 FAIL，语义判断仍靠 LLM 闸 8）；`--no-scene-population` 关闭。每个分镜按素材清单 `场景人口` 字段写明人数即可消告警。
- `--subject-required`：要求出现 `<subject>主体名</subject>`（有用户参考主体时加）。
- `--negative-required`：要求出现负向词段（项目启用负向词时加）。
- `--require-storyboard-artifact-guard`：**Phase8.5 专用**。当该 Clip 上传了故事板/分镜宫格图时加，机检正文 ① 含宫格引用（`片段分镜宫格图@图片N`/`@故事板`/`STORYBOARD GRID @图片N` 等）② 已把宫格限定为"仅供镜头顺序/构图/动作调度等规划用途" ③ 逐组排除 artifact 渲染（边框/编号/文字标签标题/箭头/时间标注/网格线/UI/水印/logo），缺任一即 FAIL。详见 `phase8-5-keyframe-anchors.md`。
- `--no-language-rule`：关闭「语言：…」必需（默认开启）。
- `--banned-term X`：追加禁用词（可多次）；脚本另内置电影/导演/名人/品牌默认软告警。
- `--forbid-performance-internal-labels`：**表演引擎专用**（详见 `performance-engine.md` §3/§8）。Phase8 正文残留发动机**内部标签**则 FAIL——**只抓明确「字段名+冒号」标签/模板残留**：`objective:`/`obstacle:`/`tactic:`/`subtext:`/`voice trigger A|B|C:`/`表演目标：`/`表演等级：`/`剧本依据：`/`潜台词：`/`转折触发：`/`三力配方：`。**不抓普通词**（目标/障碍/策略/结束状态/权力关系——都是合法镜头/剧情正文词，"视线目标"不误伤；实测"结束状态"曾误伤已剔除）。**边界（不可伪装成正则已证）**：P2 是否真对应剧本 beat、等级是否匹配、声音事件数量、字段是否真追溯剧本——这些**语义项仍由 LLM 跨 Phase 自检承担**，本参数只机检"明确标签残留"，**不能只写 validator PASS 当作表演验收已覆盖**。**引号内确认台词不参与扫描**（检查前先 `QUOTE_RE.sub("「」", text)` 剔除「」台词再查正文——Phase8 禁改台词原文，台词里出现"潜台词："等字不得误杀）。回归：内部标签反例被抓、合法"视线目标"与普通"障碍：/策略：/结束状态："不误报、引号内确认台词不误杀、现有 Prompt 集 PASS。

## 脚本会判 FAIL 的项（机检，全确定性）
1. 表头用冒号非句号；表头数与分镜数声明一致；分镜编号 1..N 连续。
2. **整数时间段**（小数即 FAIL）；首段从 0s 起；**相邻段首尾相接**（无间隙、无重叠）；任务总时长 ∈ [4,10]s（用户实测覆写：官方 15s，目标平台超 10s 易崩坏，已收紧）。
3. **逐任务** `@图片N/@视频N/@音频N` 从 1 连续、不跳号（支持多任务各自从 @图片1 重启）。
4. 每个分镜含 `镜头：` 五段字段；**每句完整台词 `…说：「…」` 的 `」` 后必须紧邻 `音色：`（邻接校验，非段内计数——台词与音色被隔开、或音色集中写在段尾都会 FAIL）**；未闭合的台词引号 FAIL；**（带 `--scene-image` 时）每个分镜正文都含声明的场景图引用（多值任一命中）**。
5. 末尾全局要求段（禁字幕+禁BGM 或 要文字+禁BGM）；语言规则（默认必需）；按需 `<subject>`/负向词；命中禁用词。

WARN（不阻断，提示人工复核）：疑似代称（女主/男主/两人/那个人/对方…）、疑似电影/导演/名人/品牌名、**闸 8 场景人口**（公共场景词命中却没写人群/空镜状态，默认开、`--no-scene-population` 关）。

## 机读契约（任务包/项目里用）
在产物或任务包顶部嵌一行 HTML 注释，供上游流水线解析：
```text
<!-- VALIDATE {"jimeng_video_prompt":true,"tasks":1,"shots":3,"ref_images":3,"ref_videos":0,"ref_audios":0,"scene_image":1,"language_rule":true} -->
```
字段：`jimeng_video_prompt` 启用 8-A 模板检查；`tasks` 生成任务数；`shots` 分镜总数；`ref_images/videos/audios` 引用数（单任务精确、多任务连续性）；`scene_image` 场景图编号（int 或数组——跨场景 Clip 用数组如 `[1,2]`，每分镜须含任一，映射为重复传 `--scene-image`）；`fail_pronouns` 代称升级 FAIL；`scene_population` 闸8场景人口软告警（默认 true，设 false 映射 `--no-scene-population`）；`language_rule` 要求 `语言：…`；`negative_required` 要求负向词段；`require_storyboard_artifact_guard` Phase8.5 上传宫格时映射 `--require-storyboard-artifact-guard`；`subject_required` 要求 `<subject>`；`banned_terms` 禁用词数组；`forbid_performance_internal_labels` 表演引擎：Phase8 正文残留内部标签则 FAIL（映射 `--forbid-performance-internal-labels`）。
> 对接项目级 `validate_output.py` 时，把上述字段映射为对应命令行参数即可；本脚本可独立运行，不依赖任何外部项目。

## 与自检闸的分工
- 机检兜底（本脚本）：覆盖 闸3（覆盖/编号）、闸4（时长/连贯）、闸5（引用连续）、闸7（结构/镜头/音色/**场景嵌入**/语言/合规）里**能正则确定**的部分；**闸8 场景人口**做关键词级软告警（确定性兜底）。
- 仍靠 LLM 自检（`self-check-gates.md`）：闸1 阶段前置、闸2 素材完整性、闸6 跨 Clip 连贯性、**闸8 该不该有人的语义判断**（教室该有人 vs 私人书房该空——正则只提示、判断靠人），以及闸5/闸7 里需要语义判断的部分（如代称是否真错、场景名是否与清单一致、事实无损翻译）。
