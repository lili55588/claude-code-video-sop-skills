#!/usr/bin/env python3
"""Gate10 并发编排器 v0.1（确定性机制层）。

把「多Agent并发编排层_v0.1_设计草案.md」里 Orchestrator 的**确定性**职责固化成可执行工具：
脚手架 / 锁定账本(provenance) / 批量 Part A / 任务包生成 / 合并闸（schema+provenance+确定性地板+状态归一+边界+返修折叠）。

不做 LLM 视觉判断——Part B / Part C / Boundary 的 RESULT 由 worker(agent/人) 写入。
不修改共享 frame_audit.py（仅子进程调用）。

JSON I/O 约定（吸收 dry-run 实测发现）：
- 写：UTF-8 **无 BOM**（Python open 'w' 默认即无 BOM）。
- 读：一律 utf-8-sig，容忍历史 BOM 文件。

子命令：init / parta / tasks / merge
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

FRAME_AUDIT = r"C:\Users\Administrator\Desktop\tools\video-frame-audit\frame_audit.py"
LEDGER_NAME = "锁定账本.json"
PARTA_STATE = "_parta_state.json"

# 状态严重度排序（高=更严，合并取更严）
VERDICT_RANK = {
    "PASS": 0, "REGENERATED_PASS": 0,
    "ACCEPTED_WITH_RISK": 1,
    "REVIEW_REQUIRED": 2,
    "AUDIT_INCOMPLETE": 3,
    "STALE_RESULT": 3,
    "FAIL_BLOCKED": 4,
}
RESULT_REQUIRED_FIELDS = ["unit_id", "role", "input_pins", "verdict"]


# ---------- 编码安全 I/O ----------
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> Any:
    # utf-8-sig 容忍 BOM（dry-run 实测：PowerShell Out-File utf8 会写 BOM）
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def dump_json(obj: Any, path: Path) -> None:
    # 无 BOM；ensure_ascii=False 让中文路径可读（消费端为本工具，统一 utf-8-sig 读）
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def write_text(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def find_manifest(evidence_dir: Path) -> Path | None:
    hits = sorted(evidence_dir.rglob("*manifest*.json"))
    return hits[0] if hits else None


# ---------- init ----------
def cmd_init(args: argparse.Namespace) -> int:
    spec = load_json(Path(args.units))
    job = Path(args.job_dir)
    (job / "repair").mkdir(parents=True, exist_ok=True)
    for u in spec["units"]:
        (job / "units" / u["id"] / "EVIDENCE").mkdir(parents=True, exist_ok=True)
        (job / "units" / u["id"] / "part_b").mkdir(parents=True, exist_ok=True)
        (job / "units" / u["id"] / "part_c").mkdir(parents=True, exist_ok=True)
    for b in spec.get("boundaries", []):
        (job / "boundary" / b["id"]).mkdir(parents=True, exist_ok=True)

    prompt = Path(spec["prompt_file"])
    authorities = [{
        "authority_id": "视频生成Prompt集", "type": "prompt", "path": str(prompt),
        "sha256": sha256(prompt), "lock_state": "snapshot", "source_phase": "P8",
    }]
    for u in spec["units"]:
        v = Path(u["video"])
        if not v.exists():
            print(f"[WARN] video missing: {v}")
            continue
        authorities.append({
            "authority_id": u["id"], "type": "clip_video", "path": str(v),
            "sha256": sha256(v), "lock_state": "snapshot", "source_phase": "P9",
        })
    ledger = {"project": spec["project"], "generated_by": "orchestrate_gate10/init",
              "encoding": "utf-8-no-bom", "authorities": authorities}
    dump_json(ledger, job / LEDGER_NAME)
    dump_json(spec, job / "_units.json")
    print(f"[init] job={job}  units={len(spec['units'])}  authorities={len(authorities)}  ledger={LEDGER_NAME}(no-BOM)")
    return 0


# ---------- parta ----------
def cmd_parta(args: argparse.Namespace) -> int:
    job = Path(args.job_dir)
    spec = load_json(job / "_units.json")
    ledger = load_json(job / LEDGER_NAME)
    prompt = spec["prompt_file"]
    profile = spec.get("audit_profile", "final")
    state: dict[str, Any] = {}
    for u in spec["units"]:
        evid = job / "units" / u["id"] / "EVIDENCE"
        mf = find_manifest(evid)
        reuse_ok = False
        if mf and args.reuse:
            try:  # 仅复用含新信号字段的 manifest；缺则强制重跑（旧 manifest 会让 boundary_review 消失）
                reuse_ok = load_json(mf).get("scene_diff", {}).get("boundary_review_signal") is not None
            except Exception:
                reuse_ok = False
        if reuse_ok:
            print(f"[parta] {u['id']}: reuse existing manifest")
        else:
            if mf and args.reuse:
                print(f"[parta] {u['id']}: 旧 manifest 缺 scene_diff.boundary_review_signal → 强制重跑 Part A")
            cmd = [sys.executable, FRAME_AUDIT, prompt, "--clip", str(u["clip"]),
                   "--video", u["video"], "--audit-profile", profile, "--out-dir", str(evid)]
            # Windows: 显式 utf-8 解码，避免 frame_audit 中文 stdout 触发 GBK 解码异常
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                print(f"[parta] {u['id']}: frame_audit FAILED\n{r.stdout}\n{r.stderr}")
                state[u["id"]] = {"part_a": "ERROR"}
                continue
            mf = find_manifest(evid)
        m = load_json(mf)
        p = m.get("deterministic_review_policy", {})
        rec = {
            "manifest_path": str(mf), "manifest_sha256": sha256(mf),
            "effective_status": m.get("effective_status"),
            "visual_verdict_floor": m.get("visual_verdict_floor"),
            "deterministic_status": p.get("status"),
            "frame_count": m.get("frame_count"),
            # Codex 共享工具新增软信号（仅提示 Part B 核真实切点，不改最终状态）
            "boundary_review": m.get("scene_diff", {}).get("boundary_review_signal", {}).get("status"),
        }
        state[u["id"]] = rec
        ledger["authorities"].append({
            "authority_id": f"{u['id']}_partA", "type": "part_a_manifest",
            "path": rec["manifest_path"], "sha256": rec["manifest_sha256"],
        })
        print(f"[parta] {u['id']}: eff={rec['effective_status']} floor={rec['visual_verdict_floor']} det={rec['deterministic_status']} cut={rec['boundary_review']}")
    dump_json(state, job / PARTA_STATE)
    dump_json(ledger, job / LEDGER_NAME)
    return 0


# ---------- tasks ----------
TASK_TMPL = """job_id:          {job_id}
agent_role:      vvk_part_b_judge
unit_id:         {uid}
phase_gate:      P9/Gate10
matrix_profile:  gate10
risk:            {risk}
authority_chain: [P4素材清单, P7参考图, P8:Clip{clip}Prompt, P9:本视频]
input_files:
  - path:        {video}
    sha256:      {vsha}
    lock_state:  snapshot
  - manifest_path:   {mpath}
    manifest_sha256: {msha}
output_path:     units/{uid}/part_b/RESULT.json   # 钉死实际输出；allowed_writes 必须等于它
allowed_writes:  [units/{uid}/part_b/RESULT.json]
allowed_reads:   [input_files, EVIDENCE/, authority_chain 文件, gate10 矩阵]
required_checks: [分镜对位, 朝向(参照物锚定), 站位, 道具承载面, 跨镜, 身份, 时长比例]
attention_flags: {attention}
do_not_do:       [改剧情, 改Prompt, 写MERGE_REPORT, 改锁定状态, 读其他worker结论]
"""


def cmd_tasks(args: argparse.Namespace) -> int:
    job = Path(args.job_dir)
    spec = load_json(job / "_units.json")
    ledger = {a["authority_id"]: a for a in load_json(job / LEDGER_NAME)["authorities"]}
    state = load_json(job / PARTA_STATE)
    for u in spec["units"]:
        a = ledger.get(u["id"], {})
        pa = state.get(u["id"], {})
        attention = ("[BOUNDARY_REVIEW_REQUIRED: 必须核真实切点 vs 声明分镜，"
                     "并在 RESULT.json 回填 boundary_review_resolved=true/false + 对应 finding]"
                     if pa.get("boundary_review") == "BOUNDARY_REVIEW_REQUIRED" else "[]")
        txt = TASK_TMPL.format(
            job_id=f"gate10_{spec['project']}", uid=u["id"], risk=u.get("risk", "med"),
            clip=u["clip"], video=u["video"], vsha=a.get("sha256", "?"),
            mpath=pa.get("manifest_path", "?"), msha=pa.get("manifest_sha256", "?"),
            attention=attention,
        )
        write_text(job / "units" / u["id"] / "TASK.md", txt)
    print(f"[tasks] {len(spec['units'])} 个 TASK.md 已生成（output_path 钉死 part_b/RESULT.json）")
    return 0


# ---------- merge ----------
def floor_from_parta(pa: dict[str, Any]) -> tuple[str, str | None, str]:
    """返回 (floor_verdict, issue_class, 说明)。保 issue_class。"""
    eff = pa.get("effective_status")
    det = pa.get("deterministic_status")
    floor = pa.get("visual_verdict_floor")
    if eff == "AUDIT_INCOMPLETE":
        return "AUDIT_INCOMPLETE", "EVIDENCE_GAP", "Part A 证据不全"
    if floor == "FAIL_BLOCKED" or det == "DETERMINISTIC_FAIL_BLOCKED_REQUIRED":
        return "FAIL_BLOCKED", "TECH_SPEC_BLOCKED", "确定性地板（容器修先）"
    if det == "DETERMINISTIC_UNKNOWN_REVIEW_REQUIRED":
        return "REVIEW_REQUIRED", None, "确定性未知，待补规格"
    return "PASS", None, "无地板约束"


def cmd_merge(args: argparse.Namespace) -> int:
    job = Path(args.job_dir)
    spec = load_json(job / "_units.json")
    ledger = {a["authority_id"]: a for a in load_json(job / LEDGER_NAME)["authorities"]}
    state = load_json(job / PARTA_STATE)
    rows, finals = [], {}

    for u in spec["units"]:
        uid = u["id"]
        rp = job / "units" / uid / "part_b" / "RESULT.json"
        a = ledger.get(uid, {})
        floor_v, floor_ic, floor_note = floor_from_parta(state.get(uid, {}))
        if not rp.exists():
            finals[uid] = "AUDIT_INCOMPLETE"
            rows.append((uid, "—", "MISSING_RESULT", floor_v, "AUDIT_INCOMPLETE", floor_ic, "worker 未交 RESULT"))
            continue
        res = load_json(rp)
        # schema 校验
        missing = [k for k in RESULT_REQUIRED_FIELDS if k not in res]
        if missing:
            finals[uid] = "AUDIT_INCOMPLETE"
            rows.append((uid, res.get("verdict", "?"), f"RESULT_INVALID(缺{','.join(missing)})", floor_v, "AUDIT_INCOMPLETE", floor_ic, "schema 不合格→重派"))
            continue
        # provenance 复核（屏障①）
        pin = (res.get("input_pins") or {}).get("video_sha256", "")
        if pin != a.get("sha256"):
            finals[uid] = "STALE_RESULT"
            rows.append((uid, res.get("verdict"), "STALE_RESULT", floor_v, "STALE→重派", None, f"pin {pin[:12]}≠账本 {a.get('sha256','')[:12]}"))
            continue
        # 确定性地板优先（取更严，保 issue_class）
        wv = res.get("verdict", "PASS")
        if VERDICT_RANK.get(floor_v, 0) >= VERDICT_RANK.get(wv, 0):
            final_v, final_ic = floor_v, floor_ic or res.get("issue_class")
        else:
            final_v, final_ic = wv, res.get("issue_class")
        # 轻 gate：有切点复核信号但 worker 未回填 boundary_review_resolved=true → 至少 REVIEW_REQUIRED（非硬 FAIL，防被忽略放行）
        note = floor_note
        if state.get(uid, {}).get("boundary_review") == "BOUNDARY_REVIEW_REQUIRED" and res.get("boundary_review_resolved") is not True:
            if VERDICT_RANK["REVIEW_REQUIRED"] > VERDICT_RANK.get(final_v, 0):
                final_v = "REVIEW_REQUIRED"
            note += " ⚑切点复核未回填→REVIEW_REQUIRED"
        finals[uid] = final_v
        lock = {"PASS": "LOCKED_PASS", "REGENERATED_PASS": "LOCKED_PASS",
                "ACCEPTED_WITH_RISK": "LOCKED_WITH_RISK", "REVIEW_REQUIRED": "待复核(未锁)"}.get(final_v, "REJECTED")
        rows.append((uid, wv, "OK", floor_v, f"{final_v} → {lock}", final_ic, note))

    # 边界（任一端 FAIL → BOUNDARY_PENDING，不读 worker 也能定）
    brows = []
    for b in spec.get("boundaries", []):
        lf, rf = finals.get(b["left"]), finals.get(b["right"])
        if VERDICT_RANK.get(lf, 0) >= 4 or VERDICT_RANK.get(rf, 0) >= 4:
            brows.append((b["id"], f"{b['left']}({lf}) / {b['right']}({rf})", "BOUNDARY_PENDING（端点 FAIL）"))
        else:
            brp = job / "boundary" / b["id"] / "RESULT.json"
            bs = load_json(brp).get("boundary_status", "MISSING") if brp.exists() else "MISSING(待 worker)"
            brows.append((b["id"], f"{b['left']}({lf}) / {b['right']}({rf})", bs))

    # 返修建议折叠
    repair = job / "repair" / "RESULT.json"
    repair_items = load_json(repair).get("items", []) if repair.exists() else []

    blocked = any(VERDICT_RANK.get(v, 0) >= 2 for v in finals.values())  # REVIEW_REQUIRED 及以上不放行
    overall = "FILM_BLOCKED" if blocked else "FILM_RELEASABLE"

    md = [f"# Gate10 MERGE_REPORT — {spec['project']}", "",
          f"- 写入者：Orchestrator（orchestrate_gate10/merge，单写）",
          f"- 单元：{len(spec['units'])}　边界：{len(spec.get('boundaries', []))}　整片：**{overall}**", "",
          "## 逐单元（schema → provenance → 确定性地板(保 issue_class) → 归一）",
          "| 单元 | worker verdict | 校验 | 地板 | 最终 | issue_class | 说明 |",
          "|---|---|---|---|---|---|---|"]
    md += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5] or '—'} | {r[6]} |" for r in rows]
    md += ["", "## 边界", "| 边界 | 端点 | boundary_status |", "|---|---|---|"]
    md += [f"| {b[0]} | {b[1]} | {b[2]} |" for b in brows]

    # 软信号·切点复核（Codex frame_audit boundary_review_signal；不改最终状态，仅提示 Part B）
    br_flags = [u["id"] for u in spec["units"] if state.get(u["id"], {}).get("boundary_review") == "BOUNDARY_REVIEW_REQUIRED"]
    md += ["", "## 软信号·切点复核（frame_audit boundary_review_signal，不改最终状态，仅提示 Part B 核真实切点 vs 声明分镜）"]
    md += [f"- {uid}: BOUNDARY_REVIEW_REQUIRED → Part B 须核真实切点是否偏离声明分镜" for uid in br_flags] or ["- （无）"]

    md += ["", "## 返修建议（折叠自 repair/RESULT.json）"]
    md += [f"- {it.get('unit')}: {it.get('issue_class')} → {it.get('recommended_fix')}" for it in repair_items] or ["- （无）"]
    md += ["", f"## 整片裁定：**{overall}**",
           "任一单元 REVIEW_REQUIRED / AUDIT_INCOMPLETE / STALE / FAIL_BLOCKED 即整片不放行；处理后重跑本闸。"]
    write_text(job / "MERGE_REPORT.md", "\n".join(md) + "\n")

    # 回写锁定状态
    for uid, v in finals.items():
        if uid in ledger:
            ledger[uid]["lock_state"] = {"PASS": "LOCKED_PASS", "ACCEPTED_WITH_RISK": "LOCKED_WITH_RISK", "REVIEW_REQUIRED": "REVIEW_REQUIRED"}.get(v, "REJECTED")
    dump_json({"project": spec["project"], "authorities": list(ledger.values())}, job / LEDGER_NAME)
    print(f"[merge] overall={overall}  MERGE_REPORT.md 已单写（no-BOM）")
    for r in rows:
        print(f"   {r[0]:24} {r[4]}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Gate10 并发编排器 v0.1（确定性机制层）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("init", "parta", "tasks", "merge"):
        sp = sub.add_parser(name)
        sp.add_argument("--job-dir", required=True)
        if name == "init":
            sp.add_argument("--units", required=True, help="units.json 任务规格")
        if name == "parta":
            sp.add_argument("--reuse", action="store_true", help="已有 manifest 则复用、不重抽帧")
    args = ap.parse_args(argv)
    return {"init": cmd_init, "parta": cmd_parta, "tasks": cmd_tasks, "merge": cmd_merge}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
