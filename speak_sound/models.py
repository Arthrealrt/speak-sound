import os
import threading
from collections import OrderedDict

# Only the explicit setup tool may download models. Runtime is offline.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

import numpy as np

from .config import ROOT
from .speech_filter import SpeechFilter, plausible_transcript
from .streaming import PriorityLock, PreviewBusy
from .glossary import GameGlossary
from .chinese_asr import ChineseRecognizer, available as chinese_asr_available


class LocalModels:
    def __init__(self, settings, report, cancelled=lambda: False):
        from faster_whisper import WhisperModel
        from transformers import AutoTokenizer
        import ctranslate2
        self.settings = settings
        self.asr_lock = PriorityLock()
        self.zh_asr_lock = PriorityLock()
        self.zh_asr = None
        self.mt_lock = PriorityLock()
        self.tts_lock = threading.Lock()
        self.glossary = GameGlossary() if settings.game_glossary else None
        self.translation_cache = OrderedDict()
        self.speech_cache = OrderedDict()
        self.speech_cache_bytes = 0
        self.speech_filter = SpeechFilter(settings.speech_filter)
        model_root = ROOT / "models"
        if not (model_root / "whisper" / "model.bin").exists():
            raise FileNotFoundError("缺少识别模型，请先运行 setup.ps1 下载模型")
        report("正在载入本地语音识别模型…")
        self.asr = WhisperModel(str(model_root / "whisper"), device="cpu", compute_type="int8",
                                cpu_threads=settings.asr_threads, local_files_only=True)
        if settings.chinese_asr != 'whisper':
            folder = model_root / 'chinese-asr'
            if chinese_asr_available(folder):
                report('正在载入中文低延迟 Zipformer 识别模型…')
                self.zh_asr = ChineseRecognizer(folder, settings.asr_threads)
            elif settings.chinese_asr == 'zipformer':
                raise FileNotFoundError('缺少中文识别模型，请运行 tools/download_models.py --chinese-asr-only，或选择 Whisper')
        if cancelled():
            return
        report("正在载入本地中日英翻译模型…")
        self.tokenizer = AutoTokenizer.from_pretrained(model_root / "m2m100-tokenizer", local_files_only=True)
        self.mt = ctranslate2.Translator(str(model_root / "m2m100"), device="cpu",
                                        compute_type="int8", inter_threads=1, intra_threads=4)
        if cancelled():
            return
        import pyopenjtalk
        self.jtalk = pyopenjtalk
        self.zh_tts = None
        self.en_tts = None
        if settings.speak_incoming:
            import sherpa_onnx
            report("正在载入本地中英语音合成模型…")
            folder = model_root / "chinese-tts"
            if not (folder / "model.onnx").exists():
                raise FileNotFoundError("缺少中文播报模型，请重新运行 setup.ps1，或关闭队友中文播报")
            config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=str(folder / "model.onnx"), tokens=str(folder / "tokens.txt"),
                        lexicon=str(folder / "lexicon.txt")),
                    provider="cpu", num_threads=2),
                rule_fsts=",".join(str(folder / name) for name in ("date.fst", "number.fst", "phone.fst")),
                max_num_sentences=1)
            if not config.validate():
                raise ValueError("中文语音模型配置无效，请重新运行 setup.ps1")
            self.zh_tts = sherpa_onnx.OfflineTts(config)
        if not settings.receive_only and settings.target_language == "en":
            import sherpa_onnx
            report("正在载入本地英语语音合成模型…")
            folder = model_root / "english-tts"
            if not (folder / "model.onnx").exists():
                raise FileNotFoundError("缺少英语合成模型，请运行 .venv\\Scripts\\python.exe tools\\download_models.py --english-only")
            config = sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=str(folder / "model.onnx"),
                    tokens=str(folder / "tokens.txt"), lexicon=str(folder / "lexicon.txt")),
                provider="cpu", num_threads=2), max_num_sentences=1)
            if not config.validate():
                raise ValueError("英语语音模型配置无效，请重新下载英语模型")
            self.en_tts = sherpa_onnx.OfflineTts(config)

    def recognize(self, pcm, language, preview=False):
        if language == 'zh' and self.zh_asr is not None:
            with self.zh_asr_lock.hold(preview):
                samples = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
                if len(samples) < 2560 or np.max(np.abs(samples)) < .001:
                    return ''
                text = self.zh_asr.recognize(samples)
                text = text if len(text) <= max(48, len(samples) / 16000 * 28) else ''
                if self.settings.chinese_asr == 'zipformer':
                    return text
                if self.glossary and self.glossary.translate(text, 'zh', 'en'):
                    return text
                if preview:
                    raise PreviewBusy()  # Do not spend a Whisper pass on an uncertain Chinese prefix.
                # The faster model is not consistently more accurate. Auto mode
                # only takes known complete callouts; other text uses Whisper.
        with self.asr_lock.hold(preview):
            samples = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
            if language != "zh":
                samples = self.speech_filter.apply(samples)
            if len(samples) < 2560:
                return ""
            seconds = len(samples) / 16000
            if language == "zh":
                # Give short synthesized / clipped-onset Chinese phrases a quiet lead-in.
                samples = np.pad(samples, (8000, 0))
            segments, _ = self.asr.transcribe(
                samples, language=language, beam_size=((3 if language == "zh" else 2) if self.settings.speed_mode == "fast" else (5 if language == "zh" else 3)),
                condition_on_previous_text=False,
                temperature=0, max_new_tokens=min(160, max(32, int(seconds * 16 + 16))),
                vad_filter=False, no_speech_threshold=.6, log_prob_threshold=-1.,
                initial_prompt="队友、敌人、左边、右边、前方、后方、集合、撤退、掩护、补给。"
                               if language == "zh" else None)
            return plausible_transcript(segments, seconds,
                strict=language != "zh" and self.settings.speech_filter == "strict")

    def translate(self, text, source, target, preview=False):
        if not text.strip():
            return ""
        if self.glossary:
            callout = self.glossary.translate(text, source, target)
            if callout:
                return callout
        with self.mt_lock.hold(preview):
            key = (text, source, target)
            if key in self.translation_cache:
                self.translation_cache.move_to_end(key)
                return self.translation_cache[key]
            self.tokenizer.src_lang = source
            tokens = self.tokenizer.convert_ids_to_tokens(self.tokenizer.encode(text, truncation=True, max_length=256))
            target_token = self.tokenizer.convert_ids_to_tokens(self.tokenizer.get_lang_id(target))
            result = self.mt.translate_batch([tokens], target_prefix=[[target_token]],
                                            max_decoding_length=160,
                                            beam_size=2 if self.settings.speed_mode == "fast" else 4)
            ids = self.tokenizer.convert_tokens_to_ids(result[0].hypotheses[0][1:])
            translated = self.tokenizer.decode(ids, skip_special_tokens=True).strip()
            if translated:
                self.translation_cache[key] = translated
                while len(self.translation_cache) > 128:
                    self.translation_cache.popitem(last=False)
            return translated

    def synthesize(self, text, language="ja"):
        with self.tts_lock:
            key = (text, language)
            if key in self.speech_cache:
                self.speech_cache.move_to_end(key)
                return self.speech_cache[key]
            samples, rate = self._synthesize(text, language)
            # Cached base audio is immutable; effects operate on their own copy.
            samples.setflags(write=False)
            self.speech_cache[key] = (samples, rate)
            self.speech_cache_bytes += samples.nbytes
            while len(self.speech_cache) > 24 or self.speech_cache_bytes > 32 * 1024 * 1024:
                _, (old, _) = self.speech_cache.popitem(last=False)
                self.speech_cache_bytes -= old.nbytes
            return samples, rate

    def _synthesize(self, text, language):
        if language in ("zh", "en"):
            engine = self.en_tts if language == "en" else self.zh_tts
            if engine is None:
                raise RuntimeError("未载入所选语言的语音模型，请重新运行 setup.ps1")
            audio = engine.generate(text, sid=0, speed=1.0)
            return np.asarray(audio.samples, dtype=np.float32), audio.sample_rate
        samples, rate = self.jtalk.tts(text)
        return (np.asarray(samples, dtype=np.float32) / 32768, int(rate))
