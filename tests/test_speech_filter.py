import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
from speak_sound.speech_filter import plausible_transcript, SpeechFilter
from speak_sound.models import LocalModels
from speak_sound.config import Settings


def segment(text='Enemy on the right.', **kwargs):
    return SimpleNamespace(**dict(text=text, no_speech_prob=kwargs.get('no_speech_prob', .1),
        avg_logprob=kwargs.get('avg_logprob', -.2), compression_ratio=kwargs.get('compression_ratio', 1.1)))


class SpeechFilterTests(unittest.TestCase):
    def test_short_repeated_game_callout_is_not_treated_as_a_long_hallucination(self):
        text = '撤退！撤退！撤退！撤退！'
        self.assertEqual(plausible_transcript([segment(text)], 2), text)

    def test_rejects_low_confidence_and_repeated_or_excessive_text(self):
        for item in (segment(no_speech_prob=.8), segment(avg_logprob=-1.4),
                     segment(compression_ratio=3), segment('Thank you. ' * 12), segment('x' * 100)):
            self.assertEqual(plausible_transcript([item], 1), '')
        self.assertEqual(plausible_transcript([segment()], 2), 'Enemy on the right.')
        self.assertEqual(plausible_transcript([segment(avg_logprob=-.9)], 2, strict=True), '')

    def model(self, mode='standard'):
        m = LocalModels.__new__(LocalModels)
        m.settings = Settings(speech_filter=mode)
        m.zh_asr = None
        from speak_sound.streaming import PriorityLock
        m.asr_lock = PriorityLock()
        m.speech_filter = Mock()
        m.asr = Mock()
        return m

    def test_rejected_audio_never_calls_asr(self):
        m = self.model()
        m.speech_filter.apply.return_value = np.empty(0, np.float32)
        self.assertEqual(m.recognize(bytes(64000), 'en'), '')
        m.asr.transcribe.assert_not_called()

    def test_fixed_temperature_and_token_budget_with_explicit_english(self):
        m = self.model()
        m.speech_filter.apply.side_effect = lambda samples: samples
        m.asr.transcribe.return_value = ([segment()], None)
        self.assertEqual(m.recognize(bytes(64000), 'en'), 'Enemy on the right.')
        kwargs = m.asr.transcribe.call_args.kwargs
        self.assertEqual(kwargs['language'], 'en')
        self.assertEqual(kwargs['temperature'], 0)
        self.assertEqual(kwargs['max_new_tokens'], 48)
        self.assertEqual(kwargs['beam_size'], 3)

    def test_disabling_neural_gate_preserves_input(self):
        samples = np.zeros(320, np.float32)
        self.assertIs(SpeechFilter('off').apply(samples), samples)
