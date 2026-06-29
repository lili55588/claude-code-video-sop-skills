# Phase7 角色板 / 场景板完整模板

> Phase7 生成「角色身份板」和「空场景多视角设计板」时套用本文件的固定结构。**手动模式**：本机不出图，按下面契约产出**完整可直接提交目标平台/目标平台的 prompt** 给用户拿去跑。
> **铁律**：角色不得退化成「正/侧/后三视图」、场景不得退化成「单张氛围图」。模板字段不得压缩省略；只允许把方括号字段按剧本与素材清单填实，其余结构段落完整保留。

---

## 一、角色身份板（Character Identity Board）

### 适用范围
- 每个 `待生成主体` 角色 → 生成全新身份板。
- `用户普通参考图` 角色 → 以该上传图为最高优先级身份来源，严格参考生成身份板（见下方前置句）。
- `用户参考主体`（带 `<subject>`）→ **直接复用、不重生、不出板**。
- 一张身份板只放一个角色，不带其他角色/场景/互动。

### Prompt 契约（完整结构，逐字段填实，禁压成三视图）

```text
Create a fully original, copyright-safe character and present them as an artistic CHARACTER IDENTITY BOARD.

[CHARACTER SEED]:
[角色的核心概念、身份、叙事功能与最强识别点]

[AGE / BODY TYPE]:
[年龄印象、体型、姿态、身体存在感；非人角色写可信的生物结构与比例]

[VISUAL MEDIUM]:
[明确渲染媒介，例如 realistic cinematic character design、modern 3D animation character design、2D anime character design、watercolor storybook illustration]

[STYLE]:
[明确审美方向，只写可执行的造型、服装、材质、色彩和时代语言，不写导演、艺术家、工作室或现有 IP 名称]

[OTHER DETAILS - OPTIONAL]:
[永久附属物、关键配色、材质、性格线索、必须保留和必须避免的细节]

Invent everything else needed to make the character specific and non-generic:
character name or title, role, personality traits, emotional tone, visual theme, outfit or body design, color palette, signature prop or biological feature, recognizable silhouette, pose language, and concise identity notes.

Originality rules:
The character must not resemble an existing anime, manga, game, movie, comic, celebrity, athlete, mascot, franchise character, or copyrighted creature.
Do not copy recognizable costumes, hairstyles, uniforms, weapons, logos, symbols, color combinations, silhouettes, powers, or signature traits.
Avoid fan-art aesthetics and generic stock-character design.

Character authenticity rules:
Create a strong individual identity with believable proportions, distinctive structure, subtle asymmetry, natural variation, and small imperfections appropriate to the selected visual medium.
For stylized characters, preserve uniqueness through original shape language, expressive proportions, posture, and personality cues.
For non-human characters, use functional anatomy, believable biological structure, distinctive proportions, surface texture, and clear personality cues; avoid generic mascot or stock fantasy-creature design.

Medium and style control:
[VISUAL MEDIUM] controls the rendering language.
[STYLE] controls the aesthetic direction.
The identity-board layout is only the presentation format and must not override the selected medium or style.

Create an artistic 16:9 CHARACTER IDENTITY BOARD.
The board should feel like a curated visual identity presentation, not a generic turnaround sheet.

Board content:
- one large full-body hero view;
- one neutral full-body view;
- one back view;
- one profile view;
- one secondary attitude pose;
- four to six face or expression studies;
- outfit, material, or anatomy detail close-ups;
- one key prop or signature-feature close-up;
- one small silhouette or shape-language study;
- one color-palette strip;
- short readable identity notes.

Layout:
asymmetrical, elegant, visually memorable, generous empty space, clean separation between views, no overlapping bodies, no cropped faces, no hidden limbs, and no clutter.

Background:
pure white or soft off-white, minimal clean graphic design, no environment, no scene, no logo, and no watermark.

Prioritize:
accurate visual medium, strong unique identity, readable outfit or anatomy design, clear personality, stable face/body/silhouette, believable individuality, and an artistic identity-board presentation.
```

`用户普通参考图`：在上面 prompt 开头**前置**一句——
```text
Strictly use the supplied character reference as the primary identity source. Preserve the face, hairstyle, age impression, body proportions, costume structure, permanent accessories, silhouette, colors, and recognition-critical details. Do not redesign the character.
```

- 媒介/审美：`[VISUAL MEDIUM]` 和 `[STYLE]` 必须与已锁定风格图一致；身份板只是版式、不得覆盖画风。
- 古风写实题材：`[OTHER DETAILS]` 与负面词按 `guofeng-makeup.md` 第六/七节补写实质感后缀（身份板/单体档），妆造直接继承 Phase4、不重设计。

### 角色板 QC
- 产物是 16:9 艺术化身份板，不是只有正/侧/后的三视图。
- 只呈现一个角色身份。
- 大幅全身主视图占主导、从头到脚完整不裁切。
- 全身中性/背/侧/次姿态、4-6 表情研究、细节特写、关键道具/标志特征、剪影研究、色卡齐全。
- 各视图的人脸/发型/体型/服装/鞋足/永久附属物一致不漂移。
- 分格不重叠、不裁脸、不藏肢体。
- 背景纯白/柔白，无环境、无场景、无 logo、无水印。
- 身份注记文字（如有）简短且非关键；文字乱码不得覆盖或替代视觉信息。

---

## 二、空场景多视角设计板（Empty Multi-Angle Environment Design Board）

### 适用范围
- 每个**待生成场景** → 生成多视角设计板。
- `用户普通参考图` 场景 → 以该上传图为地点/风格/布局来源，严格参考扩成同一地点的设计板（见下方前置句）。
- `用户参考主体` 场景、以及风格卡「是，指定为场景X」明确声明的实景上传图 → **按原样登记复用，不强制做成设计板**。
- 一张设计板只放一个真实物理地点，禁止把不同地点拼进同一张板。

### Prompt 契约（完整结构）

```text
[以本场最强、最独特的空间视觉特征开篇，不使用所有场景共用的固定风格开头]。

参考@图片N（风格图）的画风，重新生成<场景名>的 16:9 空场景多视角设计板，包含 3 到 5 个无文字分格。左侧大格约占画面宽度 45%-55%，展示整个场景的主空间布局，可采用俯视、斜俯视或远景观察点；其余小格展示同一地点可直接用于拍摄的不同角度，包括低机位平拍、侧面角度、近景背景板、前景遮挡角度，按本场实际需要取舍。

所有分格必须属于同一个真实物理地点，并保持地标位置、建筑或自然结构、光源方向、地面材质、尺度关系、中景表演区、可通行路径和空间出口一致。明确写出：
- 场景的空间任务（五选一）：[入口 / 过渡 / 阻碍 / 转折 / 开阔收束]；
- 构图引导线与主要地标；
- 前景少量自然或建筑遮挡；
- 中景清晰、可供角色合成和表演的留白区；
- 后景可读的空间深度、出口、远景地标或光源；
- 时间、内外景、天气及其在空气和地面的可见痕迹（外景必须可见对应天气痕迹）；
- 主光方向、色温、冷暖关系和必要的环境反射；
- 可信的地面、墙面、植物、家具或环境道具材质；
- 与全片风格图和场景世界观一致的美术媒介、造型语言、材质表现和色彩规则。

这是一张静态空场景资产设计板，不是故事关键帧，不是单张氛围照，不写运镜、视频时长、首帧、尾帧或角色动作。

禁止出现任何角色、人物、动物、拟人角色、额外生物、角色身体局部、临时手持道具、动作关系、文字标签、水印或 logo。禁止把多个不同地点拼在同一张板中。自然景深不过度虚化，中景表演区和后景空间必须清楚可读。
```

`用户普通参考图`：在上面 prompt 开头**前置**一句——
```text
严格参考所提供场景图的地点身份、空间结构、地标位置、材质、光源方向、色彩和尺度关系，将其扩展为同一地点的空场景多视角设计板，不得改造成另一个地点。
```

- 该设计板作为该场景**所有镜头的统一场景参考**，不同镜头取对应机位分格。
- 反同质化：每张场景板用本场最强空间特征开篇，不要所有场景板共用同一段「风格头/风格尾」。

### 场景板 QC
- 产物是 16:9、3-5 个无文字分格的设计板。
- 左侧主格约占 45%-55%、展示完整空间布局。
- 其余小格是同一地点的实用机位，不是无关构图。
- 各格的地标位置、光源方向、材质、尺度、表演区、路径、出口一致。
- 已声明空间任务（五选一），有可见的构图引导逻辑。
- 前景遮挡克制、中景有合成/表演留白、后景可读。
- 无任何角色/人物/动物/额外生物/身体局部/动作道具/文字/logo/水印。
- 既不是单张氛围图，也不是多个不同地点的拼贴。
