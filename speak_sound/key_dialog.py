"""Explicit shortcut capture, with no audio and no global input hook."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout
from .hotkey import NAMES, MODIFIERS, SIDE_MODIFIERS, normalize_chord, chord_text


class KeyDialog(QDialog):
    def __init__(self, chord, parent=None):
        super().__init__(parent)
        self.setWindowTitle('设置按住说话按键')
        self.setObjectName('keyDialog')
        self.setMinimumWidth(390)
        self.chord = normalize_chord(chord)
        self.modifier_candidate = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(QLabel('按下要使用的按键或组合键'))
        self.preview = QLabel(chord_text(self.chord))
        self.preview.setProperty('role', 'title')
        layout.addWidget(self.preview)
        hint = QLabel('支持键盘、Ctrl / Alt / Shift 组合及鼠标中键、侧键。\nCtrl+Enter 保存，Esc 取消；修改前请停止翻译。')
        hint.setProperty('role', 'muted')
        layout.addWidget(hint)
        row = QHBoxLayout()
        reset = QPushButton('恢复 F8')
        reset.clicked.connect(lambda: self.choose((0x77,)))
        cancel = QPushButton('取消')
        cancel.clicked.connect(self.reject)
        save = QPushButton('保存按键')
        save.clicked.connect(self.accept)
        for button in (reset, cancel, save):
            # Enter/Space must be bindable rather than triggering dialog buttons.
            button.setAutoDefault(False)
            button.setDefault(False)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            row.addWidget(button)
        layout.addLayout(row)

    def focusNextPrevChild(self, next):
        return False  # Tab is a PTT candidate while this capture dialog is open.

    def choose(self, chord):
        self.modifier_candidate = None
        self.chord = normalize_chord(chord)
        self.preview.setText(chord_text(self.chord))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        if event.isAutoRepeat():
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.modifier_candidate = None
            self.accept()
            return
        if event.modifiers() & Qt.KeyboardModifier.MetaModifier:
            self.preview.setText('请选择不含 Windows 键的组合')
            return
        vk = int(event.nativeVirtualKey())
        vk = SIDE_MODIFIERS.get(vk, vk)
        # Synthetic Qt key events used by tests have no native Windows code.
        if not vk:
            key = event.key()
            special = {Qt.Key.Key_Control: 0x11, Qt.Key.Key_Alt: 0x12, Qt.Key.Key_Shift: 0x10,
                       Qt.Key.Key_Space: 0x20, Qt.Key.Key_Tab: 0x09, Qt.Key.Key_Return: 0x0D}
            vk = special.get(key, 0x70 + key - Qt.Key.Key_F1 if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24
                             else key if 0x30 <= key <= 0x5A else 0)
        if vk not in NAMES:
            self.preview.setText('这个按键暂不支持，请换一个')
            return
        modifiers = event.modifiers()
        keys = {code for flag, code in ((Qt.KeyboardModifier.ControlModifier, 0x11),
                (Qt.KeyboardModifier.AltModifier, 0x12), (Qt.KeyboardModifier.ShiftModifier, 0x10))
                if modifiers & flag}
        if vk in MODIFIERS:
            self.modifier_candidate = tuple(keys | {vk})
            self.preview.setText(chord_text(self.modifier_candidate))
        else:
            self.modifier_candidate = None
            self.choose(tuple(keys | {vk}))
        event.accept()

    def keyReleaseEvent(self, event):
        if self.modifier_candidate is not None and not event.isAutoRepeat():
            self.choose(self.modifier_candidate)
            self.modifier_candidate = None
        event.accept()

    def mousePressEvent(self, event):
        code = {Qt.MouseButton.MiddleButton: 0x04, Qt.MouseButton.BackButton: 0x05,
                Qt.MouseButton.ForwardButton: 0x06}.get(event.button())
        if code:
            self.modifier_candidate = None
            modifiers = event.modifiers()
            keys = [key for flag, key in ((Qt.KeyboardModifier.ControlModifier, 0x11),
                    (Qt.KeyboardModifier.AltModifier, 0x12), (Qt.KeyboardModifier.ShiftModifier, 0x10))
                    if modifiers & flag]
            self.choose(keys + [code])
            event.accept()
        else:
            super().mousePressEvent(event)
