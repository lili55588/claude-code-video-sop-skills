# 多 Agent 并发编排层 v0.1 设计草案（video-sop）

> 状态：**设计阶段、未建**。Claude×Codex 收敛达成 v0.1 共识；**round-1（4 主修+3 小项）+ round-2（4 开放项答复 + 1 语义补丁）Codex 交叉检查均已折入（2026-06-18，见 §15）**。本文件 Claude 侧主笔；round-2 后已跑 **dry-run round-0**（人扮演 Orchestrator，5 历史 Clip，全链跑通+验收全中，见 §17）→ 回填 §9/§6 → **spawn 2 个独立子 agent 实测隔离收益** → **Codex 复核三发现已折入契约（§4 `output_path` / §10 无 BOM / nearest_fallback 复核信号）** → **v0.1 确定性机制层已落地为可执行工具**（`tools\gate10-orchestrator\orchestrate_gate10.py`，init/parta/tasks/merge 本机全跑通，见 §18，待 Codex 交叉检查）。
> 定位：在现有「Phase Gate + VVK + 锁定状态 + 模型无关校验器」之上，加**一个 Orchestrator 驱动的相内并发层**。不重写工作流，只把已散落的多 Agent 片段（双引擎 / VVK Part C / 任务包+校验器）收敛成显式机制。
> 关联：`闸10_成片逐帧视觉验收_规格草案.md`、`visual-verification-kernel.md`(VVK)、`COLLABORATION.md`、记忆 `multi-agent-orchestration-v0.1`、`dual-engine-collaboration-template`。

---

## 0 · 口诀与边界

```
主链串行，创作单头；
验收扇出，证据工具化；
Worker 无状态，输入钉版本；
Orchestrator 单写，合并看地板；
Part C 隔离，边界单审。
```

- **是什么**：受控并发——一个有状态 Orchestrator + 少量无状态判断型 Worker + 确定性工具前置消化 + 结构化 RESULT + 合并闸 + 三道并发屏障。
- **不是什么**：不是"12 个角色一起跑"，不是"大家一起写主文档"，不是把确定性脚本 agent 化。

**核心原则**
- 主链（权威锚定链 `P4→P7→P8.5→P8→P9`）因果串行，**不跨链并发**（假并行，会被 cascade 作废）。
- 创作/剧本（P1-3、P4 终确认、P5 终改）保持**单作者意识**，不扇出写。
- 验收 / 证据 / 参考图质检 = **大胆扇出**。
- 判据：**需 LLM 判断才叫 Agent；确定性的是工具，不 agent 化。只差注入矩阵的是同一角色的实例，不拆成多份角色。**

---

## 1 · 架构

```
                       ┌──────────────────────────┐
                       │   01 Orchestrator (单写)   │
                       │  读锁定账本→扇出→合并→更新   │
                       └──────────┬───────────────┘
        ┌─────────────────────────┼─────────────────────────┐
        │ 工具前置（确定性，零 LLM） │                          │
        │  Part A: frame_audit.py   │   无状态判断型 Worker（并发）│
        │  / image_asset_audit.py   │   03 VVK Part B Judge      │
        │  validators / 软信号采集   │   05 Part C Blind Reviewer │
        └───────────────────────────┘   06 Boundary Stitch       │
                                        02 Source-Authority Auditor│
                                        04 Prompt Writer           │
                                        07 Repair Router(建议)      │
        三道并发屏障：① provenance 钉死  ② cascade 在途  ③ Part C 隔离
        合并闸：RESULT schema 校验 + 确定性地板优先(保 issue_class) + 状态归一
```

---

## 2 · 七个真 Agent 角色

每个 Agent 单一职责，输入只读任务包，输出只写自己的 `RESULT.md`，**不得改最终主文档与锁定状态**。

| # | 角色 | 单一职责 | 典型 allowed_writes |
|---|---|---|---|
| 01 | **Orchestrator** | 唯一有状态。读锁定账本、生成任务包、分发、收 RESULT、跑合并闸、更新 HANDOFF 与锁定状态 | 锁定账本 / HANDOFF.md / MERGE_REPORT.md |
| 02 | **Source-Authority Auditor** | 审权威链完整性：P4/P5/P7/P8 素材 ID、`exact_text`、`criticality`、来源映射是否可读、是否对得上 | 自身 RESULT.md |
| 03 | **VVK Part B Judge**（参数化） | 视觉主判。**一份角色按 gate 注入检查矩阵**（闸2b 参考图 / 闸9 关键帧宫格 / 闸10 成片各一套矩阵） | 自身 RESULT.md |
| 04 | **Prompt Writer** | 只写单 Clip 的 Phase8 Prompt，**不改剧情/结构** | 单 Clip Prompt 草稿 |
| 05 | **Part C Blind Reviewer** | 对抗性独立盲审，只找盲点，**看不到 Part B 结论**（见屏障③） | 自身 RESULT.md |
| 06 | **Boundary Stitch Reviewer** | 只审相邻 Clip 边界连续性，不重审整条 Clip | 自身 RESULT.md |
| 07 | **Repair Router** | 只判最小回滚层 + 返修路径，**v0.1 仅出建议、不触发执行**（见 §8） | `repair/RESULT.md`（自己写；Orchestrator 再并入 MERGE_REPORT） |

> **VVK Part B Judge 为何是一份**：闸2b/9/10 同用 VVK 内核，只差检查矩阵——矩阵是**注入数据**不是角色代码。Codex 上一版的 04/05/08 三个 Judge 已收编为本角色的三种实例。

---

## 3 · 降为工具（不设 Agent）/ 移出并发层

**降为工具内联调用**（Orchestrator 直接跑子进程，零 LLM 上下文）：
- `frame_audit.py`（Gate10 Part A）
- `image_asset_audit.py`（闸2b/9 Part A，含 region/panel dhash + OCR + 水印软信号）
- `validate_phase8_prompt.py`（Phase8 确定性兜底）
- 软信号采集（hash/OCR/watermark）
- RESULT schema 校验器

**移出本并发层**：
- **Sync Auditor**（Codex/Claude/shared tools 跨树交叉检查）——属**双引擎维护回路**，不是每个视频项目内的 worker。

> 原则回归：最大的记忆稀释红利来自**把活推进确定性工具**，不是堆 Agent。每个 Agent 的 LLM 判断面越小、确定性预消化越多越好。

---

## 4 · 任务包契约 `TASK.md`

每个 Worker 只拿一个任务包，**输入版本钉死**（屏障①）。

```yaml
job_id:            gate10_重返那年盛夏_20260618
agent_role:        vvk_part_b_judge        # 见 §2
unit_id:           Clip12
phase_gate:        P9/Gate10
matrix_profile:    gate10                  # 注入哪套检查矩阵
authority_chain:   [P4素材清单, P7:R01/R03/P04, P8.5:Clip12宫格, P8:Clip12Prompt]
input_files:                                # 钉死版本
  - path: pippit_outputs/...Clip12.mp4
    sha256: <hash>
    lock_state: <从锁定账本读>
    source_phase: P9
    authority_id: Clip12
  - path: 参考素材图/R01_...png
    sha256: <hash>
    lock_state: LOCKED_PASS
manifest_path:     EVIDENCE/frame_audit_manifest.json
manifest_sha256:   <hash>
allowed_reads:     [input_files, EVIDENCE/, authority_chain 文件, 注入矩阵]
output_path:       part_b/RESULT.md          # 钉死实际输出文件，allowed_writes 必须等于它
allowed_writes:    [part_b/RESULT.md]         # spawn 实测：写 RESULT.md vs 实际 RESULT.agentB.md 会破约 → 用角色目录式钉死
required_checks:   [分镜对位, 朝向(参照物锚定), 站位, 道具承载面, 跨镜, 身份, 时长比例]
output_schema:     RESULT.md v0.1          # 见 §5
fail_conditions:   [错误朝向/视线, 无解释跳位, 关键道具漂移, 身份崩坏, 未全帧抽取]
do_not_do:         [改剧情, 改 Prompt, 写主文档, 改锁定状态, 读 Part B 结论(仅 Part C)]
```

---

## 5 · 输出契约 `RESULT.md`

固定结构化字段，Orchestrator 只看字段、不信散文。

```yaml
unit_id:                 Clip12
role:                    vvk_part_b_judge
input_pins:                              # 回填实际读到的 hash（屏障①复核用）
  - path: ...Clip12.mp4
    sha256_read: <hash>
  - manifest_sha256_read: <hash>
verdict:                 PASS | REGENERATED_PASS | ACCEPTED_WITH_RISK | FAIL_BLOCKED | AUDIT_INCOMPLETE
issue_class:             EVIDENCE_GAP | TECH_SPEC_BLOCKED | CONTENT_FAIL | ACCEPTABLE_RISK | null
severity:                BLOCKER | EDIT_FIX | REGEN_REQUIRED | ACCEPTABLE_RISK
evidence_used:           [帧号/区域/锚点, ...]
findings:                [逐项, 每项带证据]
risk_items:              [命名风险, 注入下游 checklist]
affected_downstream:     [被影响的下游引用单元]
minimum_rollback_layer:  P9 | P8.5 | P8 | P7 | P5 | P4
recommended_fix:         首选 + 备用
confidence:              0.0–1.0          # 合并后果见 §8
boundary_status:         PASS | FAIL_BLOCKED | BOUNDARY_PENDING   # 仅 Boundary Stitch Reviewer 填；任一端 Clip 为 FAIL → BOUNDARY_PENDING（不混进上面的 verdict 枚举）
```

证据落 `EVIDENCE/`：`frame_audit_manifest.json` / `frame_audit_report.md` / `image_asset_audit_manifest.json` / `image_asset_audit_evidence.md`。

---

## 6 · 三道并发屏障（机制必含）

### 屏障① Provenance Pinning / 版本钉死
- `TASK.md` 钉死每个输入的 `sha256 / lock_state / manifest_sha256`。
- Worker `RESULT.md` 回填 `input_pins`（实际读到的 hash）。
- Orchestrator 合并时复核：
  ```
  RESULT.input_pins.sha256 == 当前锁定账本.sha256
  RESULT.manifest_sha256   == 当前 manifest_sha256
  authority lock_state 仍有效
  ```
  不符 → `STALE_RESULT` → 作废 → 重派。
- **🔴 前置缺口（v0.1 必须先建）**：上述复核需一份**机读锁定账本**（见 §10）；现锁定态散在 HANDOFF/质检报告散文里、没有权威对比源。**没有锁定账本，屏障① 是空中楼阁——这是 v0.1 的第一前置任务。**
- **🟠 dry-run round-0 发现（manifest 钉死隐患）**：`frame_audit` manifest **无时间戳** → `manifest_sha256` 跨次重跑稳定、可钉；但 `image_asset_audit` manifest 含 `created_at` → **每跑必变、不可钉**。**结论**：provenance 以**资产/视频 `sha256`（稳定）为主钉**；manifest 仅 frame_audit 的可直接钉，闸2b/9 用 image_asset_audit 时应钉**图片资产 sha256**，或先让该工具去掉 `created_at`（共享工具归 Codex 改）。

### 屏障② Cascade In-Flight / 在途级联屏障
上游 P7/P8.5 资产被返修或重生成时：
```
Orchestrator 暂停所有依赖它的在途任务
查 downstream reference list（VVK 依赖记录）
标记 affected jobs = INVALIDATED_BY_UPSTREAM_CHANGE
重建 Part A evidence → 重新派发受影响单元
```
防"看似都 PASS、其实不是同一世界线"的假结果。**依赖清单要被当成并发屏障用，不只是事后 cascade。**

### 屏障③ Part C Isolation / 盲审机械隔离
- `Part C TASK.md` 的 `allowed_reads` **排除**：Part B 的 RESULT / verdict / comments、Repair Router notes。
- 只允许读：原始输入、Part A evidence、权威链文件、对应检查矩阵。
- **优先用另一个引擎做 Part C**（双引擎天然跨模型盲审；Clip2 背对窗证明同上下文=同盲点）。

### Boundary Stitch — 触发与 Part C（round-2 定）
Boundary Part C **不默认**，但高风险边界必须有。
- **触发 Part C**：同场景连续动作跨 Clip｜同一关键道具跨 Clip 改承载面/归属手/位置｜人物朝向/视线/左右关系承接｜任一端 `ACCEPTED_WITH_RISK`｜任一端 `confidence<0.9`｜任一端刚 repair/regenerate｜Part B 的 boundary 判定与 Clip 内判定有张力｜情绪/台词/动作状态强连续。
- **不需 Part C**：明确硬切新场景｜无共享人物/道具/动作状态｜前后叙事天然断开｜两端 `LOCKED_PASS` 且 boundary `confidence>=0.9`。
- **隔离同 Part C**：Boundary Part C 不读 Boundary 一审 RESULT，只读边界帧 + Clip 表 + Prompt + 权威链 + Part A evidence。

---

## 7 · 合并闸 — 两条健壮性

### 7.1 RESULT schema 校验
缺字段 / 状态非法 / 引用不存在 / hash 不匹配 → `RESULT_INVALID` → 拒收 → 重派（复用现成重试预算 K）。

### 7.2 确定性地板优先（**保 issue_class**）
Worker 判断不能覆盖工具地板。地板压"放行/不放行"，但**必须透传 issue_class，决定走哪条修复车道**：

```
Part A = AUDIT_INCOMPLETE,        worker 说 PASS  => 仍 AUDIT_INCOMPLETE（先修证据）
Part A = TECH_SPEC_BLOCKED,       worker 说 PASS  => 地板 FAIL_BLOCKED + issue_class=TECH_SPEC_BLOCKED
                                                     → Repair Router 走【容器修先】(裁/重导)，不是内容 regen
frame_audit effective_status=FAIL_BLOCKED, worker 说 ACCEPTED => 地板赢
```
> 🔴 **Clip2 教训**：比例 864×496 是 TECH_SPEC（容器问题），crop 成真 16:9 → ACCEPTED_WITH_RISK，**不是内容 FAIL、没重生成**。地板若抹掉 issue_class，可裁的比例问题会被误送重生成。

---

## 8 · 合并规则

Orchestrator 只看结构化字段：
```
任一 AUDIT_INCOMPLETE      -> 阻断，先修证据（不重生成）
任一 FAIL_BLOCKED          -> 阻断；按 issue_class 交 Repair Router 出建议
任一 ACCEPTED_WITH_RISK    -> 风险注入下游 checklist（LOCKED_WITH_RISK）
confidence < 0.75         -> 不默认 PASS；强制 Part C 或人工复看（呼应 VVK"看不清只降级"）
confidence 0.75–0.9       -> 可抽样 Part C
confidence >= 0.9         -> 可正常合并，但仍受确定性地板约束
全部 PASS / REGENERATED_PASS -> 可锁定（LOCKED_PASS）
Part C 与 Part B 冲突      -> 取更严格、可辩护的结论
Boundary 一端为 FAIL       -> seam 标 BOUNDARY_PENDING，不出误导性 PASS，待该端修好再审
```
> **v0.1 Repair Router 只出建议**：作为 Worker 只写自己的 `repair/RESULT.md`，由 **Orchestrator 单写并入 `MERGE_REPORT.md`** 给人/主笔执行——**Worker 不直接写 MERGE_REPORT（单写者不变式）**，且**不在并发 run 内自己触发重生成**（否则把屏障② 要防的 cascade 竞态又引回来）。

---

## 9 · 状态词表归一（合并闸必备）

两个 Part A 工具 + VVK 词表不同，合并前先归一到 VVK 语言。
> frame_audit `effective_status` 实际仅三态（`AUDIT_INCOMPLETE` / `AUDIT_READY` / `AUDIT_READY_WITH_DETERMINISTIC_RISK`）；细分靠 `deterministic_review_policy.status` **三值**（`DETERMINISTIC_PASS` / `DETERMINISTIC_FAIL_BLOCKED_REQUIRED` / `DETERMINISTIC_UNKNOWN_REVIEW_REQUIRED`，frame_audit.py:622/625/628）+ `visual_verdict_floor`。
> ⚠ **dry-run round-0 修正**：round-2 的"全枚举"漏了 `DETERMINISTIC_FAIL_BLOCKED_REQUIRED`（恰是触地板那个，U01/U02 实跑命中）——纸上共识的洞由实跑补上。

| Part A 工具输出 | 归一到 VVK | 处置车道 |
|---|---|---|
| `AUDIT_INCOMPLETE`（两工具） | `AUDIT_INCOMPLETE` / issue=EVIDENCE_GAP | 修证据，禁放行 |
| image `TECH_SPEC_REVIEW` / frame `deterministic_block=true`（含 `effective_status=AUDIT_READY_WITH_DETERMINISTIC_RISK`）/ `visual_verdict_floor=FAIL_BLOCKED` | 地板 `FAIL_BLOCKED` / issue=TECH_SPEC_BLOCKED | 容器修先 |
| frame `AUDIT_READY` + `deterministic_review_policy.status=DETERMINISTIC_UNKNOWN_REVIEW_REQUIRED` | `REVIEW_REQUIRED`（**非硬 FAIL、也非普通 PASS**） | 先补清规格 / 确认 unknown 可否接受，**不能最终 PASS** |
| `AUDIT_READY` + `visual_verdict_floor=None` + `deterministic_review_policy.status=DETERMINISTIC_PASS`（**仅此一档**进 Part B） | 证据就绪 → 交 Part B（**Part A 永不判 PASS**） | 进视觉主判 |
| 软信号 `SOFT_SIGNAL_ONLY` / `NOT_AVAILABLE` | 不改状态、仅提示 | 需视觉确认才升级 |
| frame `scene_diff.boundary_review_signal.status=BOUNDARY_REVIEW_REQUIRED`（Codex 已落地，orchestrator 已接）| 软信号、**不改最终状态** | 提示 Part B 核真实切点 vs 声明分镜（nearest_fallback 自证误绿的复核钩）|

---

## 10 · 前置任务（v0.1 落地前必须先有）

1. **机读锁定账本**（屏障① 地基）：路径**项目相对** `{project_root}/锁定账本.json`（不绑 `claude长视频创作`，方便 Codex/GPT 项目复用）。必须覆盖 Gate10 任务包要钉的**所有**权威输入——不只 P7，还含视频/Prompt/P8.5 宫格关键帧/Part A manifest，否则 §4 TASK.md 里的 video/prompt/manifest hash 没有权威账本可比：
   ```json
   { "authorities": [
     { "authority_id": "R01",          "type": "p7_asset",       "path": "参考素材图/R01_...png",
       "sha256": "...", "lock_state": "LOCKED_PASS", "source_phase": "P7",
       "downstream_refs": ["Clip4/分镜2","Clip5","宫格 Clip5"], "risk": null },
     { "authority_id": "Clip12",        "type": "clip_video",     "path": "pippit_outputs/...Clip12.mp4",
       "sha256": "...", "lock_state": "...", "source_phase": "P9" },
     { "authority_id": "Clip12_prompt", "type": "prompt",         "path": "..._视频生成Prompt集.md#Clip12",
       "sha256": "...", "lock_state": "...", "source_phase": "P8" },
     { "authority_id": "Clip12_grid",   "type": "anchor_grid",    "path": "关键帧锚点/Clip12_宫格.png",
       "sha256": "...", "lock_state": "...", "source_phase": "P8.5" },
     { "authority_id": "Clip12_partA",  "type": "part_a_manifest","path": "EVIDENCE/frame_audit_manifest.json",
       "sha256": "..." }
   ]}
   ```
   `type ∈ {p7_asset, clip_video, prompt, anchor_grid, part_a_manifest}`。由 Orchestrator 维护、单写；把现散在 HANDOFF/质检报告里的锁定结论结构化。
   **首次回填（two-step，round-2 定）**：
   - **Source-Authority Auditor**（#02）读 HANDOFF/质检报告/Prompt 集/P7·P8.5 文件 → 产 `锁定账本.draft.json`（或 `source_authority_audit_RESULT.md`）。
   - **Orchestrator** 复核 path/sha256/lock_state/downstream_refs → 单写正式 `{project_root}/锁定账本.json`。
   - **不许猜**：只能从散文推断、证据不足者 → `lock_state=AUDIT_INCOMPLETE` + `note=needs_confirmation`，**不得猜成 `LOCKED_PASS`**。
   - **边界**：Claude 项目由 **Claude（该项目主笔=Orchestrator）首次写账本**；Codex 可交叉审计、**不直接替改 Claude 项目账本**。
   - **非视觉 authority 的 `lock_state` 语义**：对 `clip_video/prompt/part_a_manifest`，`lock_state` 表示"可作当前任务权威输入的**快照状态**"，**不是 VVK 图像锁**——避免 `LOCKED_PASS` 在非视觉资产上语义混淆。
   - **编码（spawn round 实测踩中）**：账本/任务包等供 Python provenance 读取的 JSON **必须无 BOM UTF-8**（或读端统一 `utf-8-sig`）。PowerShell `Out-File -Encoding utf8`(5.1) 会写 BOM → `json.load(encoding='utf-8')` 报 `Unexpected UTF-8 BOM`；dry-run 账本已实测踩中（前 3 字节 EF BB BF）。
2. **状态归一表**（§9）固化进 Orchestrator 合并逻辑。
3. **RESULT.md / TASK.md schema** 定版（§4/§5）。

---

## 11 · 并发触发阈值（不默认全开）

```
Phase7 图片 >= 6 张        : 开并发
Phase8 Prompt >= 8 Clips   : 开并发
Gate10 视频 >= 5 Clips     : 开并发
高风险（主角/产品/文字/连续性）: 强制 Part C
少量 1–3 Clips             : 单 Agent 更划算（冷启动税 > 收益）
```

---

## 12 · v0.1 试验田 = Gate10（先文件约定，后自动框架）

**为何选 Gate10**：叶子节点（跑时不反污染 P4-P8）/ Clip 粒度天然并发 / `frame_audit.py` + 确定性地板现成 / Part C + Boundary 价值明确 / 合并简单（任一 Clip 阻断则整片不放行）。

**文件约定（先手动扇出跑通，再自动化）**：
```
/jobs/gate10_{项目}_{日期}/
  ORCHESTRATION.md            # Orchestrator 状态、单元清单、锁定账本快照
  units/
    Clip01/ { TASK.md, EVIDENCE/, RESULT.md }
    Clip02/ { TASK.md, EVIDENCE/, RESULT.md }
    ...
  boundary/
    Clip01_Clip02/ { TASK.md, RESULT.md }
    ...
  repair/
    RESULT.md                 # Repair Router 出的返修建议（worker，自己写）
  MERGE_REPORT.md             # 合并结论（**仅 Orchestrator 写**，并入 repair 建议）
```

**v0.1 Gate10 流程**：
```
1.  Orchestrator 读 Phase8 Prompt / Clip 表 / P7·P8.5 锁定资产 / 视频文件 + 锁定账本
2.  frame_audit.py 为每个 Clip 产 Part A evidence（工具，非 agent）
3.  生成各 Clip TASK.md，钉死 sha256/provenance
4.  VVK Part B Judge 按 Clip 并发审片
5.  高风险 Clip → 派 Part C Blind Reviewer（隔离上下文，优先另一引擎）
6.  Boundary Stitch Reviewer 审相邻 Clip 边界（一端 FAIL → BOUNDARY_PENDING）
7.  Orchestrator 校验 RESULT schema + provenance（不符→STALE/INVALID→重派）
8.  Orchestrator 应用确定性地板（保 issue_class）+ 状态归一
9.  Orchestrator 初判合并（地板 + 归一 + 阈值 + boundary_status）
10. 若 FAIL → Repair Router 写 `repair/RESULT.md`（最小回滚层建议，仅建议、不执行）
11. Orchestrator 并入 repair 建议 → **单写定稿 MERGE_REPORT.md** + 更新锁定账本 + HANDOFF
```

**v0.1 最小闭环验收标准（round-2 定，dry run 即可）**：
- ≥5 个 Clip 单元 ｜ ≥1 个 Boundary Stitch ｜ ≥1 个 Part C ｜ ≥1 个确定性地板（或 simulated floor）｜ ≥1 个 Repair Router 建议。
- `MERGE_REPORT.md` 能完整说明每个 Clip 的**放行 / 阻断 / 返修建议**。

**⚠ 时序现实**：重返那年盛夏现仅 Clip1-3 生成（Clip2 已审），**达不到 Gate10 ≥5 Clip 阈值**。试验田实跑要么等 Clip4-32 生成，要么拿历史 Clip 回填造 ≥5 测试集。草案可现写，实跑验证依赖生成进度。

---

## 13 · 落地优先级

1. **Gate10 Clip 审片并发**（ROI 最大、最不破坏主链）
2. **Gate2b / Phase7 图片质检并发**（和 VVK + `image_asset_audit.py` 天然匹配）
3. **Phase8.5 Anchor Pack 并发** + 同时引入 Boundary Stitch
4. **Phase8 Prompt 并发**（最后；全局一致性风险，必须挂 `validate_phase8_prompt.py` + 全局引用检查 + 相邻缝合）

---

## 14 · 不并发拆清单

- Phase1-3 剧本/故事方向：单作者意识。
- Phase4 素材清单终确认：权威源头，不多头修改。
- Phase5 Clip 表/连续性报告：**可被检查（读扇出），不宜多头改（写单头）**。
- 锁定状态更新：只能 Orchestrator 写。
- `HANDOFF.md` 最终状态：只能 Orchestrator 写。

---

## 15 · 交叉检查记录 / 未决项

**round-1（Codex 复查，2026-06-18）已折入：**
- [x] **状态归一误放行**（§9）：`AUDIT_READY_WITH_DETERMINISTIC_RISK` 原误标"无硬地板"，已归入确定性地板（`visual_verdict_floor=FAIL_BLOCKED` / `deterministic_block=true` → FAIL_BLOCKED + TECH_SPEC_BLOCKED）。
- [x] **锁定账本 schema 不够**（§10.1）：已泛化为通用 `authorities` + `type`，覆盖 clip_video/prompt/anchor_grid/part_a_manifest，不只 P7。
- [x] **Repair Router 破坏单写者**（§2/§8/§12）：改为写 `repair/RESULT.md`，MERGE_REPORT 仅 Orchestrator 写。
- [x] **BOUNDARY_PENDING 未进 schema**（§5）：加 Boundary 专用字段 `boundary_status`，不混进主 verdict 枚举。
- [x] **confidence 阈值已定**（§8）：<0.75 强制 Part C/人工｜0.75–0.9 抽样 Part C｜≥0.9 正常（仍受地板）。
- [x] **`image_asset_audit.py` ensure_ascii**：Codex 已改 `ensure_ascii=True`、两副本 SHA256 一致（本机已核验），合并闸机读 manifest 不再绊 PowerShell。
- [x] **锁定账本路径**：改为项目相对 `{project_root}/锁定账本.json`，便于跨引擎复用。

**round-2（Codex 答复，2026-06-18）已折入：**
- [x] frame_audit `effective_status` 三态全枚举 + `deterministic_review_policy.status` 细分（§9 加 `DETERMINISTIC_UNKNOWN_REVIEW_REQUIRED`→`REVIEW_REQUIRED` 一档；字段名本机已核 frame_audit.py 实有）。
- [x] 锁定账本首次回填 = Source-Authority Auditor 出 draft → Orchestrator 复核单写；不许猜成 `LOCKED_PASS`；Claude 项目 Claude 首写、Codex 只交叉审计（§10）。
- [x] Boundary Stitch Part C 触发/不触发条件 + 隔离（§6 末）。
- [x] Orchestrator v0.1 人扮演最小闭环 12 步 + 验收标准（§12）。
- [x] 非视觉 authority 的 `lock_state` 语义澄清=快照状态、非 VVK 图像锁（§10）。

**仍开（最小闭环设计/实跑阶段处理）：**
- [ ] 实跑 dry run：现项目仅 Clip1-3，需历史/复制 Clip 凑 ≥5；真实收益验证等 Clip4-32。

---

## 16 · 边界纪律

- 本草案 Claude 主笔（Claude 树视角）；Codex 交叉检查后落地，**不替改对方树**。
- 工具归共享 `tools\`，由 Codex 改；规则归各自 skill references；本编排层规则待共识后再决定挂 video-sop references 还是独立。
- 主链不拆、创作不乱拆、验收与证据层大胆拆——三方已对齐。

---

## 17 · dry-run round-0 记录（2026-06-18，人扮演 Orchestrator）

**位置**：`c:\tmp\gate10_dryrun_20260618\`（scratch，未污染项目）。**用现项目历史视频凑 5 单元**：U01 Clip1-pippit / U02 Clip2-regen / U03 Clip2-16x9 / U04 Clip3-dreamina / U05 Clip1-dreamina。

**全链跑通**：锁定账本(11 authorities) → frame_audit×5(真抽 1632 帧) → 5×TASK.md(钉真 sha256) → 5×RESULT.md → U02 Part C → Clip2_Clip3 Boundary → Repair → Orchestrator 单写 MERGE_REPORT。

**验收标准全中**：≥5 单元 / ≥1 Boundary / ≥1 Part C / ≥1 地板(U01·U02) / ≥1 Repair / MERGE_REPORT 完整。**附加演示**：屏障① STALE 拒收(U05 故意钉错 hash)、BOUNDARY_PENDING(Clip1_Clip2 两端 FAIL)、地板保 issue_class 走容器车道。

**两个真发现（已回填本草案）**：① §9 漏 `DETERMINISTIC_FAIL_BLOCKED_REQUIRED`；② §6 manifest 钉死隐患（image_asset_audit 有 created_at 不可钉）。

**隔离收益已实测（spawn round，2026-06-18，用户授权后）**：spawn 两个真·独立子 agent（Part B Judge + Part C 盲审）同审 U03，各自冷启动、只读任务包、全程不读对方输出。结果——**高价值样本验证通过（n=1 单元 / 2 agent；证明"机制能产生隔离收益"，非统计性"多 Agent 一定更准"，措辞按 Codex 复核收紧）**：
- **任务包契约自足**：冷 agent 仅凭 TASK.md + EVIDENCE + 帧即可独立产出合规 RESULT。
- **隔离产生一致且独立的判断**：两 agent 互不通气却都判 ACCEPTED_WITH_RISK，并都用参照物锚定法**独立确认**朝向盲点未复发（窗在画左、人物真转向窗、非背光误读）。
- **隔离扒得更深（记忆稀释缓解的实证）**：两 agent 都**独立**揪出 frame_audit 的 `nearest_fallback` 把窗外真切点(~2.67s,score22.4)回退到声明 4.0s 并判 `within_tolerance=true` = **确定性闸自证误绿**；而我（Orchestrator 单上下文）只把它当"历史已接受风险"轻带——独立上下文没有那层先入框架，反而当工具盲点挖了出来。
- **三个发现（Codex round-2 复核确认，已折入契约）**：
  - ①TASK.md `allowed_writes`=RESULT.md 但实际写 RESULT.agentB.md → **§4 加 `output_path` 钉死实际输出文件**（角色目录式 part_b/RESULT.md）。
  - ②frame_audit `nearest_fallback`：声明边界邻域无峰时回退最近采样判容差内（U03 实测：唯一显著峰 2.667s/score 22.408，声明边界 4.0s 回退到 score 0.017 判 within_tolerance），**掩盖窗外真切点错位约 1.3s**。应改为产 `BOUNDARY_REVIEW_REQUIRED` / `unmatched_significant_spike` / `suspected_undeclared_cut` 复核信号（**非硬 FAIL**）——候选 frame_audit 改进给 Codex；实现后 §9 归一表补对应 lane。**✅ Codex 已落地**（共享 frame_audit `scene_diff.boundary_review_signal`，"仅提示 Part B、不改最终状态"），**orchestrator 已接**（parta 捕获 + merge 软信号段），端到端验证 U03 触发 BOUNDARY_REVIEW_REQUIRED 而 verdict 不变（见 §18 交叉检查 round）。
  - ③`锁定账本.dryrun.json` 带 UTF-8 BOM（PowerShell `Out-File utf8` 所致），Python `json.load(utf-8)` 报错 → **§10 已规定账本/任务包 JSON 无 BOM UTF-8 或读端 utf-8-sig**。
- **仍待**：有宽度的真实收益实跑等 Clip4-32 生成；§9 的 BOUNDARY_REVIEW lane 待 Codex 实现 frame_audit 信号后补。

---

## 18 · v0.1 落地：确定性机制层（可执行，2026-06-18）

确定性 Orchestrator 职责已固化为工具 **`tools\gate10-orchestrator\orchestrate_gate10.py`**（Claude 主笔，待 Codex 交叉检查；不修改共享 frame_audit）。LLM 判断层（Part B/C/Boundary 的 RESULT）仍由 worker(agent/人) 产。

- **子命令**：`init`（脚手架+锁定账本，算 sha256，**无 BOM**）/ `parta`（批量调 frame_audit，记 effective_status/floor/det，账本补 part_a_manifest，`--reuse` 不重抽帧）/ `tasks`（生成 TASK.md，钉 sha + `output_path=part_b/RESULT.json`）/ `merge`（schema→provenance(STALE)→确定性地板(保 issue_class)→状态归一→边界(端点FAIL自动PENDING)→返修折叠→单写 MERGE_REPORT + 回写锁定状态）。
- **RESULT 改 JSON sidecar**（落地精化）：worker 产 `part_b/RESULT.json`（机读，合并闸只读结构化字段），§5 的 md 仅作人读镜像。
- **本机测试通过**（`c:\tmp\gate10_orch_test\`，复用 dry-run manifest）：init/parta/tasks/merge 全跑通；merge 正确产出——U05 故意钉错 sha → **屏障① STALE 拦截**（pin deadbeef…≠账本 bc85…）、U01/U02 地板 FAIL→REJECTED(保 TECH_SPEC)、U03 LOCKED_WITH_RISK、U04 LOCKED_PASS、Clip1_Clip2 边界**自动 BOUNDARY_PENDING**、返修折叠、整片 FILM_BLOCKED；**锁定账本无 BOM、Python 普通 utf-8 读取成功**（BOM 坑已修）。
- **未自动化**：worker 的 RESULT.json 仍由 agent/人写（设计本意：先文件约定，后自动 spawn）。

### 交叉检查 round（2026-06-18，双方修改后）
- **Codex 改共享 frame_audit**：加 `scene_diff.boundary_review_signal`（`BOUNDARY_REVIEW_REQUIRED`/`CLEAR`，nearest_fallback 用了但窗外有显著峰即标，"仅提示 Part B、不改最终状态"）+ 更新其树 post-gen/phase9-repair 文档。**未建平行 orchestrator**（本工具 Claude 独家）。
- **向后兼容 PASS**：新 frame_audit 仍输出 `effective_status`/`visual_verdict_floor`/`deterministic_review_policy.status`/`frame_count`，orchestrator parta/merge 不受影响（本机验证）。
- **orchestrator 已接新信号**：parta 捕获 `scene_diff.boundary_review_signal.status`，merge 新增「软信号·切点复核」段（**不改 verdict**）。端到端验证：U03（2.67s 真切点）→ `cut=BOUNDARY_REVIEW_REQUIRED` 贯穿 manifest→parta→merge，最终 verdict 仍 ACCEPTED_WITH_RISK（软信号未污染裁定）。
- **结论**：两侧一致、集成点对齐；spawn 发现的 nearest_fallback 误绿已三方闭环（发现→工具信号→orchestrator 接住→验证）。

### 交叉检查 round-2（Codex 复核 orchestrator，4 项全修，2026-06-18）
Codex 复核 orchestrate_gate10.py 发现信号「只到 merge 展示、没闭环到 TASK/worker」+ 3 个健壮性问题，均成立、已修+验证：
- ①**TASK 注入 attention_flags**：tasks 把 `BOUNDARY_REVIEW_REQUIRED` 写进 TASK.md（worker 现在看得到、被要求核真实切点）。验证：U03 TASK 有该 flag，U04 对照 `[]`。
- ②**merge 轻 gate**：有信号但 worker 未回填 `boundary_review_resolved=true` → 该单元升 `REVIEW_REQUIRED`（非硬 FAIL，防被忽略放行）；回填后回正常裁定。验证双向：U03 未回填→REVIEW_REQUIRED→待复核(未锁)，回填 true→ACCEPTED_WITH_RISK→LOCKED_WITH_RISK。
- ③**--reuse 检字段**：旧 manifest 缺 `scene_diff.boundary_review_signal` → 强制重跑 Part A（防信号消失，正是先前 cut=None 的根因）。
- ④**subprocess utf-8**：`encoding="utf-8", errors="replace"`，修 Windows GBK 解码异常。
- 连带：新增 `REVIEW_REQUIRED` 锁态（待复核·未锁）+ 整片放行阈收紧到"任一单元 ≥REVIEW_REQUIRED 即不放行"。py_compile/min flow 验证通过。**信号闭环 manifest→parta→TASK→worker→merge 完成。**
