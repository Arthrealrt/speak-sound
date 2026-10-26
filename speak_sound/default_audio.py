"""Restore previous defaults only when Windows automatically selects our new cable."""
from .routing import is_virtual_microphone


class DefaultAudioGuard:
    def __enter__(self):
        import comtypes
        from _ctypes import COMError
        from pycaw.utils import AudioUtilities
        self.comtypes, self.audio = comtypes, AudioUtilities
        comtypes.CoInitialize()
        self.saved = {}
        enumerator = self.audio.GetDeviceEnumerator()
        for flow in (0, 1):
            for role in (0, 1, 2):
                try:
                    self.saved[(flow, role)] = enumerator.GetDefaultAudioEndpoint(flow, role).GetId()
                except (OSError, COMError):
                    pass  # Headless machines may not yet have a default device.
        return self

    def restore(self):
        from pycaw.constants import ERole
        enumerator = self.audio.GetDeviceEnumerator()
        for (flow, role), previous_id in self.saved.items():
            current = enumerator.GetDefaultAudioEndpoint(flow, role)
            if current.GetId() == previous_id:
                continue
            name = self.audio.CreateDevice(current).FriendlyName or ""
            # Preserve concurrent user changes to any other physical/virtual device.
            if is_virtual_microphone(name) and "speak sound" in name.casefold():
                previous = enumerator.GetDevice(previous_id)
                if previous.GetState() & 1:
                    self.audio.SetDefaultDevice(previous_id, [ERole(role)])

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.restore()
        finally:
            self.comtypes.CoUninitialize()
