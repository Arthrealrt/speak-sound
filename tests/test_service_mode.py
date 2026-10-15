import unittest
from unittest.mock import patch

try:
    from speak_sound.config import Settings
    from speak_sound.service import Service
    SERVICE_AVAILABLE = True
except ImportError:
    SERVICE_AVAILABLE = False


class FakeCapture:
    def __init__(self, p, info, destination, stop, enabled, settings, report):
        self.stop = stop
        self.ident = None

    def start(self):
        self.ident = 1
        self.stop.set()

    def join(self):
        pass


@unittest.skipUnless(SERVICE_AVAILABLE, "desktop dependencies not installed")
class ServiceModeTests(unittest.TestCase):
    def run_mode(self, settings):
        import speak_sound.service as module
        resolved = []

        def resolve(p, kind, key):
            resolved.append(kind)
            return {"index": 1}

        with patch.object(module, "LocalModels"), patch.object(module.pa, "PyAudio") as audio, \
             patch.object(module, "resolve", side_effect=resolve), \
             patch.object(module, "Capture", FakeCapture), patch.object(module, "play") as play:
            service = Service(settings)
            service.run()
            audio.return_value.terminate.assert_called_once()
            play.assert_not_called()
        return resolved

    def test_subtitle_mode_does_not_open_microphone_or_output(self):
        self.assertEqual(self.run_mode(Settings(receive_only=True, speak_incoming=False)), ["receive"])

    def test_duplex_mode_opens_both_sides_with_open_driver(self):
        self.assertEqual(self.run_mode(Settings(receive_only=False, send_to_virtual=True,
                                                speak_incoming=False, monitor_outgoing=False,
                                                output_device="RadioVoice Output")),
                         ["receive", "microphone", "output"])

    def test_local_monitor_does_not_require_virtual_microphone(self):
        self.assertEqual(self.run_mode(Settings(receive_only=False, send_to_virtual=False,
                                                speak_incoming=True, monitor_outgoing=True)),
                         ["receive", "microphone", "output"])
