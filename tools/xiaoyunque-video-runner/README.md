# Xiaoyunque Video Runner

独立的小云雀 / Pippit / Seedance 视频生成执行器。

这个目录只负责把已经确认、已经校验的 video-sop Phase8 Clip Prompt 提交给小云雀，并记录查询/下载结果。它不是即梦 Prompt 规则的一部分，也不参与 Phase1-8 创作、拆镜、改写、审片或验收规则设计。

## 启动条件

只在用户明确要求以下动作时使用：

- 用小云雀生成
- 用 Pippit CLI 生成
- 用 `seedance2.0_vision` / `seedance2.0_direct` 直接提交
- 查询或下载小云雀生成结果

普通 video-sop / 即梦 Prompt 生成、Phase8.5 宫格锚点、即梦网页上传顺序，不自动启动本脚本。

## Dry Run

先检查 Prompt、Clip、参考图解析，不提交生成：

```powershell
python C:\Users\Administrator\Desktop\tools\xiaoyunque-video-runner\xiaoyunque_phase8_runner.py `
  "C:\Users\Administrator\Desktop\claude长视频创作\重返那年盛夏\重返那年盛夏_视频生成Prompt集.md" `
  --clip 1 `
  --model seedance2.0_vision `
  --resolution 480p
```

## Submit

真正提交小云雀生成：

```powershell
python C:\Users\Administrator\Desktop\tools\xiaoyunque-video-runner\xiaoyunque_phase8_runner.py `
  "C:\Users\Administrator\Desktop\claude长视频创作\重返那年盛夏\重返那年盛夏_视频生成Prompt集.md" `
  --clip 1 `
  --submit `
  --poll `
  --model seedance2.0_vision `
  --resolution 480p `
  --access-key-file "C:\Users\Administrator\Desktop\xiaoyunqkey.txt"
```

## Runner Outputs

本 runner 只在项目目录下写入：

- `pippit_runs\`：dry-run/submit/query/download manifest 与日志
- `pippit_outputs\`：下载的视频结果

它不改写 `{项目名}_视频生成Prompt集.md`，不改写参考素材，不改写 video-sop 规则，不生成逐帧审片报告。

## Gate 10 After Download

视频下载后，按共享 video-sop Gate10 工具做逐帧验收证据准备：

```powershell
python C:\Users\Administrator\Desktop\tools\video-frame-audit\frame_audit.py `
  "C:\Users\Administrator\Desktop\claude长视频创作\重返那年盛夏\重返那年盛夏_视频生成Prompt集.md" `
  --clip 2 `
  --video "C:\Users\Administrator\Desktop\claude长视频创作\重返那年盛夏\pippit_outputs\生成视频.mp4" `
  --project-dir "C:\Users\Administrator\Desktop\claude长视频创作\重返那年盛夏"
```

审片规则以 Codex video-sop 的 `references/post-generation-video-audit.md` 为准。小云雀 runner 只把生成视频路径交给 Gate10，不下视觉结论。

## Windows 稳定性规则

- Python 调用 CLI 时必须先捕获 stdout/stderr 原始 bytes，再由脚本用 `utf-8-sig`、`utf-8`、`gb18030` 依次容错解码；不要使用 `subprocess.run(..., text=True)` 依赖 Windows 默认编码。
- Windows 上不要从 Python 直接调用 npm 生成的 `pippit-tool-cli.cmd` shim。脚本会自动解析并改走 `node ...\@pippit-dev\cli\scripts\run.js`，避免长中文 Prompt 和参数被 `.cmd` 包装层吞掉。
- `XYQ_ACCESS_KEY` 只允许来自环境变量或 `--access-key-file`，不要通过命令行明文参数传入，避免进入终端历史或 manifest。
- 如果提交后脚本崩在查询/记录阶段，先检查 `pippit_runs\`、CLI 日志和已有 `thread_id/run_id`，不要立刻重复提交。

## 边界

- Phase8 Prompt 必须先是已确认内容；脚本不做剧情重写。
- 参考图按每个 Clip 的 `@图片N` 顺序提交。
- `XYQ_ACCESS_KEY` 只从环境变量或 key 文件读取，不打印、不写入日志。
- 小云雀失败时，只记录错误；是否重抽、修 Prompt、回滚 Phase5/7，仍按 video-sop Phase9 判责树决定。
