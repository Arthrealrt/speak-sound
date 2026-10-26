# Speak Sound 开源虚拟麦克风

v0.5 新增用户态虚拟 USB 声卡。信号路径：

`实体麦克风 / 日语译音 → Speak Sound 变声 → Speak Sound Virtual Cable 播放端 → 本地 USB/IP → 同名麦克风端 → 游戏 / Discord`

用户态 USB Audio Class 1.0 源码来自 [Virtual Cables 固定版本](https://github.com/tarekwasfy01/Virtual-Cables/tree/8a819c29971d30a73955178ac8a3aac00b1a5230)，BSD-2-Clause，随项目发布在 `native/virtual-mic`。修改说明见其 NOTICE.md。Windows 使用系统自带的 USB 音频类驱动；USB 运输层使用开源 [usbip-win2](https://github.com/vadimgrn/usbip-win2)，BSD-2-Clause。

USB/IP 官方说明其发行驱动为 WHLK / attestation signed，正式签名发行包不需要测试模式。这条路线与旧 RadioVoice 测试签名方案不同。软件不改 Secure Boot、测试签名、代码完整性策略或证书存储。

## 当前状态

用户态后端源码、构建脚本、本机 `bin/speak-sound-mic.exe`、连接按钮、实时及翻译变声均已准备。Go 协议测试及已编译 EXE 的 localhost 设备枚举与关闭检查通过。本机已安装并加载签名运输驱动，安装前后 Secure Boot 均为 true，Windows 已创建配对端点。合成 440 Hz 音变调 -5 半音后经播放端进入虚拟麦克风，捕获主峰约 327 Hz，验证实际端点可用；未录制真人音频。游戏 / Discord 仍需实际配置和测试。

USBip 0.9.8.1 x64 官方安装包已下载并核对 SHA-256，Authenticode 状态 Valid，签名者 Cloudyne Systems (Scheibling Consulting AB)。安装器签名有效不等于已验证实际内核加载。核验记录见 usbip-release.json。

## 构建后端

完整 setup.ps1 默认构建用户态后端。也可单独运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\drivers\build_virtual_mic.ps1
```

需要 Go 1.22+；未找到时，脚本在项目 work/go-toolchain 下载 Go 1.27.3 便携 ZIP 并校验固定哈希，不改系统 PATH。构建不安装驱动。GitHub 和源码 ZIP 不包含 EXE；本次本地应用 ZIP 带后端 EXE，但不含 Python 环境、模型和系统驱动安装器。setup.ps1 -SkipVirtualMic 可跳过此构建。

## 准备和安装运输驱动

只下载、核验，不安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\drivers\setup_virtual_mic.ps1
```

来源：[USBip 0.9.8.1 x64 官方发行版](https://github.com/vadimgrn/usbip-win2/releases/tag/v.0.9.8.1)。安装器保存在 downloads/USBip-0.9.8.1-x64.exe。

SHA-256：`38cad6d4432b52d5bb9409d9ad03b72fdffc4ada4cd3a48fbeca1a2752a8518a`。

**上游安装器会短暂重启 USB 3.0 Hub，USB 键鼠、声卡、摄像头和移动硬盘可能短暂断开。** 请避开游戏、会议、录音和文件传输；上游建议准备系统还原点。本项目不自动创建还原点或重启电脑。

准备好并同意 USB 设备短暂断开后，以管理员 PowerShell 执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\drivers\setup_virtual_mic.ps1 -Install -AcceptUsbRestart
```

脚本再次核对哈希并要求安装器签名 Valid，再启动原版安装器，禁用自动重启。若 Windows 拒绝加载，停止并查看 downloads/usbip-install.log，不要通过关闭安全启动或开启测试模式绕过。若安装要求重启，手动安排后再连接。后续翻译与变声通常无需管理员权限。

## 在应用和聊天软件中使用

1. 在设备页点击连接 Speak Sound 虚拟麦克风，等待并刷新设备。
2. 本软件发送输出选 `扬声器 / Speakers (Speak Sound Virtual Cable 01)`，勾选发送声音。
3. 游戏 / Discord 输入选 `麦克风 / Microphone (Speak Sound Virtual Cable 01)`，输出保持耳机。
4. 直接变声：顶部选实时变声器，选真实麦克风、音效；F8 按住期间连续发送。关闭 F8 开关则持续发送。
5. 翻译变声：顶部保持双向翻译，在变声器页启用效果；仅自己的日语译音会变声，队友中文播报保持原音色。
6. 先在耳机中监听测试。实时监听需戴耳机，避免扬声器和麦克风回授。

断开或关闭本软件会关闭本软件的虚拟声卡，运输驱动留在系统。不设置开机自启或永久 USB 连接。管理器仅分离本次确切拥有的 USB/IP 端口，不执行 detach-all，不关闭其他程序。32401 端口被其他程序占用时提示失败。

## 格式和边界

48 kHz / 双声道 / 16 位 PCM。ring 容量 80 ms 不是总延迟保证；变调读指针另有约 5～85 ms 延迟，还需计入采集、输出、USB、聊天软件等缓冲。音频只走内存和 127.0.0.1，不发外部服务器。

后端仍是实验性 USB 模拟代码，不能保证每种游戏、反作弊、Windows 版本和长期负载兼容。采用上游实验 USB VID/PID，不宣称注册了硬件 ID。卸载运输驱动应通过 Windows 已安装的应用卸载 USBip，本软件不强删可能被其他应用共享的运输驱动。

旧 `RadioVoice Output → RadioVoice Microphone` GPL 接入为旧配置保留，其现有上游包要求测试签名，本项目不安装或改变安全设置。新的推荐路线是上述签名运输层和开源用户态声卡。
连接前保存系统默认设备；若 Windows 自动将新声卡设为默认，软件按播放/录音、控制台/多媒体/通信六个角色恢复原默认，仅在当前默认仍是本声卡时恢复，不覆盖用户并发切换到其他设备的选择。该行为已在本机验证。为防回授，不允许选择自身虚拟麦克风或 Primary Sound Capture / 主声音捕获等动态别名，旧配置需重选明确名称的实体麦克风。
额外验证：安装包内两个 SYS 与两个 CAT 均为 Valid 的 Microsoft Windows Hardware Compatibility Publisher 签名，已记录各文件哈希；仍未实际加载驱动。脚本只安装 main/client，不选择 GUI、SDK、调试符号或随包 VC Redistributable，使用本机已有 Windows C++ 运行环境。
