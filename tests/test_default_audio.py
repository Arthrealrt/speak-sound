import unittest
from unittest.mock import Mock
from speak_sound.default_audio import DefaultAudioGuard


class DefaultAudioTests(unittest.TestCase):
    def test_only_auto_selected_own_cable_is_restored(self):
        for name, expected in [('Speakers (Speak Sound Virtual Cable 01)',True),
                               ('Other USB Headset',False),('RadioVoice Microphone',False)]:
            with self.subTest(name=name):
                guard=DefaultAudioGuard()
                guard.saved={(0,0):'old-device'}
                guard.audio=Mock()
                enumerator=guard.audio.GetDeviceEnumerator.return_value
                enumerator.GetDefaultAudioEndpoint.return_value.GetId.return_value='new-device'
                enumerator.GetDevice.return_value.GetState.return_value=1
                guard.audio.CreateDevice.return_value.FriendlyName=name
                guard.restore()
                self.assertEqual(guard.audio.SetDefaultDevice.called,expected)

    def test_unchanged_default_is_not_written(self):
        guard=DefaultAudioGuard()
        guard.saved={(1,2):'same-device'}
        guard.audio=Mock()
        guard.audio.GetDeviceEnumerator.return_value.GetDefaultAudioEndpoint.return_value.GetId.return_value='same-device'
        guard.restore()
        guard.audio.SetDefaultDevice.assert_not_called()
