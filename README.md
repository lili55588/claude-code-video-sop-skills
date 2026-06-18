# claude-code-video-sop-skills

即梦 seedance2.0「长视频创作」全流程 Claude Code 技能 + 配套工具 + 视觉验收体系规格。

把 Claude Code / Codex 当成即梦 AI agent 的「导演大脑」，覆盖 Phase 1–9：创意发散 → 内容大纲 → 剧本 → 素材挖掘 → 分镜设计 → 比例确认 → 参考素材生成 → 分镜并行生视频 → 剪辑成片。

## 目录

```
skills/video-sop/        即梦长视频创作全流程技能（SKILL.md + references/ + scripts/）
tools/video-frame-audit/        闸10 成片逐帧视觉验收工具（ffmpeg/ffprobe 抽帧+差分+分镜锚定，摆证据不判分）
tools/image-asset-audit/        闸2b/9 图片 Part A 证据工具（分辨率/比例/格式/宫格分割，摆证据不判分）
tools/xiaoyunque-video-runner/  小云雀/Pippit 提交 runner（已确认 Phase8 Prompt 的外部提交器）
docs/                    闸10 规格草案 + 双引擎协作规则（COLLABORATION/CLAUDE/AGENTS）
```

## 上游视觉验收体系（本仓核心新增）

把严苛的成片自检往上游搬，挡在源头——**早失败便宜**：一张错字/跑脸的 P7 图会污染下游每个宫格(P8.5)和成片(P9)。

- **VVK 视觉验收内核**（`skills/video-sop/references/visual-verification-kernel.md`）：三层（确定性摆证据 + 视觉主判 + 对抗性独立盲审）+ 反糊弄协议 + 参照锚定法 + 返修决策层，被三个视觉闸共用：
  - **闸2b**（P7 角色/场景/道具/产品图）
  - **闸9**（P8.5 关键帧/分镜宫格）
  - **闸10**（P9 成片逐帧）— `references/phase9-frame-audit.md`
- 确定性证据按 `issue_class` 分类（`EVIDENCE_GAP`→`AUDIT_INCOMPLETE` / `TECH_SPEC_BLOCKED`→`FAIL_BLOCKED` 容器层先 / `CONTENT_FAIL`→`FAIL_BLOCKED` 重生成）；软信号（OCR/人脸数/水印/感知哈希）只提示风险、需视觉确认。
- **权威锚定链** `P4素材清单→P7参考图→P8.5关键帧→P8 Prompt→P9成片` + 依赖记录 cascade 复检。
- **锁定状态** `LOCKED_PASS / LOCKED_WITH_RISK / REJECTED / AUDIT_INCOMPLETE`——只有锁定的图能被下游引用。
- **参照物锚定法**：判朝向先锚固定参照物（窗/门/桌），判正对/背对/侧对——被参照物的光照亮 ≠ 朝向它。

## 工具用法

成片逐帧视觉验收（闸10）：
```powershell
python tools/video-frame-audit/frame_audit.py "{项目}_视频生成Prompt集.md" --clip 2 --video "成片.mp4" --audit-profile final --out-dir "逐帧自检/Clip2"
```
图片证据（闸2b/9）：
```powershell
python tools/image-asset-audit/image_asset_audit.py --image "角色图.png" --profile phase7 --expected-ratio 16:9 --out-dir "out"
```

> 工具只摆证据、不判分；最终判定由视觉层（人/视觉模型）按矩阵写证据。

## 安全

- 不含任何 API key；小云雀 runner 的 key 只从环境变量 `XYQ_ACCESS_KEY` 或本地 key 文件读取，绝不入仓。
- 路径示例为 Windows 本机路径，按需替换。

## 协作

Claude × Codex 双引擎协作，规则见 `docs/COLLABORATION.md`。两引擎各维护自己的 skill 树，工具为共享实现。
