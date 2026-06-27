# X-Tech 高级控制模块：OAK × Koda（外接·默认不执行·自动评估）

> **定位**：video-sop 的**外接高级导演控制技法包**，源自 X 平台 OAK(@_OAK200) 与 Koda(@aimikoda) 的 Seedance 提示词技法。它**不替代**主流程——video-sop 管项目流程/10s 上限/验证/交付；本模块管**高级表演发现、构图探索、storyboard/triptych 控制、infer-between 质感生成**。两者通过 **Clip 级 Route + Reference Authority Contract** 对接。
> **默认不执行、但自动评估**：本模块不默认改写主流程；但 **Phase5/Phase8 有常开轻量候选探针**自动评估每个 Clip 适不适合 X-Tech（**哪怕只给一句灵感**，不需用户记术语）。**命中候选、或用户点名触发词**时才加载本文件、提议具体 Route，**用户确认才执行、绝不静默改路线**；全是普通事实驱动项目则默认纯 video-sop。**唯一常开增量**：Reference Authority Contract（已进 Phase8 core，轻量）。
> **真相源**：本文件是 X-Tech 模块的单一真相源；SKILL.md 只放 router 入口。原始 prompt 全文不搬进来，外部 source pack 见 §10。

触发词：`X技巧 / OAK / Koda / aimikoda / triptych / 三联画 / audition / 试镜 / Character Identity Board / Director Strip / storyboard blueprint / FACS / IPA / Laban / Seedance 原生 15s / infer-between / 脑补生成`。

---

## 1 · 最高铁律（违反即不合格）

1. **原文保护**：OAK/Koda 高级 prompt 本身是资产，不做低配改写。本模块只决定**何时用哪条**、做外层分层衔接；变量化只抽角色名/参考图/场景名/panel 数/shot beat 等显式变量，不动核心规则段（Project Card / Continuity Header / Scene Packet / Style Locks / Panel Rules / Director Strip / Beat / Casting Read / Acting Style / Triptych 分析）。裁剪版另存实验压缩版，不覆盖完整版。
2. **Clip 级分支，永不在单 prompt 内混写**：不要在同一条 video prompt 里既要求模型"自由推断三图之间的电影时间"（松/OAK），又要求"逐格照 storyboard 执行"（严/Koda）。分支粒度是 **clip**：一部片里事实驱动 Clip 走严控、质感 Clip 走 infer-between，各是独立一次生成，单 prompt 内永不混写。
3. **单一权威**：同一维度只能有一个权威（身份/结构/调度/look/表演）。多 reference 抢同一维度 = 抢权，必须用 §4 Reference Authority Contract 显式声明。
4. **10s 默认 / 15s 风险模式**：默认仍按 video-sop 全局铁律——单 Clip 4~10s（用户实测覆写，**不改回 15s**）。OAK/Koda 的 15s 仅作"原生 Seedance 上限 / 用户**显式要求**的风险模式"，校验器单独传 `--max-duration 15`，**默认值不动**。Koda 12 格/15s 默认要转成 8~10s 或拆分。

## 1.5 · 启用协议（两段闸·自动评估、不默认执行）

用户**不需要记术语、也不需要判断"该不该用 X-Tech"**——系统自动评估、提议，用户确认才执行：

1. **第一段·常开轻量探针**（钉在 `phase5-storyboard.md` 5.3 + `phase8-video-prompt.md` §一 核心，**不靠触发词**）：每个 Clip 标 6 类之一（与 Codex 根同串、便于 HANDOFF）——`FACT-DRIVEN`(默认严控 8-A、**不提**) / `TEXTURE-DRIVEN`(→Route B infer-between 候选) / `ONE-TAKE`(→Route C) / `STRICT-ACTION`(→Route D) / `AUDITION-CANDIDATE`(试镜/表演校准) / `NO-XTECH`(默认)；用户报"即梦太僵硬/动作不自然"也算候选信号。探针极轻、不加载全模块。门槛高，拿不准标 `NO-XTECH`。
2. **第二段·命中才加载 + 提议**：探针发现候选，才加载本文件，把所有候选 Clip **一次性**列给用户、各带一句理由 + 建议 Route（如"Clip3 质感驱动，建议 Route B infer-between：锁事实放权动作；要不要启用？"）。
3. **用户确认才执行**：点头才走该 Route；**绝不静默改路线**。拿不准 / 全是事实驱动就不提、默认严控。
4. 用户也可**直接点名触发词**主动启用（见模块顶部触发词）——那是第二条入口，不是唯一入口。

> 即：**不是"用户不说就不用"，而是"系统自动判断、但不会无说明地乱套"**。默认仍是纯 video-sop，X-Tech 只在命中条件的 Clip 上、经确认后启用。

---

## 2 · 控制旋钮 + Route A-F

顶层只有一个旋钮：**松（OAK，放权模型）↔ 严（Koda，逐格锁定）**。旋钮下挂 6 条具体路线：

| 路线 | 工具 | 用途 | 松/严 | 归属 |
|---|---|---|---|---|
| **A · OAK Audition / Self-tape** | 试镜/自拍 | 表演发现、独白、心理测试 | 松 | module（挂 `performance-engine.md` §7 self-tape）|
| **B · OAK Triptych infer-between** | 竖向三联画脑补生成 | 质感驱动 Clip（氛围/情绪流/一镜到底）| 松 | module·见 §5 |
| **C · Koda 4-panel same-lens master** | 4 格一镜到底 | 连续追逐/运动、镜头不剪 | 中 | module（Phase8.5 锚点）|
| **D · Koda 8/10/12-panel storyboard** | 多格分镜 | 武打/复杂动作/多 beat、逐格照搬 | 严 | **≈ core Phase8 8-A 已有** |
| **E · Koda direct shotlist text-to-video** | 角色 ref + 文字 shotlist，无分镜表 | 因果动作但不画分镜 | 中-严 | **≈ core Phase8 8-A 已有** |
| **F · Koda Extend continuous-take continuation** | 续接上一条 | 连续 take 延时（地点可在 take 内变化）| — | module·谨慎 |

- **选路线 = 先定松/严旋钮，再挑工具。** A/B 同属 OAK 松控但用途不同（A 发现表演、B 搭三联画短片结构·原生 15s 上限，**落地仍按 10s 默认**）；C-F 同属 Koda 但控制强度递增。
- **D/E 本就是 video-sop 默认 Phase8 8-A**（每分镜显式 shotlist + 逐分镜 `@图片N`），无需新增，只是把它纳入 Route 词表便于沟通。
- **Route F 硬规则**：Extend **不能与独立 Clip 批量并行**（Phase8 默认逐 Clip 并行提交）；它依赖 video1 先生成、**必须在该 Clip 输出存在后串行运行**。仅当"连续 take 连贯"比并行吞吐更重要时才用。非跨场景表演迁移（那走 §6 Route A 的 acting style）。
- **格数 = 控制强度**（非越多越好，由动作复杂度/因果密度/连贯需求决定）：3 格=松（triptych）、4 格=中（same-lens）、8~12 格=严；经验密度 ≈ 0.8 panel/秒（12 格/15s，落地按 10s 上限折算）。

---

## 3 · Clip 长度 = 连贯需求（不按固定网格切）

> **优先原则**：在 10s 上限内，动作 / 一镜到底**优先整条单次生成、不细分**；只有当控制模式切换（松↔严）、平台时长限制、或刻意情绪断点时才切 Clip。
> 不是绝对命令：这是"别把一条连贯动作切碎"，**不是"短动作也要凑满"**——6~8s 单动作镜头就该是 6~8s，长度跟动作自然时长走。

理由：一镜到底切碎=把要避免的剪辑点又加回去；动作的物理/动量/身份只有在单次生成里才连续；切条会每条从参考图重置身份与物理、接缝增漂移。情绪/独白/落点这类较静的 Clip 短一点反而更紧、才适合细分。

---

## 4 · Reference Authority Contract（与 Phase8 core 对接）

每条 Clip 进 Phase8 前先声明 5 权威，防身份图/storyboard/triptych/style prompt 抢同一维度（落点见 `phase8-video-prompt.md` 产物格式头）：
```
IDENTITY AUTHORITY:  谁控脸/体型/服装/比例（通常 <subject> 或角色 @图片N）
STRUCTURE AUTHORITY: Route A-F 哪个控 clip 结构
STAGING AUTHORITY:   谁控动作/blocking/camera path/screen direction
LOOK AUTHORITY:      谁控风格/灯光/色彩/媒介
ACTING AUTHORITY:    OAK acting style / performance-engine / 三本表演手册
```
- **不取代** `<subject>` vs `@图片N` 硬规则（见 `rules-and-fallback.md`），是其超集说明；与既有「权威锚定链 P4→P7→P8.5→P8→P9」并存。
- **OAK 原生 Triptych（Route B）**：三联画本就控 story/pacing/camera language/**look/lighting/mood/environment**（OAK 原文要求匹配参考图）——**不要在原生路线里把它降级成只剩叙事骨架**。混 Koda 身份板分工时，才用 Contract 把 triptych **收窄**到只控 staging/structure、长相交身份板。

---

## 5 · ⭐ infer-between 模式（Route B 的核心·质感驱动 Clip）

### 5.1 是什么
三联画（上/中/下 3 关键图）只交 3 张图 + 「做成片段」，让模型**自己脑补 3 图之间的动作/过渡/运镜/情绪节拍/动量**。源自 OAK 003。

### 5.2 为什么不破无损翻译
video-sop 无损翻译只管**事实**（人物/事件/时序/地点/道具/台词），**不要求逐帧规定动作**；OAK 三联画**也禁发明新事实**（no new characters/props/locations，preserve identity），只 infer 动作。边界对得上：**锁事实、放权动作**。

### 5.3 决策变量：每条 Clip 问「事实驱动 还是 质感驱动」
| | 事实驱动（剧情/带货/因果动作）| 质感驱动（氛围/舞蹈/情绪流/一镜到底）|
|---|---|---|
| 衔接动作 | 是剧情事实，**逐拍写**（严控 8-A / Route D-E）| 非关键事实，**放权脑补**（Route B infer-between）|
| 例 | 「拧螺丝→机器塌」因果链 | 功夫独舞爆发段、云海风帆 |

判定挂 `phase5-storyboard.md` 5.1/5.3：该 Clip 若全是质感、无因果链/无必须命中的具体动作事实，才允许标 `infer-between`。

### 5.4 护栏：FACT-LOCK（infer-between Clip 必填，没写清不准启用）
模型在**动作/运镜上呼吸**，在**事实上不许漂**。FACT-LOCK 用下列**七字段固定英文标签**（机检键名·三根一致·跨根可移植；校验器按行首标签解析，**勿改名/勿译**，中文写在值里）：
```
FACT-LOCK
IDENTITY / COSTUME / SIGNATURE MARKERS:
[身份：<subject> 或 @图片N，全名、服装/状态、身份不变量，一字不差]

SCENE / ENVIRONMENT REFERENCE:
[场景：Clip 级场景 @图片N（即便不逐分镜嵌也不能丢，防场景漂移），地点/时间/天气/材质地标]

PROP WHITELIST:
[允许出现的道具白名单；无新增时写 no new props]

POPULATION STATE:
[无人物 / 只有{命名角色} / 背景有弱化学生/路人/乘客/宾客/工作人员 / 其它确切人口状态（沿用 Phase4 场景人口字段）]

NO INVENTION:
No new characters, no new locations, no new props, no new plot events, no new dialogue, no changed identity.

KEY BEATS:
[1~3 个关键 beat：起点状态 / 转折或压力 / payoff 或落幅]

INFERENCE SCOPE:
Only infer missing action, transition, camera evolution, emotional pacing, and momentum between the key beats.
```
> NO INVENTION 与 INFERENCE SCOPE 两行保留上面英文原句（校验器按其内容机检"禁发明事实"与"只推断动作/运镜"，别替换成纯中文，否则会判缺）。

### 5.5 Phase8 专用格式（不伪装成普通 8-A）
infer-between Clip 用独立块，便于解析器/校验器区分严控 8-A 与质感 infer-between。**子段标签与字段名固定英文**（FACT-LOCK / REFERENCE AUTHORITY CONTRACT / TRIPTYCH ROLE / GENERATION DIRECTION 及各权威字段都是校验器机检键，**勿改名/勿译**）：
```
X-TECH INFER-BETWEEN CLIP
FACT-LOCK:
  [§5.4 完整 FACT-LOCK 七字段块，逐字段固定英文标签]

REFERENCE AUTHORITY CONTRACT:
  IDENTITY AUTHORITY:
  STRUCTURE AUTHORITY:   ← 须点名 Route B / OAK Triptych / infer-between
  STAGING AUTHORITY:
  LOOK AUTHORITY:
  ACTING AUTHORITY:

TRIPTYCH ROLE:
  Top panel    = start state
  Center panel = progression pressure
  Bottom panel = payoff / final frame
  [声明 Triptych 控 look/lighting/mood/environment 还是只控 structure/pacing——OAK 原生控 look；混身份板时按 Contract 收窄]

GENERATION DIRECTION:
  Infer only the missing action, transition, camera evolution, emotional pacing, and momentum between the panels.
  Do not add new characters, props, locations, plot events, dialogue, or changed identity.
```
- infer-between Clip **豁免** Phase8「每个中间动作/分镜都逐拍 + 逐分镜 `@图片N`」硬清单；**但 Clip 级场景 `@图片N` 与 population 必须保留**。**校验器现已机检本格式**（三根对齐 2026-06-27）：FACT-LOCK 七字段齐 + 场景 @图片N + population + no-invention + 1~3 key beats + inference scope、四段标签齐、STRUCTURE AUTHORITY 点名 Route B、单 prompt 不混 8-A、infer-between 块内无 FACS/IPA/Laban/AU 泄漏；见 §5.7/§9 与 `validate_phase8_prompt.py --expected-xtech-infer-between N`。

### 5.6 松生成 + 严审片
- **松生成**：按上面格式给即梦发挥空间。
- **严审片**：用 video-sop 现成 **Gate10 逐帧审片**（canonical ID `generated_video_visual_audit`；本根 reference = `phase9-frame-audit.md`、Codex 根 = `post-generation-video-audit.md`，跨根别名表见该文件顶部「跨根 canonical 标识」节；共享工具 `Desktop\tools\video-frame-audit\frame_audit.py`）拿 FACT-LOCK 逐帧核身份/道具/朝向/关键 beat/场景人口；漂了按 Gate10 返修（重抽/局部删/改 Prompt）。
- 一句话：**放权放在动作和运镜上，不放在事实上；松着生成、严着审片。**

### 5.7 ✅ validator 现状（已扩展·2026-06-27 三根对齐）
`validate_phase8_prompt.py` **现已机检 `X-TECH INFER-BETWEEN CLIP` 格式**（三根一致：Claude/Antigravity 中文消息、Codex 英文，机检键名与规则同源）：
- 跑法：含 infer-between 的 Prompt 集照常跑校验器、加 `--expected-xtech-infer-between N` 断言专用块数量，`RESULT: PASS` 才交付（不再"会 FAIL/报错"）。
- 机检覆盖：① 单 prompt 不混松严（C1：标准 8-A 块禁现 infer-between/FACT-LOCK 字样、专用块禁现 8-A 表头/分镜时段）；② infer-between 块豁免逐分镜 `@图片N`、改校 FACT-LOCK 七字段（场景 @图片N + population + no-invention + 1~3 key beats + inference scope）+ 四段标签齐 + STRUCTURE AUTHORITY 点名 Route B；③ infer-between 块内 FACS/IPA/Laban/`AU\d+` 泄漏拦截。
- 仍归人工/Gate10：beat 是否真对应剧本、acting code 语义正确性、成片是否真没漂事实（机检只管格式完整性，Gate10 管像素事实）。故闸7b 现是**机检兜底 + 人工语义**，不再是"纯人工"。

---

## 6 · 各 Route 细则要点

- **A · OAK Audition**：表演发现/独白/心理测试 → 输出 `ACTING STYLE TO APPLY`（6~9 行，简洁、可给演员执行）。🔴 **接 video-sop 时禁沿用 OAK「从图推角色」**——`performance-engine.md` 铁律是"禁从角色图推动机"（本流程有完整剧本）；OAK audition 只作**无剧本试镜 / self-tape 表演校准**，不进剧情 Clip、不覆盖已确认剧本事实。acting style 保持短，不写成 storyboard 块（防在 Koda 巨型 prompt 里被稀释）。
- **B · OAK Triptych infer-between**：见 §5。
- **C · Koda 4-panel same-lens master**：4 格是 sampled phases、不是 4 个独立切镜；same-lens / developing master 写清；scale change 来自物理 camera movement 不是剪辑。做视觉锚点时挂 `phase8-5-keyframe-anchors.md`。
- **D · Koda storyboard**：= Phase8 8-A 严控（storyboard 是 blueprint、character ref 是身份权威、不渲染 storyboard sheet 本身、不继承草图代理比例、按 panel order 执行）。
- **E · Koda direct shotlist**：不画 storyboard，直接角色 ref + 文字 shot sequence（shot 号/lens/动作/cause-effect/SFX/style/env）；shot 因果短而强时用，空间调度不如 storyboard 稳、需更强文字因果。
- **F · Koda Extend**：见 §2 硬规则。

---

## 7 · C1-C9 在 video-sop 的去向

| # | 冲突/风险 | 去向 |
|---|---|---|
| C1 | 松推断 vs 逐格执行 | gate 项：单 prompt 不混 infer-between 与逐拍 8-A |
| C2 | 成品三联画 vs 单色草图 look 源 | Reference Authority Contract（LOOK AUTHORITY）|
| C3 | acting style 散文 vs FACS/IPA/Laban 编码 | OAK acting style 主权；FACS/IPA/Laban 仅可选增强、**不进正文**（见 §8）|
| C4 | 跨场景迁移 vs Extend | 跨场景(意图切换)用 acting style；连续 take 续接用 Extend（Route F·地点可在 take 内变）|
| C5 | 镜头探索 vs 锁定蓝图 | 探索（OAK 十构图）只在前期；进 Route C-F 即锁定 |
| C6 | 短表演指导 vs 超长生产板 | acting style 保 6~9 行 |
| C7 | 模型推断 vs 因果链锁定 | 因果重要走 Route D/E 写清 cause-effect |
| C8 | 多 reference 抢权 | Reference Authority Contract |
| C9 | 整理稿替代原文（**过程风险**）| §1 原文保护，不当机检闸 |

---

## 8 · 反重复吸收 / 边界（防降级·防双系统）

- **OAK audition** 已 = `performance-engine.md`，且**故意反转**（禁从图推角色）。别再开第二套。
- **FACS / IPA / Laban** 是内部编码层、**不进 Phase8 正文**（内容已被三本表演手册 micro-expression/voice-control/action-naturalness 物理化覆盖）。⚠️ **现有 validator 尚未直接拦这些词**（只拦 Voice Trigger 等 performance 内部标签）——要机检需扩展（FACS `AU\d+` 是安全判别式可正则；Laban 的 weight/time/space/flow 是常用英文词、IPA 误伤高，宜走语义 self-check gate）。在扩展前，由 LLM 语义自检守"FACS/IPA/Laban 不进正文"。
- **Koda storyboard / direct shotlist** 已是 Phase8 8-A，别当新东西。
- **performance-engine.md 不动**（no-touch）；**OAK 十构图** = video-sop 现无的镜头发散器，真增量，放前期探索（Phase5/Phase8.5），进锁定路线后不再自由探索。
- **10s 上限不动**（见 §1.4）。

---

## 9 · 与 Phase1-9 映射 + 待办

| X技巧层 | 位置 | 方式 |
|---|---|---|
| Koda Identity Board | Phase7 | 高级角色身份板模式 |
| OAK Audition | performance-engine §7 self-tape | 表演校准（禁从图推角色）|
| Acting Style Extraction | Phase5+Phase8 | 输出 `{项目名}_角色表演基线卡.md` |
| OAK 十构图探索器 | Phase5 / Phase8.5 | 镜头发散 |
| OAK Triptych infer-between | Phase8 质感 Clip 路线 | §5 + FACT-LOCK + Gate10 |
| Koda 4-panel same-lens | Phase8.5 | 一镜到底锚点 |
| Koda 8/10/12 storyboard | ≈ Phase8 8-A | 已是默认 |
| Koda direct shotlist | ≈ Phase8 8-A | 已是默认 |
| Koda Extend | Phase8/Phase9 continuation | 串行依赖（§2）|
| Reference Authority Contract | Phase8 必填 | core（§4）|

**待办（不在本批，需双根对齐后再动）**：
- ✅ **`validate_phase8_prompt.py` 已扩展（2026-06-27·三根对齐·见 §5.7）**：① C1 不混写检查 ✓；② infer-between Clip 豁免「逐分镜 `@图片N`」硬断言、改校 FACT-LOCK 含场景 ref + population ✓；③ FACS/IPA/Laban/`AU\d+` 在 infer-between 块内拦截 ✓。新 CLI `--expected-xtech-infer-between N`。三根行为一致（Codex 英文先行；Claude/Antigravity 中文港入、消息中文 + 英文机检键、保留闸8 场景人口软告警；Claude≡Antigravity validator 字节相同）。回归实测：标准 8-A prompt 新旧输出**字节一致**、infer-between good/bad/disguise 判定正确。落地评估见 `X技巧资料库\validator对齐评估_Codex_infer-between分支_给三根.md`。
- ✅ **Gate10 审片 reference 双根命名分歧（已按别名法收口·Claude 侧）**：不改名——跨根统一到 canonical ID `generated_video_visual_audit`（人读名闸10 + 共享工具 `frame_audit.py`，本就两根一致）；reference 文件名各保留本根惯例（Claude `phase9-frame-audit.md` ↔ Codex `post-generation-video-audit.md`），别名表 + 跨根引用规则见 `phase9-frame-audit.md` 顶部「跨根 canonical 标识」节。**待 Codex 侧加对称别名注**（提案见 `X技巧资料库\双根审片文件名统一_别名法_给Codex.md`），届时双根对齐完成。
- **待实测后补 infer-between 金样示例**：本模块现只给 schema/格式模板，**不放未实测填实例**（防未验证内容当金样被照抄）；待一条 infer-between Clip 真过即梦 + Gate10，再把验证过的 prompt 补进 `§11 示例`（性质同 `phase8-video-prompt.md` §五官方原文示例）。
- ✅ **source pack 可移植性（已选 A·已落地）**：原始/复刻 prompt 已打包进 `references/x-tech-source/`，随 skill 自洽、换机/clone 不断链（见 §10）。

---

## 10 · source pack（原始 prompt 全文·随 skill 自洽打包）

每条 Route 的原始/复刻提示词**已打包进 `references/x-tech-source/`**，随 skill 走（含进 GitHub）、换机/clone 不断链：
- `001_OAK_audition_system_prompt.md`（Route A 试镜）/ `001_OAK_acting_style_extractor.md`（表演风格提取）
- `002_OAK_10composition_expander.md`（十构图探索）
- `003_OAK_triptych_to_seedance.md`（Route B 三联画）
- `004_Koda_full_prompts.md`（Koda 11 条完整原文 verbatim）

需要原文完整措辞时**先开 `references/x-tech-source/`**（按 §1 原文保护使用）。更完整的采集库（方法说明/拆解/合一工作流定稿/双引擎交叉检查）在桌面 `X技巧资料库\`，非必需。

🔴 **连 `x-tech-source/` 都缺失/不可达时，不得凭本模块摘要重建原文 prompt**——宁可暂停、向用户要原文，也不低配复写（守 §1 原文保护 + C9 过程风险）。
