# 复刻版提示词：从试镜中提取可迁移表演风格

说明：
这是根据 OAK 后续回复整理出的复刻版。目标是把 approved audition 中有效的表演方式提取出来，变成可以贴进正式场景 prompt 的 `ACTING STYLE TO APPLY`。

## 使用场景

当你已经完成角色试镜，并选出一个满意版本后，使用这个提示词。

输入材料：
- approved Seedance prompt
- casting read
- character sheet
- assigned role
- voice triggers
- emotional triggers
- performance notes

输出结果：
- 一段可复制到新场景 prompt 的 acting style direction

## Prompt

Read all provided material before extracting the acting style.

Materials:
- Approved Seedance audition prompt
- Casting Read
- Character Sheet
- User-assigned role
- Voice triggers
- Emotional triggers
- Performance notes

Extract the acting style from the approved audition prompt, but make it character-aware using the Casting Read, Character Sheet, assigned role, voice triggers, emotional triggers, and performance notes.

Do not copy:
- dialogue
- scene
- setting
- costume
- camera setup
- plot
- specific story events
- exact framing
- lighting setup
- color palette
- composition

Do not turn the output into a generic template.

Do not use placeholders.

Do not explain your process.

Focus only on:
- emotional starting state
- restraint level
- vocal tone
- pacing
- silence
- pauses
- verbal fracture
- stutter
- loudness shifts
- breath control
- eye behavior
- facial micro-movements
- body movement
- emotional arc
- what to avoid

Use the approved audition prompt as the main source for:
- movement
- pacing
- delivery rhythm
- silence
- loudness
- performance behavior

Use the Casting Read and Character Sheet to understand:
- psychology
- inner wound
- pressure
- emotional logic
- identity
- behavioral consistency

Use the assigned role to shape:
- energy
- power dynamic
- social position
- dramatic function

Use the voice triggers to refine:
- tone
- texture
- volume
- speech pattern

Output must be concise, cinematic, actor-directable, and ready to paste into another prompt.

Output only in this style:

ACTING STYLE TO APPLY

Write 6-9 concise lines or short paragraphs.

Keep the language specific and character-aware.

Do not use bullet points.

Do not use subheadings.

Do not include context or story summary.

Do not mention the source materials.

Do not copy exact dialogue.

## 中文使用版

请先阅读我提供的全部材料，再提取角色的表演风格。

材料包括：
- 已通过的 Seedance 试镜 prompt
- Casting Read
- Character Sheet
- 用户指定的角色定位
- Voice triggers
- Emotional triggers
- Performance notes

你的任务不是复制试镜视频，也不是复刻原场景。

你的任务是只提取可迁移的表演风格，并让它符合角色本身。

不要复制：
- 原台词
- 原场景
- 原地点
- 原服装
- 原镜头设置
- 原剧情
- 原故事事件
- 原构图
- 原灯光
- 原色彩

不要写成通用模板。

不要使用占位符。

不要解释你的过程。

只关注：
- 情绪起点
- 克制程度
- 声音质感
- 说话节奏
- 沉默
- 停顿
- 语言破裂
- 轻微口吃
- 音量变化
- 呼吸控制
- 眼神行为
- 面部微动作
- 身体动作
- 情绪弧线
- 需要避免的问题

输出必须简洁、电影化、可给演员执行，并且可以直接粘贴进新的正式场景 prompt。

输出格式：

ACTING STYLE TO APPLY

写 6-9 行或短段落。

要求：
- 具体
- 针对这个角色
- 不使用项目符号
- 不使用小标题
- 不写背景故事总结
- 不提来源材料
- 不复制原台词

## 正式场景接入模板

在正式视频 prompt 中这样接入：

Character:
[角色身份、外观、服装、年龄、体型、一致性要求]

New Scene:
[新的场景目标、地点、关系、剧情动作]

Dialogue or Action:
[正式场景里的新台词或动作]

Acting Style To Apply:
[粘贴提取出的 ACTING STYLE TO APPLY]

Camera:
[新的镜头设计，不沿用试镜镜头]

Lighting and Composition:
[新的灯光与构图，不沿用试镜场景]

Negative Direction:
Do not copy the audition scene, audition dialogue, audition camera movement, audition lighting, audition composition, or audition framing. Carry over only the acting style, emotional behavior, vocal delivery, eye behavior, facial micro-movements, body rhythm, and performance logic.
