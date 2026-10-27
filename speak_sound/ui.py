import ctypes
import html
import os
import sys
import threading
import subprocess
from pathlib import Path

import pyaudiowpatch as pa
from PySide6.QtCore import Qt, QTimer, QLocale, Signal
from PySide6.QtGui import QCloseEvent, QFont, QFontDatabase, QColor, QPalette
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFormLayout,
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QSpinBox,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget, QSlider, QDoubleSpinBox, QScrollArea,
    QGraphicsDropShadowEffect)

from .audio import devices
from .config import Settings
from .service import Service
from .routing import is_open_output, is_virtual_microphone, is_default_input_alias
from .process_audio import running_processes
from .virtual_mic import VirtualMicrophone
from .voice import PRESETS
from . import __version__
from .subtitles import subtitle_pages
from .presentation import assemble_window, stylesheet, brand_icon


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
        layout.setContentsMargins(10, 8, 10, 8)
        self.label = QLabel()
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setWordWrap(False)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        shadow = QGraphicsDropShadowEffect(self.label)
        shadow.setBlurRadius(7)
        shadow.setOffset(0, 1)
        shadow.setColor(QColor(0, 0, 0, 240))
        self.label.setGraphicsEffect(shadow)
        self.pages = []
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.next_page)

    def display(self, original, translated):
        self.setStyleSheet("background: transparent;")
        self.label.setStyleSheet("QLabel { color: white; background: transparent; padding: 0;"
                                  f"font-size: {self.settings.font_size}px; }}")
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(self.settings.font_size)
        self.label.setFont(font)
        self.label.ensurePolished()
        screens = QApplication.screens()
        screen = screens[max(0, min(self.settings.screen, len(screens) - 1))]
        rect = screen.geometry()
        width = min(1200, int(rect.width() * .72))
        self.setFixedWidth(width)
        metrics = self.label.fontMetrics()
        height = metrics.lineSpacing() * 2 + 20
        self.setFixedHeight(height)
        self.pages = subtitle_pages(translated, metrics.horizontalAdvance, width - 24,
                                    lines=1 if self.settings.subtitle_original else 2)
        self.original = metrics.elidedText(" ".join(original.split()), Qt.TextElideMode.ElideRight, width - 24)
        self.move(rect.x() + (rect.width() - width) // 2,
                  rect.bottom() - self.settings.bottom_margin - height)
        self.next_page()

    def next_page(self):
        if not self.pages:
            self.hide()
            return
        page = self.pages.pop(0)
        self.label.setText(page + ("\n" + self.original if self.settings.subtitle_original and self.original else ""))
        self.show()
        # New incoming subtitles replace pending pages, keeping the overlay current.
        self.timer.start(min(self.settings.subtitle_seconds * 1000, max(1800, len(page) * 65)))

    def hideEvent(self, event):
        self.pages.clear()
        self.timer.stop()
        super().hideEvent(event)


class Window(QMainWindow):
    virtual_finished = Signal(str)

    def __init__(self):
        super().__init__()
        try:
            self.settings = Settings.load()
        except (ValueError, TypeError):
            self.settings = Settings()
        self.service = None
        self.closing = False
        self.stop_requested = False
        self.virtual = VirtualMicrophone()
        self.virtual_busy = False
        self.virtual_finished.connect(self.virtual_ready)
        self.overlay = Subtitle(self.settings)
        self.setWindowTitle(f"Speak Sound {__version__} · 双向翻译与变声")
        self.resize(850, 700)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        title = QLabel("Speak Sound")
        title.setStyleSheet("font-size: 24px; font-weight: 600; color: #ffffff;")
        layout.addWidget(title)
        layout.addWidget(QLabel("中文 → 日语 / 英语虚拟麦克风    ·    队友外语 → 底部中文字幕"))
        self.operating_mode = QComboBox()
        layout.addWidget(QLabel("功能模式 · 仅双向翻译 / 翻译与变声同时运行"))
        self.operating_mode.addItem("仅双向翻译（不变声）", "translation_only")
        self.operating_mode.addItem("日语译音变声 → 虚拟麦克风（推荐）", "translation")
        self.operating_mode.addItem("原声实时变声 → 虚拟麦克风，同时双向翻译", "live_translation")
        self.operating_mode.setCurrentIndex(self.operating_mode.findData(self.settings.operating_mode))
        layout.addWidget(self.operating_mode)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        controls = QWidget()
        form = QFormLayout(controls)
        self.target_language, self.incoming_language = QComboBox(), QComboBox()
        for combo, saved in ((self.target_language, self.settings.target_language),
                             (self.incoming_language, self.settings.incoming_language)):
            combo.addItem("日语", "ja")
            combo.addItem("英语", "en")
            combo.setCurrentIndex(combo.findData(saved))
        form.addRow("我的中文翻译成", self.target_language)
        form.addRow("队友说的语言", self.incoming_language)
        self.mic, self.receive, self.output = QComboBox(), QComboBox(), QComboBox()
        form.addRow("你的实体麦克风", self.mic)
        self.receive_mode = QComboBox()
        self.receive_mode.addItem("整个播放设备（回环）", "device")
        self.receive_mode.addItem("指定运行进程（包含子进程）", "process")
        self.receive_mode.setCurrentIndex(self.receive_mode.findData(self.settings.receive_mode))
        self.receive_mode.currentIndexChanged.connect(self.update_mode)
        form.addRow("接收来源", self.receive_mode)
        self.speech_filter = QComboBox()
        for name, key in (("标准 · 神经网络语音检测 + 置信度过滤", "standard"),
                          ("严格 · 更少音效误触发，可能漏掉短句", "strict"),
                          ("关闭神经网络检测（仍过滤异常识别文本）", "off")):
            self.speech_filter.addItem(name, key)
        self.speech_filter.setCurrentIndex(self.speech_filter.findData(self.settings.speech_filter))
        form.addRow("接收人声筛选", self.speech_filter)
        separation_hint = QLabel("游戏内语音与音效混合时，筛选可减少非人声触发，但不能辨认谁在说话，"
                                "也会接收角色对白。若游戏提供独立聊天输出，将它送到独立设备后选对应回环；"
                                "使用 Discord 时选其进程，可排除其他游戏声音。")
        separation_hint.setWordWrap(True)
        form.addRow(separation_hint)
        process_row = QWidget()
        process_layout = QHBoxLayout(process_row)
        process_layout.setContentsMargins(0, 0, 0, 0)
        self.process = QComboBox()
        self.process.setEditable(True)
        self.process.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.process.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        process_layout.addWidget(self.process, 1)
        self.process_refresh = QPushButton("刷新进程")
        self.process_refresh.clicked.connect(self.refresh_processes)
        process_layout.addWidget(self.process_refresh)
        form.addRow("接收进程（可输入名称筛选）", process_row)
        form.addRow("接收语音（耳机/音频线的回环）", self.receive)
        form.addRow("发送输出（虚拟音频线播放端）", self.output)
        self.receive_only = QCheckBox("仅接收队友语音（关闭我的麦克风）")
        self.receive_only.setChecked(self.settings.receive_only)
        self.receive_only.toggled.connect(self.update_mode)
        form.addRow(self.receive_only)
        self.send_virtual = QCheckBox("向虚拟麦克风发送声音")
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
        self.virtual_button = QPushButton("连接 Speak Sound 虚拟麦克风")
        self.virtual_button.clicked.connect(self.toggle_virtual)
        form.addRow(self.virtual_button)
        install = QPushButton("查看 / 准备开源驱动安装包")
        install.clicked.connect(self.prepare_driver)
        form.addRow(install)
        self.screen = QComboBox()
        for index, screen in enumerate(QApplication.screens()):
            self.screen.addItem(f"屏幕 {index + 1} · {screen.name()}", index)
        self.screen.setCurrentIndex(min(self.settings.screen, self.screen.count() - 1))
        form.addRow("字幕显示器", self.screen)
        self.font_size = QSpinBox()
        self.font_size.setRange(16, 60)
        self.font_size.setValue(self.settings.font_size)
        form.addRow("字幕字号", self.font_size)
        self.subtitle_original = QCheckBox("字幕附带外语原文（总计最多两行）")
        self.subtitle_original.setChecked(self.settings.subtitle_original)
        form.addRow(self.subtitle_original)
        form.addRow(QLabel("字幕背景透明，默认只显示中文；长句分页，完整内容保留在记录页。"))
        self.margin = QSpinBox()
        self.margin.setRange(0, 500)
        self.margin.setValue(self.settings.bottom_margin)
        form.addRow("字幕距屏幕底部（像素）", self.margin)
        self.preview = QPushButton("预览底部字幕")
        self.preview.clicked.connect(self.preview_subtitle)
        form.addRow(self.preview)
        device_scroll = QScrollArea()
        device_scroll.setWidgetResizable(True)
        device_scroll.setWidget(controls)
        self.tabs.addTab(device_scroll, "设备与字幕")
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
        hint = QLabel("本地播放直接使用现有耳机，无需新驱动。若未勾选发送，外语只供自己试听。\n\n"
                      "指定进程模式只收目标及其子进程的声音，播放译音时仍可收队友。"
                      "整个设备模式会在译音播放时暂停接收，以防循环翻译。"
                      "实体麦克风在译音播放时均暂停，建议佩戴耳机。\n\n"
                      "播放设备选择不会创建 Windows 虚拟扬声器；下面的音量只影响本地译音。")
        hint.setWordWrap(True)
        playback_form.addRow(hint)
        self.tabs.addTab(self.playback_controls, "译音播放")
        voice_page = QWidget()
        self.voice_controls = voice_page
        voice_form = QFormLayout(voice_page)
        voice_form.addRow(QLabel("顶部选择「仅双向翻译」时，此页不生效；原有音效设置会保留。"))
        self.voice_enable = QCheckBox("启用变声（实时麦克风或发送的日语译音）")
        self.voice_enable.setChecked(self.settings.voice_enabled)
        voice_form.addRow(self.voice_enable)
        self.monitor_live_voice = QCheckBox("监听原声实时变声（请戴耳机；仅原声发送方式）")
        self.monitor_live_voice.setChecked(self.settings.monitor_live_voice)
        self.monitor_live_voice.toggled.connect(self.update_live_monitor)
        voice_form.addRow(self.monitor_live_voice)
        self.voice_preset = QComboBox()
        self.voice_preset.addItem("自定义", "custom")
        for key, (label, pitch, effect) in PRESETS.items():
            self.voice_preset.addItem(label, key)
        voice_form.addRow("音效预设", self.voice_preset)
        self.voice_pitch = QDoubleSpinBox()
        self.voice_pitch.setRange(-12, 12)
        self.voice_pitch.setDecimals(1)
        self.voice_pitch.setSingleStep(.5)
        self.voice_pitch.setSuffix(" 半音")
        self.voice_pitch.setValue(self.settings.voice_pitch)
        voice_form.addRow("音高（低沉 ← 0 → 明亮）", self.voice_pitch)
        self.voice_effect = QComboBox()
        for label, key in (("干净", "clean"), ("机器人", "robot"), ("电台", "radio")):
            self.voice_effect.addItem(label, key)
        self.voice_effect.setCurrentIndex(self.voice_effect.findData(self.settings.voice_effect))
        voice_form.addRow("附加音效", self.voice_effect)
        matching = next((key for key, (_, pitch, effect) in PRESETS.items()
                         if pitch == self.settings.voice_pitch and effect == self.settings.voice_effect), "custom")
        self.voice_preset.setCurrentIndex(self.voice_preset.findData(matching))
        self.voice_preset.currentIndexChanged.connect(self.apply_voice_preset)
        self.voice_enable.toggled.connect(self.update_voice)
        self.voice_pitch.valueChanged.connect(self.update_voice)
        self.voice_effect.currentIndexChanged.connect(self.update_voice)
        voice_hint = QLabel("变声与双向翻译同时运行。推荐发送外语译音：中文先翻译成所选日语或英语，再变声发送；"
                            "队友外语持续翻译为中文字幕和中文播报，中文播报不加变声。\n\n"
                            "也可选择原声实时发送：按住 F8 立即发送变声后的原语言，松开提交翻译；"
                            "外语译文仍显示在记录页，并可本地试听，但不会再向游戏发送外语译音。"
                            "所有模式均使用本地模型。选择「仅双向翻译」可直接发送合成译音，不进行变声。\n\n"
                            "音高、音效与启用开关可运行时调整。此功能为本地 DSP 音效，"
                            "没有 AI 音色克隆或共振峰保持，不能保证模仿特定人物。\n\n"
                            "实时变声监听必须戴耳机，避免扬声器声音进入麦克风形成啸叫。"
                            "Windows 虚拟麦克风需先在设备页连接；仅试听不需要驱动。")
        voice_hint.setWordWrap(True)
        voice_form.addRow(voice_hint)
        voice_scroll = QScrollArea()
        voice_scroll.setWidgetResizable(True)
        voice_scroll.setWidget(voice_page)
        self.tabs.addTab(voice_scroll, "变声器")
        self.timing_controls = QWidget()
        timing_form = QFormLayout(self.timing_controls)
        self.speed = QComboBox()
        self.speed.addItem("均衡 · 更完整的识别与翻译搜索", "balanced")
        self.speed.addItem("快速 · 减少模型搜索，可能降低准确率", "fast")
        self.speed.setCurrentIndex(self.speed.findData(self.settings.speed_mode))
        timing_form.addRow("计算模式", self.speed)
        self.asr_threads = QSpinBox()
        self.asr_threads.setRange(1, 16)
        self.asr_threads.setValue(self.settings.asr_threads)
        timing_form.addRow("识别 CPU 线程数", self.asr_threads)
        self.silence = QSpinBox()
        self.silence.setRange(100, 1500)
        self.silence.setSingleStep(20)
        self.silence.setSuffix(" ms")
        self.silence.setValue(self.settings.silence_ms)
        timing_form.addRow("停顿后等待多久提交", self.silence)
        self.segment = QDoubleSpinBox()
        self.segment.setRange(1, 10)
        self.segment.setSingleStep(.5)
        self.segment.setSuffix(" 秒")
        self.segment.setValue(self.settings.max_speech_seconds)
        timing_form.addRow("连续讲话最长分段", self.segment)
        self.incoming_silence = QSpinBox()
        self.incoming_silence.setRange(100, 1500)
        self.incoming_silence.setSingleStep(20)
        self.incoming_silence.setSuffix(" ms")
        self.incoming_silence.setValue(self.settings.incoming_silence_ms)
        timing_form.addRow("队友停顿提交等待", self.incoming_silence)
        self.incoming_segment = QDoubleSpinBox()
        self.incoming_segment.setRange(1, 6)
        self.incoming_segment.setSingleStep(.5)
        self.incoming_segment.setSuffix(" 秒")
        self.incoming_segment.setValue(self.settings.incoming_max_seconds)
        timing_form.addRow("队友最长分段（控制字幕出字频率）", self.incoming_segment)
        quick = QPushButton("应用低延迟预设（200 ms / 3 秒 / 快速）")
        quick.clicked.connect(lambda: self.set_timing("fast", 200, 3))
        timing_form.addRow(quick)
        balanced = QPushButton("应用均衡预设（400 ms / 5 秒）")
        balanced.clicked.connect(lambda: self.set_timing("balanced", 400, 5))
        timing_form.addRow(balanced)
        timing_hint = QLabel("停止后可调整，下次开始生效。F8 松开即提交，不额外等待停顿。\n\n"
                            "等待越短，出字幕越快，但自然停顿更容易把一句话切断；分段越短，"
                            "长句越早开始处理，但上下文减少、计算次数增加。\n\n"
                            "接收默认 240 ms / 2.5 秒独立分段，只保留最新一条待处理语音，避免旧字幕积压。\n\n"
                            "两种计算模式都取消温度回退重试；快速模式进一步减少搜索。增加 CPU 线程数可能加速，也会占用游戏资源，"
                            "并非越多越快。低延迟预设最多使用 8 线程，均衡使用 4 线程。\n\n"
                            "总延迟还包括识别、翻译、语音合成和排队；这些数值不是总耗时上限。"
                            "记录页的处理时间仅包含识别与翻译。")
        timing_hint.setWordWrap(True)
        timing_form.addRow(timing_hint)
        timing_scroll = QScrollArea()
        timing_scroll.setWidgetResizable(True)
        timing_scroll.setWidget(self.timing_controls)
        self.tabs.addTab(timing_scroll, "速度与延迟")
        # Outside the disabled settings tabs: gain and mute remain live while running.
        volume_box = QWidget()
        volume_form = QFormLayout(volume_box)
        self.incoming_volume = QSlider(Qt.Orientation.Horizontal)
        self.outgoing_volume = QSlider(Qt.Orientation.Horizontal)
        self.volume_labels = []
        for slider, value, label in ((self.incoming_volume, self.settings.incoming_volume, "队友中文播报音量"),
                                      (self.outgoing_volume, self.settings.outgoing_volume, "我的译音 / 原声监听音量")):
            slider.setRange(0, 100)
            slider.setValue(value)
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(slider, 1)
            percentage = QLabel(f"{value}%")
            percentage.setMinimumWidth(45)
            self.volume_labels.append(percentage)
            row_layout.addWidget(percentage)
            slider.valueChanged.connect(self.update_volume)
            volume_form.addRow(label, row_widget)
        self.mute = QCheckBox("静音本地译音（不影响虚拟麦克风发送）")
        self.mute.setChecked(self.settings.playback_muted)
        self.mute.toggled.connect(self.update_volume)
        volume_form.addRow(self.mute)
        layout.addWidget(volume_box)
        self.volume_save = QTimer(self)
        self.volume_save.setSingleShot(True)
        self.volume_save.timeout.connect(self.settings.save)
        self.send_volume = QSlider(Qt.Orientation.Horizontal)
        self.send_volume.setRange(0, 100)
        self.send_volume.setValue(self.settings.send_volume)
        self.send_volume.valueChanged.connect(self.update_volume)
        volume_form.addRow("虚拟麦克风发送音量", self.send_volume)
        self.send_mute = QCheckBox("静音虚拟麦克风发送（不影响本地监听）")
        self.send_mute.setChecked(self.settings.send_muted)
        self.send_mute.toggled.connect(self.update_volume)
        volume_form.addRow(self.send_mute)
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
            "在「字幕与播放」启用中文播报与外语试听；保持虚拟麦克风发送关闭即可无需驱动使用。\n\n"
            "只收队友：勾选「只接收队友」；若只看字幕，再关闭「字幕与播放」的中文播报。\n\n"
            "2. 按 drivers/README.md 安装签名开源 USB/IP 运输驱动，再在「音频连接」点击连接虚拟麦克风。"
            "这会创建 Speak Sound Virtual Cable 的播放端和麦克风端；保持系统安全设置不变。\n\n"
            "3. 本软件：实体麦克风选你的麦克风；接收语音选耳机对应的 [Loopback]；"
            "发送输出选 Speak Sound Virtual Cable 的播放端。\n\n"
            "4. 游戏 / Discord / 其他语音软件：输入设备选 Speak Sound Virtual Cable 的麦克风端；输出设备选耳机。"
            "目标软件使用语音激活或持续输入；它的按键说话必须覆盖翻译播放时段，"
            "本软件 F8 松开后才开始翻译。\n\n"
            "5. 在「语音工作台」分别选择发送语言（日语 / 英语）和队友语言，再开始翻译。"
            "按住 F8 说中文、松开；队友讲话会在底部显示中文，透明背景、最多两行。\n\n"
            "耳机回环包含该耳机播放的全部声音。为了减少游戏音效干扰，"
            "可改选「指定运行进程」，刷新并选择 Discord 或游戏 PID。采集包含子进程，"
            "不能在同一个游戏进程中分离队友语音与游戏音效。进程退出后停止，重启需重新选择。\n\n"
            "独占全屏游戏可能遮住字幕，请选择无边框窗口。字幕窗口不接收鼠标点击。\n\n"
            "内置 OpenJTalk 的 Mei 日语声库采用 CC BY 3.0，归属信息见 DEPENDENCIES.md。\n\n"
            "签名 USB/IP 驱动需单独安装；安装会短暂重启 USB 设备。软件不修改安全启动、"
            "测试签名或证书存储。旧 RadioVoice 仍为可选接入。\n\n"
            "变声与翻译同时使用：顶部默认将中文翻译为所选外语后变声发送，队友翻译持续运行。"
            "选择原声实时发送时，游戏收到变声后的原语言，外语译文仍显示并可本地试听。"
            "在变声器页选择预设或调整半音；实时监听请戴耳机。\n\n"
            "独立双向翻译：顶部选择「仅双向翻译」，直接发送合成的外语译音，不应用变声音效；"
            "队友字幕、中文播报、外语试听与音量设置照常使用。变声页的设置会保留，切回其他模式后恢复。\n\n"
            "在「速度与延迟」页调整停顿等待、最长分段和计算模式；下方音量与静音可实时调整。"
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
        assemble_window(self)
        self.poll = QTimer(self)
        self.poll.timeout.connect(self.poll_ptt)
        self.poll.start(20)
        self.refresh_devices()
        self.refresh_processes()
        self.operating_mode.currentIndexChanged.connect(self.update_mode)
        self.target_language.currentIndexChanged.connect(self.update_languages)
        self.incoming_language.currentIndexChanged.connect(self.update_languages)
        self.update_languages()
        self.update_mode()

    def update_languages(self):
        target, source = self.target_language.currentText(), self.incoming_language.currentText()
        pair = f"中文与{target}" if target == source else f"中文 → {target} / {source} → 中文"
        self.operating_mode.setItemText(self.operating_mode.findData("translation_only"),
                                       f"仅双向翻译 · {pair}（不变声）")
        self.operating_mode.setItemText(self.operating_mode.findData("translation"),
                                       f"{target}译音变声 → 虚拟麦克风")
        self.incoming_voice.setText(f"队友{source} → 中文播报，同时显示中文字幕")
        self.outgoing_monitor.setText(f"试听我说中文后生成的{target}")
        self.update_mode()

    def refresh_summary(self, *unused):
        if not hasattr(self, "sending_path"):
            return
        mode = self.operating_mode.currentData()
        destination = "虚拟麦克风" if self.send_virtual.isChecked() else "本地试听"
        if self.receive_only.isChecked():
            route = "实体麦克风已关闭"
        elif mode == "live_translation":
            route = "原声 → " + ("变声 → " if self.voice_enable.isChecked() else "") + destination
        else:
            route = "中文 → " + self.target_language.currentText()
            if mode != "translation_only" and self.voice_enable.isChecked():
                route += " → 变声"
            route += " → " + destination
        self.sending_path.setText(route)
        receiving = self.incoming_language.currentText() + " → 中文 → 底部字幕"
        if self.incoming_voice.isChecked() and not self.mute.isChecked() and self.incoming_volume.value() > 0:
            receiving += " / 中文播报"
        self.receiving_path.setText(receiving)

    def audio_active(self, active):
        self.run_badge.setText("翻译中" if active else "已停止")
        self.run_badge.setProperty("active", active)
        self.run_badge.style().unpolish(self.run_badge)
        self.run_badge.style().polish(self.run_badge)

    def apply_voice_preset(self):
        key = self.voice_preset.currentData()
        if key in PRESETS:
            _, pitch, effect = PRESETS[key]
            self.voice_pitch.setValue(pitch)
            self.voice_effect.setCurrentIndex(self.voice_effect.findData(effect))
            self.voice_enable.setChecked(True)
            self.update_voice()

    def update_voice(self):
        self.settings.voice_enabled = self.voice_enable.isChecked()
        self.settings.voice_pitch = self.voice_pitch.value()
        self.settings.voice_effect = self.voice_effect.currentData()
        if hasattr(self, "volume_save"):
            self.volume_save.start(350)
        self.refresh_summary()

    def update_live_monitor(self):
        self.settings.monitor_live_voice = self.monitor_live_voice.isChecked()
        self.update_mode()
        if hasattr(self, "volume_save"):
            self.volume_save.start(350)

    def prepare_driver(self):
        QMessageBox.information(self, "开源虚拟麦克风", "驱动来源为 BSD 开源 usbip-win2 的签名发行版。\n"
            "此按钮只下载、核对哈希及签名，不安装。安装方法和 USB 设备短暂重启说明见 drivers/README.md。")
        subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                          str(Path(__file__).resolve().parents[1] / "drivers/setup_virtual_mic.ps1")],
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.status.setText("正在后台准备驱动包，保存在 downloads；此步骤不安装驱动")

    def toggle_virtual(self):
        if self.virtual_busy or self.service:
            return
        self.virtual_busy = True
        self.virtual_button.setEnabled(False)
        self.status.setText("正在连接 / 断开虚拟麦克风…")
        def work():
            try:
                if self.virtual.connected:
                    self.virtual.stop()
                    message = "已断开 Speak Sound 虚拟麦克风"
                else:
                    self.virtual.start()
                    message = "已连接虚拟 USB 声卡；刷新设备后选其播放端，游戏选择同名麦克风端"
            except Exception as exc:
                message = f"虚拟麦克风：{exc}"
            self.virtual_finished.emit(message)
        threading.Thread(target=work, name="virtual-microphone-manager", daemon=True).start()

    def virtual_ready(self, message):
        self.virtual_busy = False
        self.virtual_button.setEnabled(True)
        self.virtual_button.setText("断开 Speak Sound 虚拟麦克风" if self.virtual.connected else "连接 Speak Sound 虚拟麦克风")
        self.refresh_devices()
        self.status.setText(message)
        if self.virtual.connected:
            QTimer.singleShot(1500, self.refresh_devices)
        if self.closing:
            self.close()

    def refresh_processes(self):
        current = self.process.currentData()
        self.process.clear()
        for target in running_processes():
            self.process.addItem(f"{target.name} · PID {target.pid}", target)
        index = next((i for i in range(self.process.count()) if self.process.itemData(i) == current), -1)
        self.process.setCurrentIndex(index)
        self.process.setPlaceholderText("请选择游戏 / Discord 进程")

    def set_timing(self, mode, silence, segment):
        self.speed.setCurrentIndex(self.speed.findData(mode))
        self.silence.setValue(silence)
        self.segment.setValue(segment)
        self.incoming_silence.setValue(200 if mode == "fast" else 300)
        self.incoming_segment.setValue(2 if mode == "fast" else 3)
        self.asr_threads.setValue(min(8, max(1, (os.cpu_count() or 4) // 2)) if mode == "fast" else 4)

    def update_volume(self):
        self.settings.incoming_volume = self.incoming_volume.value()
        self.settings.outgoing_volume = self.outgoing_volume.value()
        self.settings.playback_muted = self.mute.isChecked()
        self.settings.send_volume = self.send_volume.value()
        self.settings.send_muted = self.send_mute.isChecked()
        for slider, label in zip((self.incoming_volume, self.outgoing_volume), self.volume_labels):
            label.setText(f"{slider.value()}%")
        self.volume_save.start(350)
        self.refresh_summary()

    def update_mode(self):
        if not hasattr(self, "outgoing_monitor"):
            return
        sending = not self.receive_only.isChecked()
        live = self.operating_mode.currentData() == "live_translation"
        translation_only = self.operating_mode.currentData() == "translation_only"
        if hasattr(self, "voice_controls"):
            self.voice_controls.setEnabled(not translation_only)
        by_process = self.receive_mode.currentData() == "process"
        self.process.setEnabled(by_process)
        self.process_refresh.setEnabled(by_process)
        self.receive.setEnabled(not by_process)
        if hasattr(self, "process_field"):
            self.process_field.setVisible(by_process)
            self.receive_device_field.setVisible(not by_process)
        self.mic.setEnabled(sending)
        self.output.setEnabled(sending and self.send_virtual.isChecked())
        self.send_virtual.setEnabled(sending)
        self.ptt.setEnabled(sending)
        self.outgoing_monitor.setEnabled(sending)
        live_monitor = hasattr(self, "monitor_live_voice") and self.monitor_live_voice.isChecked()
        if hasattr(self, "monitor_live_voice"):
            self.monitor_live_voice.setEnabled(live and sending and self.service is None)
        self.listen.setEnabled(self.incoming_voice.isChecked() or (sending and
                               (self.outgoing_monitor.isChecked() or (live and live_monitor))))
        self.ptt.setText("按住 F8 连续发送原声变声" if live else "按住 F8 说话，松开提交译文")
        if hasattr(self, "status") and self.service is None:
            self.start_button.setText("开始双向翻译" if translation_only else "开始双向翻译 + 变声")
            if not sending:
                self.status.setText("就绪 · 接收队友语音，显示字幕及可选中文播报")
            elif live:
                self.status.setText("就绪 · 原声实时变声发送 + 双向翻译；游戏收到原语言，外语译音可本地试听")
            elif translation_only:
                self.status.setText("就绪 · 独立双向翻译（不变声） · 中文 → " + self.target_language.currentText() +
                    (" · 虚拟麦克风发送" if self.send_virtual.isChecked() else " · 本地译音试听"))
            else:
                self.status.setText("就绪 · 中文翻译为" + self.target_language.currentText() + "后变声 · " +
                    ("启用虚拟麦克风发送" if self.send_virtual.isChecked() else "本地双向译音试听"))
        self.refresh_summary()

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
                elif kind == "microphone":
                    choices = [(key, index) for key, index in choices
                               if not is_virtual_microphone(key) and not is_default_input_alias(key)]
                elif kind == "receive":
                    choices = [(key, index) for key, index in choices if not is_virtual_microphone(key)]
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
            self.route_status.setText("已检测到开源虚拟播放端点；游戏选择配对的麦克风" if self.output.count()
                                      else "尚未连接开源虚拟声卡 · 安装签名 USB/IP 驱动后点击连接")
        except Exception as exc:
            self.status.setText(f"读取音频设备失败：{exc}")

    def save(self):
        self.settings.target_language = self.target_language.currentData()
        self.settings.incoming_language = self.incoming_language.currentData()
        self.settings.speech_filter = self.speech_filter.currentData()
        self.settings.incoming_silence_ms = self.incoming_silence.value()
        self.settings.incoming_max_seconds = self.incoming_segment.value()
        self.settings.subtitle_original = self.subtitle_original.isChecked()
        self.settings.operating_mode = self.operating_mode.currentData()
        self.settings.microphone = self.mic.currentText()
        self.settings.receive_device = self.receive.currentText()
        self.settings.receive_mode = self.receive_mode.currentData()
        self.settings.speed_mode = self.speed.currentData()
        self.settings.asr_threads = self.asr_threads.value()
        self.settings.silence_ms = self.silence.value()
        self.settings.max_speech_seconds = self.segment.value()
        self.settings.output_device = self.output.currentText()
        self.settings.receive_only = self.receive_only.isChecked()
        self.settings.send_to_virtual = self.send_virtual.isChecked()
        self.settings.listen_device = self.listen.currentText()
        self.settings.speak_incoming = self.incoming_voice.isChecked()
        self.settings.monitor_outgoing = self.outgoing_monitor.isChecked()
        self.settings.monitor_live_voice = self.monitor_live_voice.isChecked()
        self.settings.push_to_talk = self.ptt.isChecked()
        self.settings.screen = self.screen.currentData() or 0
        self.settings.font_size = self.font_size.value()
        self.settings.bottom_margin = self.margin.value()
        self.settings.save()

    def preview_subtitle(self):
        self.save()
        self.overlay.display("味方が右にいます。一緒に行こう。", "队友在右边，一起走吧。")

    def start(self):
        if self.virtual_busy:
            QMessageBox.information(self, "虚拟麦克风连接中", "请等待虚拟声卡连接结束后再开始。")
            return
        live = self.operating_mode.currentData() == "live_translation"
        by_process = self.receive_mode.currentData() == "process"
        target = self.process.currentData() if by_process else None
        if by_process and (target is None or self.process.currentText() != f"{target.name} · PID {target.pid}" or not target.alive()):
            QMessageBox.information(self, "请选择进程", "请刷新并从列表选择仍在运行的游戏或聊天进程。")
            return
        required = [] if by_process else [self.receive]
        if not self.receive_only.isChecked():
            required.append(self.mic)
            if self.send_virtual.isChecked():
                required.append(self.output)
            elif not (self.outgoing_monitor.isChecked() or (live and self.monitor_live_voice.isChecked())):
                QMessageBox.information(self, "请选择声音输出", "请启用本地试听或虚拟麦克风发送，也可勾选仅接收队友语音。")
                return
        if self.incoming_voice.isChecked() or (not self.receive_only.isChecked() and
                (self.outgoing_monitor.isChecked() or (live and self.monitor_live_voice.isChecked()))):
            required.append(self.listen)
        if not all(combo.currentText() for combo in required):
            message = "请选择所需的实体麦克风、接收回环和本地译音播放设备。"
            if self.send_virtual.isChecked() and not self.receive_only.isChecked():
                message += "虚拟麦克风发送需 Speak Sound Virtual Cable 播放端；说明见 drivers/README.md。"
            QMessageBox.information(self, "请选择设备", message)
            return
        self.save()
        self.stop_requested = False
        self.service = Service(self.settings, target)
        self.service.events.status.connect(self.status.setText)
        self.service.events.subtitle.connect(self.overlay.display)
        self.service.events.transcript.connect(self.record)
        self.service.events.finished.connect(self.finished)
        self.service.events.active.connect(self.audio_active)
        self.start_button.setEnabled(False)
        self.operating_mode.setEnabled(False)
        for widget in self.run_locked_widgets:
            widget.setEnabled(False)
        self.monitor_live_voice.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status.setText("正在准备本地模型与双向音频…")
        self.run_badge.setText("准备中")
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
        self.translation_preview.display(direction, original, translated, elapsed)

    def stop(self):
        self.stop_requested = True
        if self.service:
            self.service.stop.set()
            self.service.talking.clear()
        self.stop_button.setEnabled(False)
        self.status.setText("正在停止，等待当前模型计算结束…")
        self.run_badge.setText("停止中")
        self.overlay.hide()

    def finished(self):
        self.service = None
        if self.stop_requested:
            self.status.setText("已停止 · 可以调整设置后重新开始")
        self.overlay.hide()
        self.start_button.setEnabled(True)
        self.operating_mode.setEnabled(True)
        for widget in self.run_locked_widgets:
            widget.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.monitor_live_voice.setEnabled(self.operating_mode.currentData() == "live_translation"
                                           and not self.receive_only.isChecked())
        self.audio_active(False)
        if self.closing:
            self.close()

    def closeEvent(self, event: QCloseEvent):
        if self.virtual_busy:
            self.closing = True
            event.ignore()
        elif self.service:
            self.closing = True
            self.stop()
            event.ignore()
        else:
            self.virtual.stop()
            self.overlay.close()
            event.accept()


def create_application(argv=None):
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Arthrealrt.SpeakSound")
        except (AttributeError, OSError):
            pass
    QLocale.setDefault(QLocale("zh_CN"))
    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("Speak Sound")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Speak Sound")
    app.setWindowIcon(brand_icon())
    if "Microsoft YaHei UI" not in QFontDatabase.families():
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("msyh.ttc", "segoeui.ttf"):
            QFontDatabase.addApplicationFont(str(fonts / name))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    font_path = Path(__file__).parent / "assets/InterVariable.ttf"
    if font_path.exists():
        QFontDatabase.addApplicationFont(str(font_path))
        font = QFont()
        font.setFamilies(["Inter Variable", "Inter", "Microsoft YaHei UI"])
        font.setPointSize(10)
        app.setFont(font)
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in ((QPalette.ColorRole.Window, "#000000"), (QPalette.ColorRole.Base, "#111111"),
                         (QPalette.ColorRole.Text, "#ffffff"), (QPalette.ColorRole.WindowText, "#ffffff"),
                         (QPalette.ColorRole.ButtonText, "#ffffff"), (QPalette.ColorRole.Button, "#262626"),
                         (QPalette.ColorRole.Highlight, "#444444"), (QPalette.ColorRole.HighlightedText, "#ffffff"),
                         (QPalette.ColorRole.PlaceholderText, "#949494")):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet())
    return app


def main():
    if sys.platform != "win32":
        raise SystemExit("Speak Sound 目前仅支持 Windows 11 / WASAPI")
    app = create_application()
    window = Window()
    window.show()
    sys.exit(app.exec())
