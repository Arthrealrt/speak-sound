from collections import OrderedDict
import threading
import unittest
from unittest.mock import Mock
from types import SimpleNamespace
import numpy as np
from speak_sound.models import LocalModels
from speak_sound.config import Settings
from speak_sound.glossary import GameGlossary
from speak_sound.streaming import PriorityLock


class ModelCacheTests(unittest.TestCase):
    def test_synthesis_reuses_base_audio_without_reapplying_effects_to_the_cache(self):
        m = LocalModels.__new__(LocalModels)
        m.tts_lock = threading.Lock()
        m.speech_cache = OrderedDict()
        m.speech_cache_bytes = 0
        m._synthesize = Mock(return_value=(np.ones(320, np.float32), 16000))
        a, _ = m.synthesize('我倒了', 'zh')
        b, _ = m.synthesize('我倒了', 'zh')
        self.assertIs(a, b)
        self.assertFalse(a.flags.writeable)
        m._synthesize.assert_called_once()
        m.synthesize('我倒了', 'en')
        self.assertEqual(m._synthesize.call_count, 2)

    def test_chinese_engine_never_receives_other_languages_or_silent_audio(self):
        m = LocalModels.__new__(LocalModels)
        m.zh_asr = Mock()
        m.settings = Settings(chinese_asr='zipformer')
        m.zh_asr.recognize.return_value = '我倒了'
        m.zh_asr_lock = PriorityLock()
        self.assertEqual(m.recognize(bytes(6400), 'zh'), '')
        m.zh_asr.recognize.assert_not_called()
        pcm = np.full(3200, 1600, np.int16).tobytes()
        self.assertEqual(m.recognize(pcm, 'zh'), '我倒了')
        samples = m.zh_asr.recognize.call_args.args[0]
        self.assertAlmostEqual(float(samples[0]), 1600 / 32768)

    def test_auto_only_uses_fast_recognizer_for_known_callouts_and_falls_back_for_unknown_text(self):
        m = LocalModels.__new__(LocalModels)
        m.settings = Settings(chinese_asr='auto')
        m.glossary = GameGlossary()
        m.zh_asr_lock, m.asr_lock = PriorityLock(), PriorityLock()
        m.zh_asr = Mock()
        m.asr = Mock()
        m.asr.transcribe.return_value = ([SimpleNamespace(text='敌人在右边', no_speech_prob=.01,
            avg_logprob=-.1, compression_ratio=1.)], None)
        pcm = np.full(6400, 1600, np.int16).tobytes()
        m.zh_asr.recognize.return_value = '没有敌人别开枪'
        self.assertEqual(m.recognize(pcm, 'zh'), '没有敌人别开枪')
        m.asr.transcribe.assert_not_called()
        m.zh_asr.recognize.return_value = '依院在右边'
        self.assertEqual(m.recognize(pcm, 'zh'), '敌人在右边')
        m.asr.transcribe.assert_called_once()
