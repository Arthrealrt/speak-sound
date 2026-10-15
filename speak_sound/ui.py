import ctypes
import html
import os
import sys
from pathlib import Path

import pyaudiowpatch as pa
from PySide6.QtCore import Qt, QTimer, QLocale
from PySide6.QtGui import QCloseEvent, QFont, QFontDatabase
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFormLayout,
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QSpinBox,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget)

from .audio import devices
from .config import Settings
from .service import Service
from .routing import is_open_output


class Subtitle(QWidget):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput
                            | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

    def display(self, original, translated):
        self.label.setStyleSheet("QLabel { color: white; background: rgba(10, 14, 24, 210);"
                                  "border-radius: 12px; padding: 14px 24px;"
                                  f"font-size: {self.settings.font_size}px; }}")
        self.label.setFont(QFont("Microsoft YaHei UI", self.settings.font_size))
        self.label.setText(translated + ("\n" + original if original else ""))
        screens = QApplication.screens()
        screen = screens[min(self.settings.screen, len(screens) - 1)]
        rect = screen.geometry()
        width = int(rect.width() * .82)
        self.setFixedWidth(width)
        height = min(int(rect.height() * .35), max(90, self.label.heightForWidth(width) + 8))
        self.setFixedHeight(height)
        self.move(rect.x() + (rect.width() - width) // 2,
                  rect.bottom() - self.settings.bottom_margin - height)
        self.show()
        self.timer.start(self.settings.subtitle_seconds * 1000)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        try:
            self.settings = Settings.load()
        except (ValueError, TypeError):
            self.settings = Settings()
        self.service = None
        self.closing = False
        self.stop_requested = False
        self.overlay = Subtitle(self.settings)
        self.setWindowTitle("Speak Sound · 中日游戏语音翻译")
        self.resize(850, 700)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        title = QLabel("Speak Sound")
        title.setStyleSheet("font-size: 32px; font-weight: 700; color: #aab9ff;")
        layout.addWidget(title)
        layout.addWidget(QLabel("中文 → 日语虚拟麦克风    /    日语 → 屏幕底部中文字幕"))
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        controls = QWidget()
        form = QFormLayout(controls)
        self.mic, self.receive, self.output = QComboBox(), QComboBox(), QComboBox()
        form.addRow("你的实体麦克风", self.mic)
        form.addRow("接收语音（耳机/音频线的回环）", self.receive)
        form.addRow("日语输出（虚拟音频线播放端）", self.output)
        self.receive_only = QCheckBox("仅接收队友语音（关闭我的麦克风）")
        self.receive_only.setChecked(self.settings.receive_only)
        self.receive_only.toggled.connect(self.update_mode)
        form.addRow(self.receive_only)
        self.send_virtual = QCheckBox("向虚拟麦克风发送日语（需兼容开源驱动）")
        self.send_virtual.setChecked(self.settings.send_to_virtual)
        self.send_virtual.toggled.connect(self.update_mode)
        form.addRow(self.send_virtual)
        self.refresh = QPushButton("刷新音频设备")
        self.refresh.clicked.connect(self.refresh_devices)
        form.addRow(self.refresh)
        self.ptt = QCheckBox("按住 F8 说中文，松开后发送翻译（推荐）")
        self.ptt.setChecked(self.settings.push_to_talk)
        form.addRow(self.ptt)
        form.addRow("本地语音引擎", QLabel("Whisper + M2M100 + OpenJTalk · CPU"))
        self.route_status = QLabel()
        self.route_status.setWordWrap(True)
        form.addRow("开源虚拟麦克风", self.route_status)
        self.screen = QComboBox()
        for index, screen in enumerate(QApplication.screens()):
            self.screen.addItem(f"屏幕 {index + 1} · {screen.name()}", index)
        self.screen.setCurrentIndex(min(self.settings.screen, self.screen.count() - 1))
        form.addRow("字幕显示器", self.screen)
        self.font_size = QSpinBox()
        self.font_size.setRange(16, 60)
        self.font_size.setValue(self.settings.font_size)
        form.addRow("字幕字号", self.font_size)
        self.margin = QSpinBox()
        self.margin.setRange(0, 500)
        self.margin.setValue(self.settings.bottom_margin)
        form.addRow("字幕距屏幕底部（像素）", self.margin)
        self.preview = QPushButton("预览底部字幕")
        self.preview.clicked.connect(self.preview_subtitle)
        form.addRow(self.preview)
        self.tabs.addTab(controls, "设备与字幕")
        self.playback_controls = QWidget()
        playback_form = QFormLayout(self.playback_controls)
        self.listen = QComboBox()
        playback_form.addRow("本地译音播放到耳机 / 扬声器", self.listen)
        self.incoming_voice = QCheckBox("队友日语 → 中文播报，同时显示中文字幕")
        self.incoming_voice.setChecked(self.settings.speak_incoming)
        self.incoming_voice.toggled.connect(self.update_mode)
        playback_form.addRow(self.incoming_voice)
        self.outgoing_monitor = QCheckBox("试听我说中文后生成的日语")
        self.outgoing_monitor.setChecked(self.settings.monitor_outgoing)
        self.outgoing_monitor.toggled.connect(self.update_mode)
        playback_form.addRow(self.outgoing_monitor)
        hint = QLabel("本地播放直接使用现有耳机，无需新驱动。若未勾选发送，日语只供自己试听。\n\n"
                      "当前监听整台设备的回环。为防止译音被再次识别，译音播放期间及结束后约 0.3 秒，"
                      "暂停接收与麦克风采集；这段时间的重叠讲话可能漏收。\n\n"
                      "这里的播放设备选择不会在 Windows 中创建新的虚拟扬声器。")
        hint.setWordWrap(True)
        playback_form.addRow(hint)
        self.tabs.addTab(self.playback_controls, "译音播放")
        self.history = QTextEdit()
        self.history.setReadOnly(True)
        self.history.document().setMaximumBlockCount(300)
        self.tabs.addTab(self.history, "实时翻译记录")
        guide = QTextEdit()
        guide.setReadOnly(True)
        guide.setPlainText(
            "首次使用\n\n"
            "1. 运行 setup.ps1，安装依赖并下载本地模型。之后翻译可以断网运行。\n\n"
            "本地双向试听：选择实体麦克风和接收回环，在「译音播放」页选择耳机，"
            "启用中文播报与日语试听；保持虚拟麦克风发送关闭即可无需驱动使用。\n\n"
            "只收队友：勾选「仅接收队友语音」；若只看字幕，再关闭「译音播放」页的中文播报。\n\n"
            "2. 开源音频驱动接入说明见 drivers/README.md。当前支持 RadioVoice 的 GPL 驱动端点。"
            "未安装驱动时，虚拟麦克风尚不可用。\n\n"
            "3. 本软件：实体麦克风选你的麦克风；接收语音选耳机对应的 [Loopback]；"
            "日语输出选 RadioVoice Output。\n\n"
            "4. 游戏 / Discord / 其他语音软件：输入设备选 RadioVoice Microphone；输出设备选耳机。"
            "目标软件使用语音激活或持续输入；它的按键说话必须覆盖翻译播放时段，"
            "本软件 F8 松开后才开始翻译。\n\n"
            "5. 开始翻译，按住 F8 说中文，松开。日语队友讲话会在屏幕底部显示中文。\n\n"
            "耳机回环包含该耳机播放的全部声音。为了减少游戏音效干扰，"
            "可将聊天软件输出单独路由到另一条音频线，再监听该音频线回环。\n\n"
            "独占全屏游戏可能遮住字幕，请选择无边框窗口。字幕窗口不接收鼠标点击。\n\n"
            "内置 OpenJTalk 的 Mei 日语声库采用 CC BY 3.0，归属信息见 DEPENDENCIES.md。\n\n"
            "此版本保持系统安全设置不变，不自动安装内核驱动，不开启测试签名。"
            "上游驱动当前要求测试模式，尚未验证可在你保留现有安全设置时使用。\n\n"
            "翻译按短句处理；语音停顿约 0.4 秒后提交，连续讲话约 5 秒分段。"
            "实际延迟取决于硬件、模型和排队情况，记录页显示处理耗时。"
        )
        self.tabs.addTab(guide, "连接指引")
        row = QHBoxLayout()
        self.start_button = QPushButton("开始翻译")
        self.start_button.clicked.connect(self.start)
        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop)
        row.addWidget(self.start_button)
        row.addWidget(self.stop_button)
        layout.addLayout(row)
        self.status = QLabel("就绪 · 请先选择三个音频设备")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.poll = QTimer(self)
        self.poll.timeout.connect(self.poll_ptt)
        self.poll.start(20)
        self.refresh_devices()
        self.update_mode()

    def update_mode(self):
        sending = not self.receive_only.isChecked()
        self.mic.setEnabled(sending)
        self.output.setEnabled(sending and self.send_virtual.isChecked())
        self.send_virtual.setEnabled(sending)
        self.ptt.setEnabled(sending)
        self.outgoing_monitor.setEnabled(sending)
        self.listen.setEnabled(self.incoming_voice.isChecked() or (sending and self.outgoing_monitor.isChecked()))
        if hasattr(self, "status") and self.service is None:
            if not sending:
                self.status.setText("就绪 · 接收队友语音，显示字幕及可选中文播报")
            else:
                self.status.setText("就绪 · " + ("启用虚拟麦克风发送" if self.send_virtual.isChecked()
                                                else "本地双向译音试听，不向游戏发送日语"))

    def refresh_devices(self):
        try:
            with pa.PyAudio() as p:
                available = devices(p)
                try:
                    default_receive = int(p.get_default_wasapi_loopback()["index"])
                except OSError:
                    default_receive = None
                default_listen = p.get_host_api_info_by_type(pa.paWASAPI)["defaultOutputDevice"]
            for combo, kind, saved in [(self.mic, "microphone", self.settings.microphone),
                                       (self.receive, "receive", self.settings.receive_device),
                                       (self.output, "output", self.settings.output_device),
                                       (self.listen, "listen", self.settings.listen_device)]:
                current = combo.currentText() or saved
                combo.clear()
                choices = available["output" if kind == "listen" else kind]
                if kind == "output":
                    choices = [(key, index) for key, index in choices if is_open_output(key)]
                elif kind == "listen":
                    choices = [(key, index) for key, index in choices if not is_open_output(key)]
                for key, _ in choices:
                    combo.addItem(key)
                index = combo.findText(current)
                if index >= 0:
                    combo.setCurrentIndex(index)
                elif kind == "output":
                    candidates = [i for i in range(combo.count()) if is_open_output(combo.itemText(i))]
                    candidates.sort(key=lambda i: "wasapi" not in combo.itemText(i).lower())
                    combo.setCurrentIndex(candidates[0] if candidates else -1)
                elif kind == "receive":
                    candidates = [i for i, (_, device_index) in enumerate(available[kind])
                                  if device_index == default_receive]
                    combo.setCurrentIndex(candidates[0] if candidates else -1)
                elif kind == "listen":
                    candidates = [i for i, (_, device_index) in enumerate(choices) if device_index == default_listen]
                    combo.setCurrentIndex(candidates[0] if candidates else (0 if choices else -1))
                else:
                    combo.setPlaceholderText("请选择你的实体麦克风")
                    combo.setCurrentIndex(-1)
            self.route_status.setText("已检测到开源驱动端点；实际收发仍需联调" if self.output.count()
                                      else "未检测到兼容开源驱动 · 虚拟麦克风尚不可用")
        except Exception as exc:
            self.status.setText(f"读取音频设备失败：{exc}")

    def save(self):
        self.settings.microphone = self.mic.currentText()
        self.settings.receive_device = self.receive.currentText()
        self.settings.output_device = self.output.currentText()
        self.settings.receive_only = self.receive_only.isChecked()
        self.settings.send_to_virtual = self.send_virtual.isChecked()
        self.settings.listen_device = self.listen.currentText()
        self.settings.speak_incoming = self.incoming_voice.isChecked()
        self.settings.monitor_outgoing = self.outgoing_monitor.isChecked()
        self.settings.push_to_talk = self.ptt.isChecked()
        self.settings.screen = self.screen.currentData() or 0
        self.settings.font_size = self.font_size.value()
        self.settings.bottom_margin = self.margin.value()
        self.settings.save()

    def preview_subtitle(self):
        self.save()
        self.overlay.display("味方が右にいます。一緒に行こう。", "队友在右边，一起走吧。")

    def start(self):
        required = [self.receive]
        if not self.receive_only.isChecked():
            required.append(self.mic)
            if self.send_virtual.isChecked():
                required.append(self.output)
            elif not self.outgoing_monitor.isChecked():
                QMessageBox.information(self, "请选择日语输出", "请启用本地日语试听或虚拟麦克风发送；也可勾选仅接收队友语音。")
                return
        if self.incoming_voice.isChecked() or (not self.receive_only.isChecked() and self.outgoing_monitor.isChecked()):
            required.append(self.listen)
        if not all(combo.currentText() for combo in required):
            message = "请选择所需的实体麦克风、接收回环和本地译音播放设备。"
            if self.send_virtual.isChecked() and not self.receive_only.isChecked():
                message += "虚拟麦克风发送还需 RadioVoice Output；说明见 drivers/README.md。"
            QMessageBox.information(self, "请选择设备", message)
            return
        self.save()
        self.stop_requested = False
        self.service = Service(self.settings)
        self.service.events.status.connect(self.status.setText)
        self.service.events.subtitle.connect(self.overlay.display)
        self.service.events.transcript.connect(self.record)
        self.service.events.finished.connect(self.finished)
        self.start_button.setEnabled(False)
        self.tabs.widget(0).setEnabled(False)
        self.playback_controls.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText("正在准备本地模型…")
        self.service.start()

    def poll_ptt(self):
        if self.service:
            if ctypes.windll.user32.GetAsyncKeyState(0x77) & 0x8000:
                self.service.talking.set()
            else:
                self.service.talking.clear()

    def record(self, direction, original, translated, elapsed):
        label = "队友 → 你" if direction == "in" else "你 → 队友"
        self.history.append(f"<b>{label}</b> · 处理 {elapsed:.1f}s<br>"
                            f"{html.escape(original)}<br><b>{html.escape(translated)}</b><br>")

    def stop(self):
        self.stop_requested = True
        if self.service:
            self.service.stop.set()
            self.service.talking.clear()
        self.stop_button.setEnabled(False)
        self.status.setText("正在停止，等待当前模型计算结束…")
        self.overlay.hide()

    def finished(self):
        self.service = None
        if self.stop_requested:
            self.status.setText("已停止 · 可以调整设置后重新开始")
        self.overlay.hide()
        self.start_button.setEnabled(True)
        self.tabs.widget(0).setEnabled(True)
        self.playback_controls.setEnabled(True)
        self.stop_button.setEnabled(False)
        if self.closing:
            self.close()

    def closeEvent(self, event: QCloseEvent):
        if self.service:
            self.closing = True
            self.stop()
            event.ignore()
        else:
            self.overlay.close()
            event.accept()


def create_application(argv=None):
    QLocale.setDefault(QLocale("zh_CN"))
    app = QApplication(sys.argv if argv is None else argv)
    if "Microsoft YaHei UI" not in QFontDatabase.families():
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("msyh.ttc", "segoeui.ttf"):
            QFontDatabase.addApplicationFont(str(fonts / name))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyle("Fusion")
    app.setStyleSheet("QWidget { background: #131925; color: #eef0f8; font-size: 14px; }"
                       "QComboBox, QTextEdit { background: #202b3e; padding: 6px; }"
                       "QSpinBox { background: #202b3e; min-height: 32px; padding: 0 6px; }"
                       "QPushButton { background: #354787; border-radius: 6px; padding: 10px; }"
                       "QPushButton:disabled { background: #262e41; color: #8890a3; }")
    return app


def main():
    if sys.platform != "win32":
        raise SystemExit("Speak Sound 目前仅支持 Windows 11 / WASAPI")
    app = create_application()
    window = Window()
    window.show()
    sys.exit(app.exec())
