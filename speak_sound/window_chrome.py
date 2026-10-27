"""Translucent native window chrome and pointer feedback for Qt Widgets."""
import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import Qt, QVariantAnimation, QEasingCurve, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget, QPushButton, QHBoxLayout, QLabel


class NavButton(QPushButton):
    def __init__(self, name, parent=None):
        super().__init__(name, parent)
        self.hover = 0.0
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(150)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._frame)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(42)
        self.toggled.connect(lambda _: self.update())

    def _frame(self, value):
        self.hover = float(value)
        self.update()

    def animate(self, target):
        self.animation.stop()
        self.animation.setStartValue(self.hover)
        self.animation.setEndValue(float(target))
        self.animation.start()

    def enterEvent(self, event):
        self.animate(1)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.animate(0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 1.5, -0.5, -1.5)
        painter.setPen(Qt.PenStyle.NoPen)
        # Resting navigation stays transparent, including the selected row.
        painter.setBrush(QColor(255, 255, 255, round(25 * self.hover)))
        painter.drawRoundedRect(rect, 8, 8)
        if self.isChecked():
            painter.setBrush(QColor('#78d7b2'))
            painter.drawRoundedRect(QRectF(0, self.height() / 2 - 7, 3, 14), 1.5, 1.5)
        font = self.font()
        font.setWeight(QFont.Weight.DemiBold if self.isChecked() else QFont.Weight.Medium)
        painter.setFont(font)
        painter.setPen(QColor('#ffffff' if self.isChecked() or self.hover > .05 else '#dedede'))
        painter.drawText(self.rect().adjusted(12 + round(4 * self.hover), 0, -6, 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
        if self.hasFocus():
            painter.setPen(QPen(QColor('#ffffff'), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 7, 7)


class TitleBar(QWidget):
    """Keep drag, double-click, minimize, maximize and close with per-pixel alpha."""
    def __init__(self, window):
        super().__init__(window)
        self.owner = window
        self.setObjectName('titleBar')
        self.setFixedHeight(28)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        label = QLabel('Speak Sound')
        label.setProperty('role', 'meta')
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(label)
        row.addStretch()
        self.controls = []
        for name, glyph, action in (('最小化', '−', window.showMinimized),
                                    ('最大化 / 还原', '□', self.toggle_maximize),
                                    ('关闭', '×', window.close)):
            button = QPushButton(glyph)
            button.setObjectName('windowControl')
            button.setAccessibleName(name)
            button.setToolTip(name)
            button.setFixedSize(36, 28)
            button.clicked.connect(action)
            row.addWidget(button)
            self.controls.append(button)

    def toggle_maximize(self):
        self.owner.showNormal() if self.owner.isMaximized() else self.owner.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.owner.windowHandle():
            self.owner.windowHandle().startSystemMove()
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximize()
            event.accept()


def resize_hit(window, event_type, message):
    """Native edge hit testing retains system resize cursors and resize dragging."""
    if sys.platform != 'win32' or bytes(event_type) not in (b'windows_generic_MSG', b'windows_dispatcher_MSG'):
        return None
    msg = wintypes.MSG.from_address(int(message))
    if msg.message != 0x0084 or window.isMaximized():  # WM_NCHITTEST
        return None
    rect = wintypes.RECT()
    user32 = ctypes.windll.user32
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    if not user32.GetWindowRect(msg.hWnd, ctypes.byref(rect)):
        return None
    x = ctypes.c_short(msg.lParam & 0xFFFF).value
    y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
    border = max(6, round(6 * window.devicePixelRatioF()))
    left, right = x < rect.left + border, x >= rect.right - border
    top, bottom = y < rect.top + border, y >= rect.bottom - border
    if top:
        return 13 if left else 14 if right else 12
    if bottom:
        return 16 if left else 17 if right else 15
    return 10 if left else 11 if right else None
