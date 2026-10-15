"""Device selection for the documented GPL open-source loopback driver."""


def is_open_output(name):
    return "radiovoice output" in name.casefold()


def require_open_output(name):
    if not is_open_output(name):
        raise ValueError("请选择开源驱动的 RadioVoice Output；驱动要求与安装限制见 drivers/README.md")
