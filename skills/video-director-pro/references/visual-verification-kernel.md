# 视觉验收内核（VVK）— 闸2b / 闸9 / 闸10 共用

> 把「**确定性摆证据 + 视觉主判 + 对抗盲审 + 反糊弄 + 锚定 + 返修决策**」抽成共用内核。三个视觉闸——**闸2b(P7 素材图) / 闸9(P8.5 关键帧·宫格) / 闸10(P9 成片)**——都挂本内核，各自只定制 **Part A 工具 + 检查矩阵**。
> **为什么**：早失败便宜。P7 一张错字/跑脸的图，会污染下游每个引用它的宫格(P8.5)和成片(P9)；在 P7 重抽一张图，比 P9 重抽整段视频便宜几个数量级。把严苛度往上游搬，挡在源头。

## 0 · 三层架构（与闸10 同构）
- **Part A 确定性证据**（永不判分，只摆证据）
- **Part B 视觉主判**
- **Part C 对抗性独立盲审**（高风险素材必做）

## 1 · 前置完整性闸
文件存在 / 可读 / **来源链清楚**（对得上哪个 Phase 规格）→ 否则 `AUDIT_INCOMPLETE`：修证据/补文件/重导，**不改图、不重生成**。

## 2 · Part A 确定性证据（issue-class 分类，**状态只用四态**）
> **别另起平行状态**：原因用 `issue_class` 标，状态仍是 `AUDIT_INCOMPLETE` 或 `FAIL_BLOCKED`（与 Codex 树对齐）。
- **`EVIDENCE_GAP` → 状态 `AUDIT_INCOMPLETE`**：文件缺/不可读/打不开/来源链不清/映射缺 → 修证据，不改图、不重生成。
- **`TECH_SPEC_BLOCKED` → 状态 `FAIL_BLOCKED`**：文件可读但分辨率/比例/格式/板式不符 → **容器层先**（重导/裁切/补标准版）；裁切会损主体/道具/文字/构图才升重生成。**报为 `FAIL_BLOCKED + issue_class=TECH_SPEC_BLOCKED`，不是视觉内容失败。**
- **`CONTENT_FAIL` → 状态 `FAIL_BLOCKED`**：烤进画面的内容错（跑脸/手崩/关键文字错/场景有人/变体越改/多视角不一致）→ 重生成 + 责任分流。
- **软信号 → 风险证据，需视觉确认才升级，不自动判死**：OCR、人脸数、水印、宫格分割、感知哈希/嵌入（图片版 `scdet/ffprobe` 同类，但更模糊，不当硬判官）。

**软信号使用规则**
- **OCR 按文字关键性分流**：素材清单标「需一字不差」的文字（产品名/logo/招牌/剧情关键字）→ **二钥规则**（要求一字不差 + OCR 高置信判错 + 视觉复核确认）→ 内容 `FAIL_BLOCKED` → 重生成/精修；**incidental**（水印/AI 乱码/无关说明字）且可无损去除 → 技术/局部 → 裁/遮。
- **人脸数**：空镜场景板应 0 脸（检出→风险，视觉确认）；角色主视图应 1 脸。侧脸/背影/插画风易漏检 → 只作信号。
- **感知哈希/嵌入 = 图片版差分**：**角度感知**，别 naive 比「正脸 vs 背影」（本就该差异大≠跑脸）；只对**有脸视图**用人脸嵌入比，或比**发型/服装区域**。
- 检测产出的 **bbox 可自动填进「返修区域」**字段。

**第二批工具契约（`image_asset_audit.py` v0.2 已落地 2026-06-18，与 Codex 树「Second-batch tool contract」对齐）**
- 软信号槽位仅在引擎可用时填，**永不改 `part_a_status`**；升级仍须 Part B 视觉确认。
- **感知哈希＝已接**：region/panel 域 `dhash`（full / center_80 / 宫格各格），`--ref-image` 比权威参考出 distance + review_hint（`REVIEW_DIFFERENCE`/`NEAR_MATCH_SIGNAL`），供重复/漂移/导错图/宫格逐格差分；**禁 naive 整图当身份/角度/内容判据**，工具自带 `angle_awareness=无人脸/人体嵌入` 免责；人脸/人体嵌入比对仍未接。
- **OCR＝可选**：`--expect-text must-match:/incidental:` 接 P4 `exact_text+criticality`，走二钥（must-match + OCR 高置信不符 + 视觉确认才升 CONTENT_FAIL）；依赖 `pytesseract`+原生 Tesseract，缺则降级 `NOT_AVAILABLE`、工具照跑；无上游 exact-text 契约时 OCR 仅原始证据。
- **水印＝OCR 派生**：角区 + 关键词启发式（`--watermark-keyword` 可补，默认含 dreamina/jimeng/目标平台/pippit 等），非独立引擎；视觉确认前按 incidental/局部修候选。
- **人脸＝推迟**：恒 `NOT_AVAILABLE`，除非项目反复需确定性人数；将来接也只报 count/bbox/遮挡过小/盲点，不做身份识别。

## 3 · Part B 视觉主判 + 反糊弄协议
默认存疑；PASS 也要写正证据；怀疑项先穷举；二元勾选不写散文；看不清只降级（`ACCEPTABLE_RISK`/待复看），不默认 PASS。

## 4 · Part C 对抗性独立盲审
高风险素材必做（主角身份 / 产品文字 / 核心场景 / 多视角 / 关键帧宫格）：派独立子代理盲审，**不给看主判结论**，死磕身份/文字/站位/道具/方向/连续；分歧逐项取更严判定。
> ⚠ 对抗复审有**共享模型盲点**（见闸10：背对窗误判）——轴外/身后的视线目标、几何关系类问题，人工抽查不能省。

## 5 · 参照锚定法 + 权威锚定链
- **锚定法**：锚**权威参考/布局**再判一致/漂移，不靠「看着行」。多视角锚**主视图**；场景格锚**声明布局**；变体锚**基底**；关键帧身份锚 **P7 角色图（非上一帧）**；成片用参照物锚定法。
- **权威锚定链**：`P4素材清单 → P7参考图 → P8.5关键帧 → P8 Prompt → P9成片`。
- **依赖记录**：每个素材记一份**下游引用清单**（扫 Prompt 集/锚点包得「R03 被 Clip2/5/8 + 宫格 G2 引用」），让 cascade 复检**机械可算、不靠猜**。

## 6 · 锁定状态（下游可否引用，映射既有四态）
- `LOCKED_PASS`（=PASS/REGENERATED_PASS）：可作权威参考、被下游引用。
- `LOCKED_WITH_RISK`（=ACCEPTED_WITH_RISK）：可引用，但**命名风险必须注入下游审片项**（用它的每个下游强制单查该风险有没有发作/恶化）。
- `REJECTED`（=FAIL_BLOCKED，修好前）：**禁止下游引用**。
- `AUDIT_INCOMPLETE`：证据不足，**禁止放行**。
> 铁律：**只有锁定（PASS/带风险）的素材才能成为下游 P8.5/P9 参考**；REJECTED/INCOMPLETE 不得被引用。

## 7 · 返修决策层（图片版）+ cascade
**顺序**：先修证据 → 再修技术规格 → 再局部 → 再重生成 → 最后才回退上游。
- **无「trim 时间码」**（图不能裁时间）→ 改写**返修区域坐标**（命名区 `左上角水印区`/`角色右手区`/`产品瓶身文字区` + 可选 bbox，Part A 检测可自动填）。
- **局部坏** → 换抽卡候选 / 弃用非承重变体。
- **容器层**（技术规格 / incidental 文字水印）→ 重导/裁/遮，不伤主体。
- **内容错** → 改 Prompt 重生成，**责任分流**：Prompt 含糊→改 P7｜抽崩→图生图重抽加固参考绑定｜漏登记/缺状态变体→回 P4｜blocking 缺→回 P5。
- **重试预算 K**（同闸10）：同 Prompt 重抽 ≤2 → Prompt 修版 ≤2 → 升级回 P5 重拆/拆任务。
- **闭环**：改完**重跑本闸** + **沿锚定链 cascade 复检所有下游引用**（改一张 P7 图 → 重审引用它的宫格/Clip/成片）。

**报告「返修决策」字段**（三轴：状态 / issue_class / 严重度，与 Codex 树一致）：位置/问题 · **状态**(AUDIT_INCOMPLETE/PASS/REGENERATED_PASS/ACCEPTED_WITH_RISK/FAIL_BLOCKED) · **issue_class**(EVIDENCE_GAP/TECH_SPEC_BLOCKED/CONTENT_FAIL/ACCEPTABLE_RISK) · **严重度**(BLOCKER/EDIT_FIX/REGEN_REQUIRED/ACCEPTABLE_RISK) · 是否承重 · 是否允许局部修 · 返修区域(命名区+bbox) · 下游引用受影响 · 首选+备用处理 · 最小回退层级(P9/P8/P8.5/P7/P5/P4) · Prompt 修正方向 · 重试预算 · 修后复检范围(含 cascade 下游清单) · 锁定状态。

## 8 · 三闸适配器（同内核，各定制 Part A + 矩阵）

| 闸 | 阶段·对象 | Part A（硬/软） | 检查矩阵重点 | 锚定 |
|---|---|---|---|---|
| **2b** | P7 角色/多视角/状态变体/场景/道具/产品图 | 硬:分辨率·比例·文件 / 软:OCR·人脸数·水印·哈希(角度感知) | 同一人·五官手不崩·多视角不跑脸·**关键文字logo一字不差**·场景空镜·道具状态·变体只改声明点 | 多视角锚主视图·场景锚布局·变体锚基底 |
| **9** | P8.5 首帧/关键帧/结束帧/宫格/锚点包 | 硬:分辨率 / 软:编号·边框·箭头·宫格分割·**标记残留(框/箭头/圈/标签)** | 对应分镜·站位(blocking map)·道具位置(prop map)·朝向视线手部·逐帧连贯·越轴·**宫格本机拼非AI重绘·每格独立原图·artifact不进成片·上一帧不当身份源**·**标记式两阶段证据链(机位反推标记原点/支撑点/身体朝向箭头/标记彻底清除)** | 身份锚P7·站位锚场景图·**机位锚 Stage1 标记底图** |
| **10** | P9 成片 | （已建）ffprobe·全帧·scdet差分·分镜锚定 | （已建）朝向/站位/道具/跨镜/身份/人口·参照物锚定法 | 参照物锚定法 |

## 边界
- 工具只摆证据、不判分；**软信号不判死**；不 AI 重绘任何图/帧（本机像素）。
- 不碰目标平台上传规则、不碰小云雀 / Pippit 提交规则。
- 闸10 的 Part A 工具是两树共享 `tools\video-frame-audit\frame_audit.py`；**闸2b/9 的图片 Part A 工具是两树共享 `tools\image-asset-audit\image_asset_audit.py`（已建：`--profile phase7/phase8.5/direct-image`、`--expected-ratio/width/height`、`--grid ROWSxCOLS`；产 file/尺寸/比例/格式/板式证据 + `overall_part_a_status`，输出仍需 Part B 视觉判定；v0.2 已接第二批软信号——感知哈希(region/panel dhash + --ref-image)、OCR(--expect-text/--watermark-keyword，依赖 pytesseract+Tesseract、缺则降级)、水印(OCR 派生)已落地，人脸仍 deferred；软信号永不改 `part_a_status`，详 §2「第二批工具契约」）。**
