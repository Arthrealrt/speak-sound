# 开源组件与模型许可

本项目应用代码为 MIT。必需组件采用以下开源软件许可或允许复制、修改及商业使用的模型/声音资源许可。下载的模型和 Python 包不包含在源码 ZIP 中；安装时从列出的来源获取。Windows 及目标游戏是运行平台，不属于本项目发布内容。

| 组件 | 许可与来源 |
| --- | --- |
| 应用源码 | [MIT](LICENSE) |
| Whisper 模型、faster-whisper、CTranslate2 | MIT；[Whisper](https://github.com/openai/whisper)、[faster-whisper](https://github.com/SYSTRAN/faster-whisper)、[CTranslate2](https://github.com/OpenNMT/CTranslate2) |
| M2M100 原始权重与分词器 | MIT；[Meta 模型卡](https://huggingface.co/facebook/m2m100_418M) |
| M2M100 int8 权重 | MIT；[固定转换版本](https://huggingface.co/jncraton/m2m100_418M-ct2-int8/tree/7c1b2620a4e58dacecbd8bf89cfd6da7eb9eb7b0) |
| RadioVoice 虚拟音频驱动 | GPL-3.0-or-later；[源码与许可](https://github.com/doctorspider42/radio-voice)。独立组件，未打包或安装 |
| PySide6 / shiboken6 | LGPL-3.0 / GPL 许可选项；[Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html)，使用动态安装包 |
| PyAudioWPatch / PortAudio | 包元数据标注 Apache-2.0；其继承的 PyAudio / PortAudio 含 MIT 许可部分，见[上游](https://github.com/s0d3s/PyAudioWPatch)及安装包 notices |
| NumPy / SciPy | BSD 为主，含各自开源组件 notices；[NumPy](https://github.com/numpy/numpy)、[SciPy](https://github.com/scipy/scipy) |
| WebRTC VAD | MIT / WebRTC BSD notices；[webrtcvad-wheels](https://github.com/daanzu/py-webrtcvad-wheels) |
| pyopenjtalk-plus / OpenJTalk / HTS Engine | MIT / BSD 系列许可；[pyopenjtalk-plus](https://github.com/tsukumijima/pyopenjtalk-plus)及其第三方源码 notices |
| SudachiPy / SudachiDict-core | Apache-2.0；[SudachiPy](https://github.com/WorksApplications/SudachiPy)、[SudachiDict](https://github.com/WorksApplications/SudachiDict) |
| Mei 日语声库 | CC BY 3.0；MMDAgent Project Team，Copyright 2009–2013 Nagoya Institute of Technology, Department of Computer Science。[随包原始声明](licenses/Mei-voice-LICENSE.txt) |
| Transformers / Hugging Face Hub / tokenizers / SentencePiece | Apache-2.0；各包及上游仓库中的许可文件 |
| ONNX Runtime | MIT；[上游](https://github.com/microsoft/onnxruntime) |
| PyAV / FFmpeg | PyAV BSD-3-Clause；FFmpeg 及编解码器按其 LGPL/GPL 和 bundled notices，均须保留随包声明。[PyAV](https://github.com/PyAV-Org/PyAV) |

CC BY 3.0 用于声音数据，不是软件代码许可；它要求署名，没有非商业或禁止修改条款。本项目不宣称所有模型训练过程和训练数据都可完全重现。

其余 Python 依赖包括 MIT、BSD、Apache、MPL、PSF 等开源许可。当前部署环境的 37 个 Python 包及其元数据声明记录于 [licenses/python-packages.json](licenses/python-packages.json)；元数据未填写许可的包仍应以所安装包的 LICENSE / notices 为准。依赖确切版本见 `requirements-lock.txt`。

本版不再加载或下载此前的非商业限制翻译模型，也不依赖外部角色音色或专有 GPU 计算库。若重新分发完整二进制/环境，需要同时保留各组件 notices，并履行 LGPL/GPL 对对应组件的源码及替换要求；应用 MIT 许可不会替代这些义务。
