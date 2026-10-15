# Speak Sound

Windows 11 本地中日双向游戏语音翻译。中文麦克风 → 日语合成 → 本地试听 / 可选虚拟麦克风；队友日语 → 中文 → 屏幕底部字幕与中文播报。虚拟麦克风发送可接游戏内置语音、Discord 等支持选择输入设备的软件，但仍需要兼容驱动。

这是开源 Python 桌面应用，按短句连续处理。识别使用 Whisper small，翻译使用 MIT 许可的 M2M100 418M，日语合成使用 OpenJTalk，中文播报使用 MIT 许可的 MeloTTS / sherpa-onnx。音频不上传云服务，不需要 API Key；首次下载后可离线运行。组件许可见 [DEPENDENCIES.md](DEPENDENCIES.md)。

**当前交付状态：应用、本地模型、中文播报及日语试听可运行；开源驱动端点适配代码已完成，但未交付微软生产签名驱动，本机的游戏内虚拟麦克风发送尚不可用。** 根据用户选择，保持系统安全设置不变。所选上游驱动目前依赖测试签名；不能把它当作保留现有安全设置即可即装即用的方案。详情见 [驱动接入与限制](drivers/README.md)。

## 安装

需要 Windows 11 x64、[Python 3.12 x64](https://www.python.org/downloads/windows/)。建议预留至少 8 GB 磁盘和 8 GB 可用内存。默认 CPU 可运行；速度需要在你的机器上实测。

在本目录打开 PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

可指定解释器或更小模型：

```powershell
.\setup.ps1 -PythonExe 'C:\Python312\python.exe' -WhisperModel base
```

安装脚本只向项目 `.venv` 和 `models` 写入依赖与模型，不安装音频驱动、不修改系统默认设备。依赖下载失败后重跑即可；模型下载可续传。模型目录不要提交到 GitHub。

安装完成双击 **`start.cmd`**。代码位于 `speak_sound/`，配置保存在本目录 `config.json`。目录需要可写。

`setup.ps1` 使用 `requirements-lock.txt` 安装经过本机验证的确切依赖版本；`requirements.txt` 保留兼容版本范围供开发使用。

## 虚拟麦克风与设备连接

**无需虚拟驱动的本地播放：** 选择实体麦克风、你听队友语音的耳机 `[Loopback]`；在「译音播放」页选择耳机，保持中文播报与日语试听勾选。不要勾选「向虚拟麦克风发送日语」，即可同时听到两种译音，但日语不会传给队友。

**只收队友：** 勾选「仅接收队友语音」，不需要实体麦克风；可选择中文播报或仅看字幕。要真正发送到游戏，需准备下述驱动并启用「向虚拟麦克风发送日语」。

1. 先阅读 [开源驱动说明](drivers/README.md)。当前适配 GPL-3.0-or-later 的 RadioVoice 虚拟音频驱动；本项目不包含其二进制、不自动安装驱动、不更改启动安全设置。没有兼容驱动时，界面明确显示虚拟麦克风不可用。
2. 连接耳机，在本软件点击「刷新音频设备」。
3. 按下表选择设备：

| 位置 | 设置 | 示例 |
| --- | --- | --- |
| Speak Sound | 你的实体麦克风 | USB Microphone / 麦克风 |
| Speak Sound | 接收语音 | 你听队友语音的耳机对应 `[Loopback]` |
| Speak Sound | 日语输出 | **RadioVoice Output**（开源驱动的播放端） |
| 游戏 / Discord / 其他聊天软件 | 麦克风 / 输入 | **RadioVoice Microphone**（开源驱动的录音端） |
| 游戏 / Discord / 其他聊天软件 | 扬声器 / 输出 | 你的耳机 |

信号路径为 `RadioVoice Output → RadioVoice Microphone`：本软件写入播放端，对方软件从录音端读取。此路径须在用户自行准备好兼容驱动后联调，不代表本机已验证通过。

4. 目标聊天软件使用语音激活或持续输入。若目标软件也启用了按键说话，必须让它在**翻译日语播放期间**保持发送。只按住原文录音阶段不会传出译文。
5. 点击「开始翻译」，等待模型加载。默认**按住 F8 说中文，松开后翻译并播放日语**。也可关闭按键说话，自动检测讲话。F8 由 Windows 全局按键状态读取，不修改游戏文件。
6. 队友日语会显示为底部中文字幕，同时显示日文原文。设置里可调屏幕、字号、底部距离并预览。记录页显示识别原文、译文和模型处理耗时；记录仅在内存中保留最近 300 个文本块。

## 译音播放与虚拟扬声器

「译音播放」页提供两个独立开关：队友日语转中文播报、自己中文转日语后的本地试听。它们使用现有耳机或扬声器，无需内核驱动。两种本地声音串行播放，最多排队两句；积压时跳过新的试听，字幕与虚拟麦克风发送继续处理。停止会丢弃未播放内容。

**本地译音播放不会创建 Windows 虚拟扬声器。** 若要在系统设备列表出现独立的虚拟扬声器和虚拟麦克风，仍需驱动及微软生产签名。开源代码同样可以申请生产签名；本项目当前没有提供经过该流程的驱动包。变声器式路径与当前交付边界见 [drivers/README.md](drivers/README.md)。

回声保护：当前采集的是整台播放设备的混合声音。本地译音播放期间及结束后约 0.3 秒，会暂停接收及实体麦克风采集，防止译音再次进入识别形成循环。这段时间的重叠讲话可能漏收。关闭本地播报可恢复连续字幕接收；当前没有实现按进程排除自身播放的捕获，也没有宣称全双工回声消除。

### 减少游戏音效干扰

WASAPI 回环捕获所选播放设备的**全部声音**，没有自动分离队友语音、游戏音效和音乐。可以使用另一块实体声卡或独立耳机作为聊天输出，并监听该设备回环；仅有一个合并输出时，本版本不能可靠隔离队友语音。不要把发送用的虚拟播放端同时用作接收端。

如果游戏只提供合并后的声音，首版无法可靠提取单独的队友声音。戴耳机，避免实体麦克风拾取耳机漏音。程序在日语发送期间暂停本机麦克风采集，防止回授；这段时间不要开始下一句话。不要将发送音频线监听回接收总线。

## 本地模型与性能

| 环节 | 默认组件 | 运行位置 |
| --- | --- | --- |
| 音频采集 / 输出 | PyAudioWPatch / WASAPI | 本机 |
| 分句 | WebRTC VAD，20 ms 帧 | 本机 CPU |
| 中日语音识别 | faster-whisper small，CPU int8 | 本机 CPU |
| 双向文本翻译 | M2M100 418M / CTranslate2 int8，MIT | 本机 CPU，限制 4 个线程 |
| 日语语音合成 | pyopenjtalk-plus / OpenJTalk | 本机 CPU |
| 中文语音合成 | MeloTTS Chinese ONNX / sherpa-onnx | 本机 CPU，2 线程 |
| 虚拟音频端点适配 | RadioVoice GPL 驱动 | 需另行准备，尚未本机验证 |

说话停顿约 400 ms 后提交；连续讲话约 5 秒分段，最短约 160 ms。保留约 200 ms 前导音频，减少切掉字头。长句分段可能影响翻译上下文。每个方向最多排队两句，队列满会提示并跳过新句，避免无限积压。识别和翻译模型分别加锁，双向共享模型节省内存；繁忙时两个方向可能相互等待。记录中的耗时不包含录音、排队和最终日语播放，不代表完整端到端延迟。

更快识别可运行 `setup.ps1 -WhisperModel base`（同一个 `models/whisper` 目录会切换模型）；更高精度可选 `medium` 或 `large-v3-turbo`。下载失败时不要启动，重跑直到完成。运行期严格使用本地文件；缺失模型会显示错误，不会悄悄调用在线服务。CPU 为默认部署，不会自动安装 CUDA 或占满显卡。

本版使用 CPU 推理，不需要另装专有 GPU 计算库。内置 OpenJTalk 的音色偏机械；Mei 声库采用 CC BY 3.0，署名见 [DEPENDENCIES.md](DEPENDENCIES.md)。中文 MeloTTS 浮点 ONNX 模型约 170 MB，保存在 `models/chinese-tts`。翻译模型、分词器分别位于 `models/m2m100` 和 `models/m2m100-tokenizer`；旧版模型不再加载。

## 常见问题

- **游戏全屏看不到字幕：** 使用无边框窗口或窗口模式。独占全屏可能覆盖桌面置顶窗口。字幕穿透鼠标，不抢游戏焦点。
- **对方听不到：** 先确认已安装兼容的开源驱动；本软件输出选 RadioVoice Output，聊天输入选 RadioVoice Microphone，并确保译文播放时允许发送。当前未验证完整游戏链路。
- **识别到游戏台词或音乐：** 将队友语音输出隔离到独立设备。语音检测不能区分队友、配音和其他人声。
- **设备失效：** 停止、重新连接设备、刷新并重选。设置按设备名称保存，设备更名后需重选。
- **F8 无效：** 检查游戏是否占用或拦截该键；通常不需要管理员权限。
- **停止稍慢：** 停止会中断后续采集与播放，等待已经开始的模型计算结束，然后释放音频设备。
- **运行报错：** 从终端执行 `.venv\Scripts\python.exe -m speak_sound` 查看完整输出。

## 验证

本次实际验证范围和模型输出见 [VALIDATION.md](VALIDATION.md)。

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m compileall -q speak_sound tools tests
.venv\Scripts\python.exe tools\verify_local.py
```

`verify_local.py` 不录制麦克风：列举设备，使用本地模型翻译两句中日文，合成日语并回识别，最后保存检查结果到本机 `verification.json`。它不验证游戏服务器是否实际收到语音。最终需要实际连接虚拟音频线并和队友测试，调整音量、降噪、延迟与识别模型。

## 来源与许可

- [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch)：Windows WASAPI 回环接口。
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)：本地语音识别。
- [M2M100 原始模型](https://huggingface.co/facebook/m2m100_418M)：MIT 许可，中日双向翻译。
- [M2M100 int8 转换权重](https://huggingface.co/jncraton/m2m100_418M-ct2-int8/tree/7c1b2620a4e58dacecbd8bf89cfd6da7eb9eb7b0)：固定版本下载；分词器来自 Meta 原始模型的固定版本。
- [pyopenjtalk-plus](https://github.com/tsukumijima/pyopenjtalk-plus)：本地日语合成与辞书，随包许可证见上游。
- [RadioVoice 驱动源码](https://github.com/doctorspider42/radio-voice/tree/main/driver)：GPL-3.0-or-later；接入限制见 drivers/README.md。

本仓库新编写代码采用 MIT；第三方库、模型、音色、音频驱动各自遵循其许可证。翻译模型没有针对游戏术语专门训练，可能误译，需结合上下文使用。
