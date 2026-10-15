import unittest

from speak_sound.routing import is_open_output, require_open_output


class OpenRoutingTests(unittest.TestCase):
    def test_accepts_documented_gpl_driver_endpoint(self):
        name = "Windows WASAPI | RadioVoice Output"
        self.assertTrue(is_open_output(name))
        require_open_output(name)

    def test_does_not_mistake_capture_endpoint_or_speakers_for_output(self):
        for name in ("Windows WASAPI | RadioVoice Microphone", "Speakers", "Virtual Speakers"):
            self.assertFalse(is_open_output(name))
            with self.assertRaises(ValueError):
                require_open_output(name)

    def test_closed_source_routing_is_not_enabled(self):
        for name in ("Windows WASAPI | CABLE Input", "Voicemeeter Input"):
            self.assertFalse(is_open_output(name))
            with self.assertRaises(ValueError):
                require_open_output(name)
