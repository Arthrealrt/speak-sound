import unittest
from speak_sound.virtual_mic import own_ports, ATTACHED_PORT
from speak_sound.routing import is_open_output, require_physical_microphone


class VirtualMicrophoneTests(unittest.TestCase):
    def test_default_alias_cannot_silently_feed_back_after_usb_creation(self):
        for name in ('Windows DirectSound | 主声音捕获驱动程序', 'Primary Sound Capture Driver',
                     'Windows WASAPI | Microphone (Speak Sound Virtual Cable 01)'):
            with self.assertRaises(ValueError):
                require_physical_microphone(name)
        require_physical_microphone('Windows WASAPI | Microphone (Real USB Mic)')

    def test_detach_identifies_only_exact_local_cable(self):
        ports = '''Port 1: connected
            usbip://192.168.1.3:32401/1-1
        Port 2: connected
            usbip://127.0.0.1:32401/1-10
        Port 3: connected
            usbip://127.0.0.1:32401/1-1
        Port 4: connected
            usbip://127.0.0.1:3241/1-1
        '''
        self.assertEqual(own_ports(ports),[3])
        self.assertEqual(ATTACHED_PORT.search('successfully attached to port 3').group(1),'3')

    def test_render_is_accepted_and_capture_is_rejected(self):
        self.assertTrue(is_open_output('Windows WASAPI | Speakers (Speak Sound Virtual Cable 01)'))
        self.assertFalse(is_open_output('Windows WASAPI | Microphone (Speak Sound Virtual Cable 01)'))

