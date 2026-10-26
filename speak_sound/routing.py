"""Explicit allowlist for documented open-source virtual audio backends."""


def is_open_output(name):
    name = name.casefold()
    if any(word in name for word in ("microphone", "麦克风", "录音")):
        return False
    return "radiovoice output" in name or "speak sound virtual cable" in name


def is_virtual_microphone(name):
    return any(part in name.casefold() for part in ("radiovoice", "speak sound virtual"))


def is_default_input_alias(name):
    return any(part in name.casefold() for part in ("primary sound capture", "主声音捕获", "sound mapper", "声音映射器"))


def require_physical_microphone(name):
    if is_virtual_microphone(name) or is_default_input_alias(name):
        raise ValueError("请选择明确名称的实体麦克风，不要选择虚拟麦克风或默认设备映射，以防回授")


def require_open_output(name):
    if not is_open_output(name):
        raise ValueError("请选择 Speak Sound Virtual Cable 播放端或 RadioVoice Output；接入说明见 drivers/README.md")
