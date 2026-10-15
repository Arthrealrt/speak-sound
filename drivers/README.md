# 开源虚拟麦克风接入

当前按 [RadioVoice 驱动源码固定版本](https://github.com/doctorspider42/radio-voice/tree/872f7d570f093f94b514ebdcfbbb1a23ecc458d9/driver)的端点名称与接口说明适配，许可为 GPL-3.0-or-later。驱动独立安装，Speak Sound 通过 Windows 音频接口使用端点；没有复制或改写该驱动源码，也不分发其二进制。

| 端点 | 使用位置 |
| --- | --- |
| RadioVoice Output | Speak Sound 的日语输出 |
| RadioVoice Microphone | 游戏 / Discord 的麦克风输入 |

驱动的用途是将播放端信号转给录音端；支持的格式由上游定义，本软件写入 48 kHz、16 位 PCM。上游说明及编译过程见其 [driver/README.md](https://github.com/doctorspider42/radio-voice/blob/main/driver/README.md)。单独构建驱动即可，不需要其完整音效处理应用或其他外部音频线。

## 当前限制

上游现有安装方式要求测试签名及关闭 Secure Boot，没有提供本项目已验证的微软生产签名包。这是该发行包的签名状态，不是开源许可本身的要求。Windows 的内核驱动加载策略见 [Microsoft 官方说明](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/kernel-mode-code-signing-policy--windows-vista-and-later-)。

用户已选择**保持当前安全设置**。因此，本项目不会开启测试签名、修改 Secure Boot、添加根证书或安装内核驱动；本机的虚拟麦克风发送目前不可用。仅更改设备名称或从软件中“创建一个麦克风”不能替代内核驱动。

后续若获得兼容且带生产签名的开源驱动包，可以保持安全设置并接入。此前不能承诺这套驱动适用于要求安全启动或禁止测试模式的游戏，也没有进行游戏反作弊兼容测试。

## 已完成的接入

- 自动识别 RadioVoice Output，优先选择 WASAPI 端点。
- 输出选择器只列出这一已适配开源驱动的播放端。
- 服务启动会再次校验端点，避免旧配置恢复闭源音频线或误选实体扬声器。
- 未发现驱动时明确提示虚拟麦克风不可用。
- 安装脚本只部署用户态应用和模型，没有驱动安装或启动配置修改命令。

驱动就绪后的联调应验证：生成日语能从 RadioVoice Microphone 录到、目标聊天软件在译文播放期间发送、设备默认采样率正确，以及游戏运行时字幕可见。以上内核驱动与游戏链路尚未在本机验证。
