"""Native Qt presentation for the two audio directions. No audio is opened here."""
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QScrollArea, QTabWidget, QButtonGroup, QSizePolicy,
    QComboBox)

from . import __version__
from .subtitles import subtitle_pages
from .window_chrome import NavButton, TitleBar
from .hotkey import chord_text


def brand_icon():
    icon = QIcon()
    for size in (32, 64, 128):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(size / 40, size / 40)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#111111'))
        painter.drawRoundedRect(0, 0, 40, 40, 10, 10)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor('#ffffff'), 2.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        # Two opposite speech paths are the mark, not a simulated audio meter.
        path = QPainterPath()
        path.moveTo(5, 13); path.lineTo(12, 13); path.lineTo(16, 6)
        path.lineTo(23, 20); path.lineTo(27, 13); path.lineTo(35, 13)
        painter.drawPath(path)
        painter.setPen(QPen(QColor('#78d7b2'), 2.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        path = QPainterPath()
        path.moveTo(35, 27); path.lineTo(28, 27); path.lineTo(24, 34)
        path.lineTo(17, 20); path.lineTo(13, 27); path.lineTo(5, 27)
        painter.drawPath(path)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def text(value, role='body'):
    label = QLabel(value)
    label.setProperty('role', role)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


def column(widget=None, margins=0, gap=14):
    widget = widget or QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(margins, margins, margins, margins)
    layout.setSpacing(gap)
    return widget, layout


def panel(title, description=None):
    frame = QFrame()
    frame.setObjectName('panel')
    _, layout = column(frame, 18, 10)
    layout.addWidget(text(title, 'section'))
    if description:
        layout.addWidget(text(description, 'muted'))
    return frame, layout


def field(label, control):
    widget, layout = column(gap=5)
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    caption = text(label, 'label')
    caption.setBuddy(control)
    layout.addWidget(caption)
    layout.addWidget(control)
    control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return widget


def scroll(widget):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.viewport().setAutoFillBackground(False)
    area.setWidget(widget)
    return area


def page():
    widget, layout = column(margins=0)
    layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    return widget, layout


class Workbench(QWidget):
    def __init__(self, sender, receiver, preview):
        super().__init__()
        self.lanes = QGridLayout()
        self.lanes.setContentsMargins(0, 0, 0, 0)
        self.lanes.setSpacing(14)
        self.sender, self.receiver = sender, receiver
        self.preview = preview
        self.compact = None
        _, layout = column(self)
        layout.addLayout(self.lanes)
        layout.addWidget(preview)
        layout.addStretch()
        self.reflow(False)

    def reflow(self, compact):
        if compact == self.compact:
            return
        self.compact = compact
        self.lanes.removeWidget(self.sender)
        self.lanes.removeWidget(self.receiver)
        self.lanes.addWidget(self.sender, 0, 0)
        self.lanes.addWidget(self.receiver, 1 if compact else 0, 0 if compact else 1)
        self.lanes.setColumnStretch(0, 1)
        self.lanes.setColumnStretch(1, 0 if compact else 1)
        for lane in (self.sender, self.receiver):
            lane.ensurePolished()
            lane.setMinimumHeight(lane.sizeHint().height())
        lane_height = (self.sender.minimumHeight() + self.receiver.minimumHeight() + 14 if compact
                       else max(self.sender.minimumHeight(), self.receiver.minimumHeight()))
        self.setMinimumHeight(lane_height + self.preview.sizeHint().height() + 14)

    def resizeEvent(self, event):
        self.reflow(self.width() < 700)
        super().resizeEvent(event)


class TranslationPreview(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName('panel')
        _, layout = column(self, 16, 8)
        header = QHBoxLayout()
        self.direction = text('最新译文', 'section')
        self.elapsed = text('尚未开始', 'muted')
        header.addWidget(self.direction)
        header.addStretch()
        header.addWidget(self.elapsed)
        layout.addLayout(header)
        self.translated = text('等待语音', 'translation')
        self.translated.setMinimumHeight(28)
        layout.addWidget(self.translated)
        self.original = text('开始翻译后，这里会显示最新一句译文。', 'muted')
        layout.addWidget(self.original)
        self.target = ''

    def display(self, direction, original, translated, elapsed):
        self.direction.setText('队友 → 你' if direction == 'in' else '你 → 队友')
        self.elapsed.setText(f'识别与翻译 {elapsed:.1f} 秒')
        self.original.setText(self.original.fontMetrics().elidedText(
            ' '.join(original.split()), Qt.TextElideMode.ElideRight, max(80, self.width() - 40)))
        self.target = translated
        self.render_text()

    def render_text(self):
        if self.target:
            pages = subtitle_pages(self.target, self.translated.fontMetrics().horizontalAdvance,
                                   max(80, self.width() - 40), lines=2, max_pages=1)
            self.translated.setText(pages[0] if pages else '')

    def resizeEvent(self, event):
        self.render_text()
        super().resizeEvent(event)


def assemble_window(w):
    """Recompose existing controls; their saved settings and signal bindings survive."""
    old_root = w.takeCentralWidget()
    guide = w.tabs.widget(5)
    root, root_layout = column()
    root.setObjectName('appRoot')
    shell = QHBoxLayout()
    shell.setContentsMargins(0, 0, 0, 0)
    shell.setSpacing(0)
    root_layout.addLayout(shell)

    sidebar, side = column(margins=22, gap=8)
    sidebar.setObjectName('sidebar')
    w.sidebar = sidebar
    sidebar.setFixedWidth(186)
    icon = brand_icon()
    w.setWindowIcon(icon)
    brand = QLabel()
    brand.setPixmap(icon.pixmap(QSize(38, 38)))
    side.addWidget(brand)
    side.addWidget(text('Speak Sound', 'brand'))
    side.addWidget(text('游戏语音翻译', 'muted'))
    side.addSpacing(28)
    w.nav_group = QButtonGroup(w)
    w.nav_buttons = []
    names = ['语音工作台', '音频连接', '字幕与播放', '变声器', '速度与延迟', '翻译记录', '连接指引']
    descriptions = ['中文译音发送，队友语音接收。', '连接虚拟麦克风，核对游戏里的输入设备。',
                    '透明字幕和耳机里的译音，各自按需开启。', '调整译音或原声的音高与音效。',
                    '分别调整你和队友的分句时间。', '查看本次运行的原文、译文和处理耗时。',
                    '设备选择、离线模型与常见问题。']
    for index, name in enumerate(names):
        button = NavButton(name)
        button.setObjectName('navButton')
        button.setCheckable(True)
        button.setAccessibleName(name)
        w.nav_group.addButton(button, index)
        w.nav_buttons.append(button)
        side.addWidget(button)
    side.addStretch()
    side.addWidget(text('中 / 日 / 英', 'muted'))
    side.addWidget(text(f'本地运行 · v{__version__}', 'meta'))
    shell.addWidget(sidebar)

    canvas, body = column(margins=24, gap=14)
    canvas.setObjectName('workspace')
    shell.addWidget(canvas, 1)
    w.title_bar = TitleBar(w)
    body.addWidget(w.title_bar)
    header = QHBoxLayout()
    heading, headings = column(gap=5)
    w.page_title = text(names[0], 'title')
    w.page_description = text(descriptions[0], 'muted')
    headings.addWidget(w.page_title)
    headings.addWidget(w.page_description)
    header.addWidget(heading, 1)
    w.run_badge = text('未开始', 'status')
    header.addWidget(w.run_badge)
    w.start_button.setObjectName('primaryButton')
    w.start_button.setMinimumWidth(172)
    w.start_button.setFixedHeight(40)
    w.stop_button.setFixedHeight(40)
    w.stop_button.setMinimumWidth(60)
    header.addWidget(w.start_button)
    header.addWidget(w.stop_button)
    body.addLayout(header)
    body.addWidget(field('功能模式', w.operating_mode))

    # 1180 = 186 sidebar + 2*24 gutters + 946 canvas.
    # Two equal audio lanes use (946 - 14) / 2, with the same edges as the rows below.
    sending, send = panel('我的声音')
    w.sending_path = text('', 'muted')
    send.addWidget(w.sending_path)
    send.addWidget(field('中文翻译成', w.target_language))
    send.addWidget(field('实体麦克风', w.mic))
    send.addWidget(field('译音发送到', w.output))
    w.send_virtual.setText('发送至虚拟麦克风')
    send.addWidget(w.send_virtual)
    ptt_row = QHBoxLayout()
    ptt_row.addWidget(w.ptt)
    ptt_row.addStretch()
    w.ptt_key = QPushButton('修改按键 · ' + chord_text(w.settings.ptt_keys))
    w.ptt_key.setAccessibleName('修改按住说话按键')
    w.ptt_key.clicked.connect(w.choose_ptt_key)
    ptt_row.addWidget(w.ptt_key)
    send.addLayout(ptt_row)
    send.addStretch()
    receiving, receive = panel('队友语音')
    w.receiving_path = text('', 'muted')
    receive.addWidget(w.receiving_path)
    receive.addWidget(field('队友说的语言', w.incoming_language))
    receive.addWidget(field('接收来源', w.receive_mode))
    w.receive_device_field = field('播放设备回环', w.receive)
    receive.addWidget(w.receive_device_field)
    process, process_layout = column(gap=7)
    process_layout.addWidget(text('游戏 / 聊天进程', 'label'))
    process_row = QHBoxLayout()
    process_row.addWidget(w.process, 1)
    w.process_refresh.setText('刷新')
    process_row.addWidget(w.process_refresh)
    process_layout.addLayout(process_row)
    w.process_field = process
    receive.addWidget(process)
    w.receive_only.setText('只接收队友（关闭我的麦克风）')
    receive.addWidget(w.receive_only)
    receive.addStretch()

    volume, volumes = panel('实时音量')
    volume.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    gain_columns = QHBoxLayout()
    gain_columns.setSpacing(24)
    for slider, label, value in ((w.incoming_volume, '队友中文', w.volume_labels[0]),
                                 (w.outgoing_volume, '我方试听', w.volume_labels[1]),
                                 (w.send_volume, '虚拟麦克风', None)):
        gain, gain_layout = column(gap=8)
        row = QHBoxLayout()
        caption = text(label, 'label')
        row.addWidget(caption)
        row.addStretch()
        if value is None:
            value = text(f'{w.settings.send_volume}%', 'label')
            w.send_volume_value = value
            slider.valueChanged.connect(lambda number, label=value: label.setText(f'{number}%'))
        value.setMinimumWidth(42)
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(value)
        gain_layout.addLayout(row)
        slider.setMinimumHeight(18)
        gain_layout.addWidget(slider)
        gain_columns.addWidget(gain, 1)
    volumes.addLayout(gain_columns)
    mute_row = QHBoxLayout()
    w.mute.setText('静音本地译音')
    w.send_mute.setText('静音虚拟麦克风发送')
    mute_row.addWidget(w.mute)
    mute_row.addSpacing(20)
    mute_row.addWidget(w.send_mute)
    mute_row.addStretch()
    volumes.addLayout(mute_row)
    w.translation_preview = TranslationPreview()
    w.home = Workbench(sending, receiving, w.translation_preview)
    w.home_config = [sending, receiving]

    connection_page, connection = page()
    routing, routing_layout = panel('虚拟麦克风', '游戏 / Discord 输入选择 Speak Sound Virtual Cable，输出保持你的耳机。')
    routing_layout.addWidget(w.route_status)
    actions = QHBoxLayout()
    w.virtual_button.setText('连接虚拟麦克风')
    actions.addWidget(w.virtual_button)
    w.refresh.setText('刷新音频设备')
    actions.addWidget(w.refresh)
    actions.addStretch()
    routing_layout.addLayout(actions)
    install = QPushButton('准备开源驱动安装包')
    install.clicked.connect(w.prepare_driver)
    routing_layout.addWidget(install, alignment=Qt.AlignmentFlag.AlignLeft)
    connection.addWidget(routing)
    filter_panel, filter_layout = panel('接收人声筛选', '游戏内语音与音效混音时，人声检测不能区分队友与角色对白。')
    filter_layout.addWidget(field('筛选强度', w.speech_filter))
    filter_layout.addWidget(text('使用独立聊天软件时，在工作台选择它的进程。若游戏提供独立语音输出，可选择该设备的回环。', 'muted'))
    connection.addWidget(filter_panel)
    w.routing_controls = connection_page

    playback_page, playback = page()
    w.playback_controls, local = panel('耳机里的译音')
    local.addWidget(field('本地播放设备', w.listen))
    local.addWidget(w.incoming_voice)
    local.addWidget(w.outgoing_monitor)
    local.addWidget(text('设备回环在译音播放时暂停接收以防回授；指定进程接收可继续运行。建议使用耳机。', 'muted'))
    playback.addWidget(w.playback_controls)
    w.subtitle_controls, subtitles = panel('屏幕底部字幕', '透明背景，最多两行；完整原文与译文保留在翻译记录中。')
    subtitles.addWidget(field('显示器', w.screen))
    subtitle_row = QHBoxLayout()
    subtitle_row.addWidget(field('字号', w.font_size))
    subtitle_row.addWidget(field('底部距离（像素）', w.margin))
    subtitles.addLayout(subtitle_row)
    subtitles.addWidget(w.subtitle_original)
    subtitles.addWidget(w.preview, alignment=Qt.AlignmentFlag.AlignLeft)
    playback.addWidget(w.subtitle_controls)

    voice_page, voice = page()
    voice.addWidget(text('仅双向翻译模式会跳过变声。切换模式后，已选音高和音效会保留。', 'muted'))
    w.voice_controls, effects = panel('声音效果')
    effects.addWidget(w.voice_enable)
    effects.addWidget(field('音效预设', w.voice_preset))
    effect_row = QHBoxLayout()
    effect_row.addWidget(field('音高', w.voice_pitch))
    effect_row.addWidget(field('附加音效', w.voice_effect))
    effects.addLayout(effect_row)
    effects.addWidget(w.monitor_live_voice)
    effects.addWidget(text('音高和音效可在运行中调整。本地 DSP 效果不提供人物音色克隆。原声监听请戴耳机。', 'muted'))
    voice.addWidget(w.voice_controls)

    timing_page, timing = page()
    w.timing_controls, tuning = panel('识别与分句', '更短的分段更早提交，也会减少上下文；模型计算和排队仍会产生延迟。')
    for left, right in ((('计算模式', w.speed), ('识别 CPU 线程数', w.asr_threads)),
                        (('我的停顿等待', w.silence), ('我的最长分段', w.segment)),
                        (('队友停顿等待', w.incoming_silence), ('队友最长分段', w.incoming_segment))):
        row = QHBoxLayout()
        row.addWidget(field(*left))
        row.addWidget(field(*right))
        tuning.addLayout(row)
    presets = QHBoxLayout()
    fast = QPushButton('应用低延迟预设')
    fast.clicked.connect(lambda: w.set_timing('fast', 200, 3))
    balanced = QPushButton('应用均衡预设')
    balanced.clicked.connect(lambda: w.set_timing('balanced', 400, 5))
    presets.addWidget(fast)
    presets.addWidget(balanced)
    presets.addStretch()
    tuning.addLayout(presets)
    tuning.addWidget(text('这些设置停止后生效。处理耗时只统计识别与翻译，不代表完整语音延迟。', 'muted'))
    timing.addWidget(w.timing_controls)

    w.history.setPlaceholderText('还没有翻译记录。\n开始翻译后，原文、译文和处理耗时会出现在这里。')
    w.history.setObjectName('history')
    w.tabs = QTabWidget()
    w.tabs.setObjectName('workspacePages')
    w.tabs.tabBar().hide()
    for widget in (scroll(w.home), scroll(connection_page), scroll(playback_page), scroll(voice_page),
                   scroll(timing_page), w.history, guide):
        w.tabs.addTab(widget, '')
    body.addWidget(w.tabs, 1)
    body.addWidget(volume)
    w.live_volume_panel = volume
    w.status.setObjectName('statusText')
    w.status.setMaximumHeight(52)
    body.addWidget(w.status)
    w.nav_group.idClicked.connect(w.tabs.setCurrentIndex)

    def selected(index):
        w.nav_buttons[index].setChecked(True)
        w.page_title.setText(names[index])
        w.page_description.setText(descriptions[index])
    w.tabs.currentChanged.connect(selected)
    selected(0)
    w.run_locked_widgets = [*w.home_config, w.routing_controls, w.playback_controls,
                            w.subtitle_controls, w.timing_controls]
    w.setCentralWidget(root)
    w.setMinimumSize(820, 620)
    from PySide6.QtWidgets import QApplication
    available = QApplication.primaryScreen().availableGeometry()
    w.resize(min(1180, max(820, available.width() - 60)),
             min(860, max(620, available.height() - 60)))
    w.output.setPlaceholderText('请先在“音频连接”连接虚拟麦克风')
    w.receive.setPlaceholderText('请选择队友声音的播放设备回环')
    w.listen.setPlaceholderText('请选择你的耳机或扬声器')
    for combo in root.findChildren(QComboBox):
        combo.setMinimumWidth(0)
        combo.setMinimumContentsLength(8)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMaxVisibleItems(12)
        combo.setToolTip(combo.currentText())
        combo.currentTextChanged.connect(combo.setToolTip)
    for control in (w.target_language, w.incoming_language, w.operating_mode, w.send_virtual,
                    w.receive_only, w.incoming_voice, w.mute):
        signal = control.currentIndexChanged if isinstance(control, QComboBox) else control.toggled
        signal.connect(w.refresh_summary)
    focus_order = [w.start_button, w.stop_button, w.operating_mode, w.target_language, w.mic,
        w.output, w.send_virtual, w.ptt, w.ptt_key, w.incoming_language, w.receive_mode, w.receive,
        w.process, w.process_refresh, w.receive_only, w.incoming_volume, w.outgoing_volume,
        w.send_volume, w.mute, w.send_mute, *w.nav_buttons, w.virtual_button, w.refresh,
        w.speech_filter, w.listen, w.incoming_voice, w.outgoing_monitor, w.screen,
        w.font_size, w.margin, w.subtitle_original, w.preview, w.voice_enable,
        w.voice_preset, w.voice_pitch, w.voice_effect, w.monitor_live_voice,
        w.speed, w.asr_threads, w.silence, w.segment, w.incoming_silence, w.incoming_segment]
    for first, following in zip(focus_order, focus_order[1:]):
        QWidget.setTabOrder(first, following)
    old_root.deleteLater()


def stylesheet():
    assets = Path(__file__).parent / 'assets'
    return (assets / 'theme.qss').read_text(encoding='utf-8').replace('@assets@', assets.as_posix())
