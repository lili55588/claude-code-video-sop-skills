# gate10-orchestrator v0.1（确定性机制层）

把「多Agent并发编排层_v0.1_设计草案.md」里 Orchestrator 的**确定性**职责固化成可执行工具。
LLM 视觉判断（Part B / Part C / Boundary 的 RESULT）仍由 worker(agent/人) 写入；本工具不做视觉判分、**不修改共享 frame_audit.py**（仅子进程调用）。

> 状态：Claude 主笔 v0.1，已在 5 单元 dry-run 集上 init/parta/tasks/merge 全跑通；**待 Codex 交叉检查**。

## 流程
```
init   → 建脚手架 + 锁定账本(provenance, 无BOM, 算 video/prompt sha256)
parta  → 每单元跑 frame_audit → EVIDENCE/，记 effective_status/floor/det，账本补 part_a_manifest
tasks  → 每单元生成 TASK.md（钉 video sha + manifest sha + output_path=part_b/RESULT.json）
[worker：agent/人 按 TASK 写 units/<id>/part_b/RESULT.json；高风险写 part_c/RESULT.json；边界 boundary/<id>/RESULT.json；返修 repair/RESULT.json]
merge  → schema校验 + provenance复核(屏障①STALE) + 确定性地板(保issue_class) + 状态归一 + 边界(端点FAIL→PENDING) + 返修折叠 → 单写 MERGE_REPORT.md + 回写锁定状态
```

## 用法
```bash
python orchestrate_gate10.py init  --job-dir <job> --units units.json
python orchestrate_gate10.py parta --job-dir <job> [--reuse]   # --reuse: 已有 manifest 不重抽帧
python orchestrate_gate10.py tasks --job-dir <job>
# ……worker 写各自 RESULT.json……
python orchestrate_gate10.py merge --job-dir <job>
```

## units.json
```json
{
  "project": "项目名",
  "prompt_file": "...\\_视频生成Prompt集.md",
  "audit_profile": "final",
  "units": [{"id":"U01_Clip1","clip":1,"video":"...mp4","risk":"low|med|high"}],
  "boundaries": [{"id":"Clip1_Clip2","left":"U01_Clip1","right":"U02_Clip2"}]
}
```

## worker 必产 `part_b/RESULT.json`（合并闸只读结构化字段）
```json
{
  "unit_id": "U01_Clip1", "role": "vvk_part_b_judge",
  "input_pins": {"video_sha256": "<必须等于账本，否则 STALE_RESULT 重派>"},
  "verdict": "PASS|REGENERATED_PASS|ACCEPTED_WITH_RISK|REVIEW_REQUIRED|AUDIT_INCOMPLETE|FAIL_BLOCKED",
  "issue_class": "EVIDENCE_GAP|TECH_SPEC_BLOCKED|CONTENT_FAIL|ACCEPTABLE_RISK|null",
  "severity": "...", "confidence": 0.0, "findings": [], "risk_items": [],
  "boundary_review_resolved": true
}
```
- `boundary_review_resolved`：**仅当 TASK.md 的 `attention_flags` 含 `BOUNDARY_REVIEW_REQUIRED` 时必填**（worker 已核真实切点 vs 声明分镜）。缺或 false → merge 把该单元升 `REVIEW_REQUIRED`（非硬 FAIL，防忽略放行）。
```
边界 `boundary/<id>/RESULT.json`：`{"boundary_status":"PASS|FAIL_BLOCKED|BOUNDARY_PENDING"}`（端点任一 FAIL 时 merge 自动 PENDING，可不写）。
返修 `repair/RESULT.json`：`{"items":[{"unit","issue_class","recommended_fix","minimum_rollback_layer"}]}`。

## 合并规则（与草案 §7/§8/§9 一致）
- **确定性地板优先且保 issue_class**：Part A 的 `visual_verdict_floor=FAIL_BLOCKED` 或 `DETERMINISTIC_FAIL_BLOCKED_REQUIRED` → 最终至少 FAIL_BLOCKED + `TECH_SPEC_BLOCKED`（容器修先，非内容 regen）；`DETERMINISTIC_UNKNOWN_REVIEW_REQUIRED` → REVIEW_REQUIRED；`AUDIT_INCOMPLETE` → 同。worker 判断不能把地板风险说没。
- **屏障① provenance**：`RESULT.input_pins.video_sha256 ≠ 账本` → `STALE_RESULT` 作废重派。
- **边界**：端点任一最终 FAIL → `BOUNDARY_PENDING`（不出误导性 seam PASS）。
- **整片**：任一 FAIL_BLOCKED/STALE/AUDIT_INCOMPLETE → `FILM_BLOCKED`。

## 编码约定（吸收 dry-run 实测）
- 写：UTF-8 **无 BOM**（Python `open('w')` 默认）。
- 读：一律 `utf-8-sig`，容忍历史 BOM（PowerShell `Out-File utf8` 会写 BOM）。

## 软信号·切点复核（已接 Codex frame_audit + 闭环到 TASK/worker）
- **parta** 捕获 `scene_diff.boundary_review_signal.status`（缺字段的旧 manifest 会被 `--reuse` 强制重跑，避免信号消失）。
- **tasks** 把 `BOUNDARY_REVIEW_REQUIRED` 注入 TASK.md 的 `attention_flags`，要求 worker 核真实切点并回填 `boundary_review_resolved`。
- **merge** 出「软信号·切点复核」段；**轻 gate**：信号存在但 worker 未回填 `boundary_review_resolved=true` → 该单元升 `REVIEW_REQUIRED`（非硬 FAIL）；回填后回到正常裁定。整条 `manifest→parta→TASK→worker→merge` 已闭环。

## 已知待办
- 自动 spawn worker（当前 worker 由 agent/人 手动写 RESULT.json）。
- parta 重跑会重复 append `part_a_manifest` authority（merge 按 id 去重不影响结果，待做幂等）。
