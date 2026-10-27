"""Serializable Windows PTT chords; never installs hooks or injects input."""
import ctypes

MODIFIERS = (0x11, 0x12, 0x10)  # Ctrl, Alt, Shift; generic VKs accept either side.
NAMES = {0x10: 'Shift', 0x11: 'Ctrl', 0x12: 'Alt', 0x20: 'Space',
         0x09: 'Tab', 0x0D: 'Enter', 0x08: 'Backspace', 0x14: 'Caps Lock',
         0x24: 'Home', 0x23: 'End', 0x21: 'Page Up', 0x22: 'Page Down',
         0x25: '←', 0x26: '↑', 0x27: '→', 0x28: '↓', 0x2D: 'Insert', 0x2E: 'Delete',
         0x04: '鼠标中键', 0x05: '鼠标侧键 1', 0x06: '鼠标侧键 2',
         0xBA: ';', 0xBB: '=', 0xBC: ',', 0xBD: '-', 0xBE: '.', 0xBF: '/',
         0xC0: '`', 0xDB: '[', 0xDC: '\\', 0xDD: ']', 0xDE: "'"}
NAMES.update({key: chr(key) for key in range(0x30, 0x5B) if key <= 0x39 or key >= 0x41})
NAMES.update({0x70 + n: f'F{n + 1}' for n in range(24)})
NAMES.update({0x60 + n: f'Num {n}' for n in range(10)})
NAMES.update({0x6A: 'Num *', 0x6B: 'Num +', 0x6D: 'Num -', 0x6E: 'Num .', 0x6F: 'Num /'})
SIDE_MODIFIERS = {0xA0: 0x10, 0xA1: 0x10, 0xA2: 0x11, 0xA3: 0x11, 0xA4: 0x12, 0xA5: 0x12}


def normalize_chord(value):
    if not isinstance(value, (tuple, list)) or not value or len(value) > 4:
        return (0x77,)
    if any(type(key) is not int or key not in NAMES for key in value):
        return (0x77,)
    keys = set(value)
    if len(keys - set(MODIFIERS)) > 1:
        return (0x77,)
    return tuple(key for key in MODIFIERS if key in keys) + tuple(sorted(keys - set(MODIFIERS)))


def chord_text(value):
    return ' + '.join(NAMES[key] for key in normalize_chord(value))


def windows_key_down(key):
    return bool(ctypes.windll.user32.GetAsyncKeyState(key) & 0x8000)


class PushToTalkGate:
    """Require a full release on start/rebind so held keys cannot open the mic."""
    def __init__(self):
        self.armed = False

    def reset(self):
        self.armed = False

    def pressed(self, chord, key_down=windows_key_down):
        states = [key_down(key) for key in normalize_chord(chord)]
        if not any(states):
            self.armed = True
        return self.armed and all(states)
