# Speak Sound

Windows 11 本地中日双向游戏语音翻译。中文麦克风 → 日语语音 → 虚拟麦克风；日语队友语音 → 中文 → 屏幕底部穿透字幕。可接游戏内置语音、Discord，以及支持选择输入设备的其他软件。

这是可运行的 Python 桌面应用，按短句连续处理，**不是零延迟的逐词同传**。默认识别 Whisper small，翻译 NLLB-200 distilled 600M，日语合成 OpenJTalk；可选本机 VOICEVOX。音频不上传云服务，不需要 API Key。首次安装下载依赖与模型，之后可断网运行。

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

1. 从 [VB-Audio 官方网站](https://vb-audio.com/Cable/)下载 VB-CABLE。解压后以管理员身份运行其安装程序，按驱动提示重启。该驱动由第三方提供，没有包含在本仓库中。
2. 连接耳机，在本软件点击「刷新音频设备」。
3. 按下表选择设备：

| 位置 | 设置 | 示例 |
| --- | --- | --- |
| Speak Sound | 你的实体麦克风 | USB Microphone / 麦克风 |
| Speak Sound | 接收语音 | 你听队友语音的耳机对应 `[Loopback]` |
| Speak Sound | 日语输出 | **CABLE Input**（虚拟线的播放端） |
| 游戏 / Discord / 其他聊天软件 | 麦克风 / 输入 | **CABLE Output**（虚拟线的录音端） |
| 游戏 / Discord / 其他聊天软件 | 扬声器 / 输出 | 你的耳机 |

`CABLE Input → CABLE Output` 的命名容易混淆：本软件向播放端写入日语，对方软件从录音端读取日语。游戏若没有输入设备选择器，可在 Windows 声音设置里将 CABLE Output 设为默认通信输入设备。

4. 目标聊天软件使用语音激活或持续输入。若目标软件也启用了按键说话，必须让它在**翻译日语播放期间**保持发送。只按住原文录音阶段不会传出译文。
5. 点击「开始翻译」，等待模型加载。默认**按住 F8 说中文，松开后翻译并播放日语**。也可关闭按键说话，自动检测讲话。F8 由 Windows 全局按键状态读取，不修改游戏文件。
6. 队友日语会显示为底部中文字幕，同时显示日文原文。设置里可调屏幕、字号、底部距离并预览。记录页显示识别原文、译文和模型处理耗时；记录仅在内存中保留最近 300 个文本块。

### 减少游戏音效干扰

WASAPI 回环捕获的是所选播放设备的**全部声音**，没有自动分离队友语音、游戏音效、背景音乐。Discord 建议设置独立输出设备：将 Discord 输出路由到第二条虚拟音频线或 Voicemeeter 的独立总线，本软件监听该播放端回环，并在混音器中把它监听到耳机。游戏音效继续直接输出到耳机。需要额外音频总线才能这样隔离；单条 CABLE 已用于发送，不能同时拿来做接收。

如果游戏只提供合并后的声音，首版无法可靠提取单独的队友声音。戴耳机，避免实体麦克风拾取耳机漏音。程序在日语发送期间暂停本机麦克风采集，防止回授；这段时间不要开始下一句话。不要将发送音频线监听回接收总线。

## 本地模型与性能

| 环节 | 默认组件 | 运行位置 |
| --- | --- | --- |
| 音频采集 / 输出 | PyAudioWPatch / WASAPI | 本机 |
| 分句 | WebRTC VAD，20 ms 帧 | 本机 CPU |
| 中日语音识别 | faster-whisper small，CPU int8 | 本机，可选 NVIDIA GPU |
| 双向文本翻译 | NLLB-200 distilled 600M / CTranslate2 int8 | 本机 CPU，限制 4 个线程 |
| 日语语音合成 | pyopenjtalk-plus / OpenJTalk | 本机 CPU |
| 可选日语音色 | VOICEVOX | 仅 `127.0.0.1:50021` |

说话停顿约 400 ms 后提交；连续讲话约 5 秒分段，最短约 160 ms。保留约 200 ms 前导音频，减少切掉字头。长句分段可能影响翻译上下文。每个方向最多排队两句，队列满会提示并跳过新句，避免无限积压。识别和翻译模型分别加锁，双向共享模型节省内存；繁忙时两个方向可能相互等待。记录中的耗时不包含录音、排队和最终日语播放，不代表完整端到端延迟。

更快识别可运行 `setup.ps1 -WhisperModel base`（同一个 `models/whisper` 目录会切换模型）；更高精度可选 `medium` 或 `large-v3-turbo`。下载失败时不要启动，重跑直到完成。运行期严格使用本地文件；缺失模型会显示错误，不会悄悄调用在线服务。CPU 为默认部署，不会自动安装 CUDA 或占满显卡。

GPU 模式仅加速识别，需按 [faster-whisper 官方说明](https://github.com/SYSTRAN/faster-whisper#gpu)安装匹配的 CUDA 12 / cuDNN 9 / cuBLAS。首次可先在 CPU 模式验证路由；切换 GPU 出错可退回 CPU。GPU 模式的性能和游戏帧率影响需实机测试。

内置日语音色比较机械。需要更自然声音时，安装并启动 [VOICEVOX](https://voicevox.hiroshiba.jp/)，选择 VOICEVOX 并填有效的声音风格 ID。可在 `http://127.0.0.1:50021/speakers` 查看 ID。软件只向本机发送合成请求，并禁用环境代理。角色声音的使用需遵守对应条款。

## 常见问题

- **游戏全屏看不到字幕：** 使用无边框窗口或窗口模式。独占全屏可能覆盖桌面置顶窗口。字幕穿透鼠标，不抢游戏焦点。
- **对方听不到：** 本软件输出选 CABLE Input，聊天输入选 CABLE Output；确保目标软件在日语播放时允许发送。部分噪声抑制功能会削弱合成语音，可在目标软件中调整。
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
- [NLLB 模型卡](https://huggingface.co/facebook/nllb-200-distilled-600M)：CC-BY-NC-4.0，研究用途模型，非商业限制；本项目不附带其权重。
- [NLLB int8 转换权重](https://huggingface.co/JustFrederik/nllb-200-distilled-600M-ct2-int8/tree/302d78f00e6fdb50a1064059df7c392b735e9d05)：固定版本下载，约 623 MB，继承原模型许可；分词器来自 Meta 原始模型。
- [pyopenjtalk-plus](https://github.com/tsukumijima/pyopenjtalk-plus)：本地日语合成与辞书，随包许可证见上游。
- [VOICEVOX API](https://voicevox.github.io/voicevox_engine/api/)：可选本地语音合成。

本仓库新编写代码采用 MIT；第三方库、模型、音色、音频驱动各自遵循其许可证。翻译模型没有针对游戏术语专门训练，可能误译，需结合上下文使用。
