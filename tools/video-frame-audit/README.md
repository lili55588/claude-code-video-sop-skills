# Video Frame Audit

通用 Gate10 成片逐帧视觉验收证据工具。

这个目录属于 video-sop 通用层，不属于小云雀/Pippit 提交器。它适用于即梦、小云雀/Seedance，以及任意生成视频。

## 作用

`frame_audit.py` 只做确定性证据准备，不下人物、道具、站位是否正确的视觉结论：

- 读取 Phase8 Prompt 集并定位指定 Clip。
- 解析分镜时间段、Prompt 原话、引用槽位。
- `ffprobe` 核对时长、fps、分辨率、display aspect ratio。
- 原生帧率全帧落盘。
- 生成 contact sheet、分镜入/中/出帧、切点帧对、差分疑点帧。
- 运行 `ffmpeg scdet` 生成差分/场景突变路由证据。
- 生成 `frame_audit_manifest.json` 和审片报告模板。

视觉判定必须由审片报告完成，状态为：

- `AUDIT_INCOMPLETE`
- `PASS`
- `ACCEPTED_WITH_RISK`
- `FAIL_BLOCKED`
- `REGENERATED_PASS`

## 确定性硬闸

工具状态 `AUDIT_READY` 只代表全帧、contact sheet、差分、分镜映射等证据齐了，不代表 Clip 可放行。

如果 `deterministic_checks.duration.status` 或 `deterministic_checks.ratio.status` 是 `RISK_OR_FAIL_REVIEW`，工具会在 manifest 写入：

```json
"deterministic_review_policy": {
  "status": "DETERMINISTIC_FAIL_BLOCKED_REQUIRED",
  "visual_verdict_floor": "FAIL_BLOCKED"
}
```

视觉审片层不得用 `AUDIT_READY` 覆盖这个硬风险。除非用户明确接受“仅测试风险”，最终报告必须按 `FAIL_BLOCKED` 处理。

## 容差档

默认是成片档：

```powershell
--audit-profile final
```

- final：display ratio 默认相对容差 `0.01`。
- test：低分辨率/接口测试档，display ratio 默认相对容差 `0.03`，必须显式传 `--audit-profile test`。
- 也可以用 `--ratio-tolerance` 明确覆盖，但报告必须记录这是用户接受的测试风险或生产标准。

## scdet 量纲

`ffmpeg scdet` 的 `lavfi.scd.score` 是 raw score points，不是 0-1 概率。默认阈值：

```powershell
--scene-threshold 5.0
```

差分结果只用于把注意力路由到疑点帧和真实切点，不能替代视觉审片。

声明切点附近的真实切点定位规则：

- 在 `[declared_time - boundary_tolerance, declared_time + boundary_tolerance]` 内优先取最高的显著 `scdet` 峰值。
- 邻域内没有显著峰值时才回退到最近时间点。
- 这样可以避免“声明时间点附近的小 blip”盖掉更强的早切/晚切真实峰值。

## 参照物锚定辅助

工具会从每个分镜 Prompt 中抽取参照物候选和朝向/视线句子，写入 manifest 与报告模板：

- `orientation_anchor_review.anchors`
- `orientation_anchor_review.excluded_non_orientation_anchors`
- `orientation_anchor_review.orientation_clauses`

它只提示审片人核对窗、门、桌、床、楼梯、货架、柜、墙、讲台、舞台、车辆、产品、具名目标角色等稳定参照物，不判断画面是否正确。镜头/机位/运镜/景别/画面等相机语言，以及铅笔/笔/杯/手机/钥匙/纸/伞等手持可动小道具，不进入朝向参照物锚点；它们仍要在镜头语言或道具连续性维度检查。视觉层必须先定位参照物在画面中的方位，再判人物正对/背对/侧对；被光打亮不等于朝向该参照物。

## 返修决策

报告模板包含 `返修决策` 表，用来把每个 Gate10 问题路由到最小处理路径。工具只摆字段，不自动下返修结论。

默认顺序：

1. `AUDIT_INCOMPLETE` 先修证据，不动视频。
2. 同一 Clip 同时有内容错和容器错时，先修内容，再批量处理水印、比例、裁切等容器问题。
3. 容器问题由 Phase9/video-auto-edit 处理，但裁切、遮罩、换切点不得损伤脸、手、关键道具、口型、画面重心、动作落点或剧情连续。
4. 局部剪掉前必须证明该段不承重；剪辑只能真修复，不能遮盖内容错。
5. 重生成预算：同 Prompt 重抽 <=2；Prompt 修版重生成 <=2；仍失败则升级到 Phase5 blocking 修复、拆分分镜或重拆 Clip。

修后复检范围：重生成=该 Clip 全闸10；重剪/换切点=切点对+时长+音画同步；跨镜成对=两 Clip+边界；容器批量=全片 ffprobe+抽样视觉复核。

## 用法

```powershell
python C:\Users\Administrator\Desktop\tools\video-frame-audit\frame_audit.py `
  "C:\Users\Administrator\Desktop\claude长视频创作\重返那年盛夏\重返那年盛夏_视频生成Prompt集.md" `
  --clip 2 `
  --video "C:\Users\Administrator\Desktop\claude长视频创作\重返那年盛夏\pippit_outputs\v03c76g10004d8p6te2ljhtfluat22og.mp4" `
  --project-dir "C:\Users\Administrator\Desktop\claude长视频创作\重返那年盛夏"
```

低分辨率接口测试可显式使用：

```powershell
--audit-profile test
```

输出默认写入：

```text
{项目目录}\video_audit\Clip{N}_{timestamp}\
```

## Windows 规则

- 子进程输出统一按 bytes 捕获，再按 `utf-8-sig`、`utf-8`、`gb18030` 容错解码。
- manifest 使用 ASCII-safe JSON，避免 PowerShell 默认解码把中文路径破坏成非法 JSON。
- 工具不调用小云雀 CLI，不读取 `XYQ_ACCESS_KEY`，不提交生成。
