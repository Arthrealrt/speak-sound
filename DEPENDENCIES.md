# 开源组件与模型许可

本项目应用代码为 MIT。必需组件采用以下开源软件许可或允许复制、修改及商业使用的模型/声音资源许可。下载的模型和 Python 包不包含在源码 ZIP 中；安装时从列出的来源获取。Windows 及目标游戏是运行平台，不属于本项目发布内容。

| 组件 | 许可与来源 |
| --- | --- |
| 应用源码 | [MIT](LICENSE) |
| pycaw / comtypes | MIT；用于在 Windows 自动把新虚拟声卡设为默认时，按角色恢复连接前的默认设备；[pycaw](https://github.com/AndreMiras/pycaw)、[comtypes](https://github.com/enthought/comtypes) |
| 变声 DSP | 本项目 MIT，使用现有 NumPy / SciPy；不引入专有音效库或新模型 |
| Virtual Cables 用户态 USB 协议 / 缓冲源码 | BSD-2-Clause；[固定提交](https://github.com/tarekwasfy01/Virtual-Cables/tree/8a819c29971d30a73955178ac8a3aac00b1a5230)，[许可](native/virtual-mic/LICENSE)及[修改说明](native/virtual-mic/NOTICE.md)随源码发布 |
| usbip-win2 运输驱动 | BSD-2-Clause；[上游](https://github.com/vadimgrn/usbip-win2)，[许可副本](licenses/usbip-win2-LICENSE.txt)；签名安装包单独下载 |
| Go runtime / 标准库 | BSD-3-Clause；编译后用户态程序包含 Go runtime，保留 [Go 许可](licenses/Go-LICENSE.txt)，编译工具链仅构建时下载 |
| ProcTap 1.1.1 | MIT；[进程采集源码](https://github.com/m96-chan/ProcTap)，使用其公开源码的原生 Windows 扩展 API，并检查实际进程隔离状态；[许可证副本](licenses/ProcTap-LICENSE.txt) |
| psutil | BSD-3-Clause；[进程枚举与存活检测](https://github.com/giampaolo/psutil) |
| Whisper 模型、faster-whisper、CTranslate2 | MIT；[Whisper](https://github.com/openai/whisper)、[faster-whisper](https://github.com/SYSTRAN/faster-whisper)、[CTranslate2](https://github.com/OpenNMT/CTranslate2) |
| M2M100 原始权重与分词器 | MIT；[Meta 模型卡](https://huggingface.co/facebook/m2m100_418M) |
| M2M100 int8 权重 | MIT；[固定转换版本](https://huggingface.co/jncraton/m2m100_418M-ct2-int8/tree/7c1b2620a4e58dacecbd8bf89cfd6da7eb9eb7b0) |
| RadioVoice 虚拟音频驱动 | GPL-3.0-or-later；[源码与许可](https://github.com/doctorspider42/radio-voice)。独立组件，未打包或安装 |
| PySide6 / shiboken6 | LGPL-3.0 / GPL 许可选项；[Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html)，使用动态安装包 |
| PyAudioWPatch / PortAudio | 包元数据标注 Apache-2.0；其继承的 PyAudio / PortAudio 含 MIT 许可部分，见[上游](https://github.com/s0d3s/PyAudioWPatch)及安装包 notices |
| NumPy / SciPy | BSD 为主，含各自开源组件 notices；[NumPy](https://github.com/numpy/numpy)、[SciPy](https://github.com/scipy/scipy) |
| WebRTC VAD | MIT / WebRTC BSD notices；[webrtcvad-wheels](https://github.com/daanzu/py-webrtcvad-wheels) |
| Silero VAD | MIT；[上游源码](https://github.com/snakers4/silero-vad)，使用 faster-whisper 固定安装包随附 ONNX 模型，[许可副本](licenses/Silero-VAD-LICENSE.txt)；仅检测人声，不区分说话人身份 |
| pyopenjtalk-plus / OpenJTalk / HTS Engine | MIT / BSD 系列许可；[pyopenjtalk-plus](https://github.com/tsukumijima/pyopenjtalk-plus)及其第三方源码 notices |
| SudachiPy / SudachiDict-core | Apache-2.0；[SudachiPy](https://github.com/WorksApplications/SudachiPy)、[SudachiDict](https://github.com/WorksApplications/SudachiDict) |
| Mei 日语声库 | CC BY 3.0；MMDAgent Project Team，Copyright 2009–2013 Nagoya Institute of Technology, Department of Computer Science。[随包原始声明](licenses/Mei-voice-LICENSE.txt) |
| MeloTTS 中文声库及 ONNX 转换 | MIT；[固定模型版本](https://huggingface.co/csukuangfj/vits-melo-tts-zh_en/tree/a0d5c6a264c0ef92d70d8661d8cc502d79627cd6)，Copyright 2024 MyShell.ai，转换代码来自 [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx/tree/master/scripts/melo-tts) |
| MeloTTS 英语声库及 ONNX 转换 | MIT；[固定模型版本](https://huggingface.co/csukuangfj/vits-melo-tts-en/tree/9969cf40233d9ee504a6e1cde8aee9bab3ecf985)，Copyright 2024 MyShell.ai，[许可副本](licenses/MeloTTS-English-LICENSE.txt)；与中文模型分开加载 |
| sherpa-onnx / sherpa-onnx-core | Apache-2.0；[上游](https://github.com/k2-fsa/sherpa-onnx) |
| Transformers / Hugging Face Hub / tokenizers / SentencePiece | Apache-2.0；各包及上游仓库中的许可文件 |
| ONNX Runtime | MIT；[上游](https://github.com/microsoft/onnxruntime) |
| PyAV / FFmpeg | PyAV BSD-3-Clause；FFmpeg 及编解码器按其 LGPL/GPL 和 bundled notices，均须保留随包声明。[PyAV](https://github.com/PyAV-Org/PyAV) |

CC BY 3.0 用于声音数据，不是软件代码许可；它要求署名，没有非商业或禁止修改条款。本项目不宣称所有模型训练过程和训练数据都可完全重现。

其余 Python 依赖包括 MIT、BSD、Apache、MPL、PSF 等开源许可。当前部署环境的 43 个 Python 包及其元数据声明记录于 [licenses/python-packages.json](licenses/python-packages.json)；元数据未填写许可的包仍应以所安装包的 LICENSE / notices 为准。依赖确切版本见 `requirements-lock.txt`。

本版不再加载或下载此前的非商业限制翻译模型，也不依赖外部角色音色或专有 GPU 计算库。若重新分发完整二进制/环境，需要同时保留各组件 notices，并履行 LGPL/GPL 对对应组件的源码及替换要求；应用 MIT 许可不会替代这些义务。
