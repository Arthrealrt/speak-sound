import os
import threading

# Only the explicit setup tool may download models. Runtime is offline.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

import numpy as np

from .config import ROOT


class LocalModels:
    def __init__(self, settings, report, cancelled=lambda: False):
        from faster_whisper import WhisperModel
        from transformers import AutoTokenizer
        import ctranslate2
        self.settings = settings
        self.asr_lock = threading.Lock()
        self.mt_lock = threading.Lock()
        model_root = ROOT / "models"
        if not (model_root / "whisper" / "model.bin").exists():
            raise FileNotFoundError("缺少识别模型，请先运行 setup.ps1 下载模型")
        report("正在载入本地语音识别模型…")
        self.asr = WhisperModel(str(model_root / "whisper"), device="cpu", compute_type="int8",
                                cpu_threads=4, local_files_only=True)
        if cancelled():
            return
        report("正在载入本地中日翻译模型…")
        self.tokenizer = AutoTokenizer.from_pretrained(model_root / "m2m100-tokenizer", local_files_only=True)
        self.mt = ctranslate2.Translator(str(model_root / "m2m100"), device="cpu",
                                        compute_type="int8", inter_threads=1, intra_threads=4)
        if cancelled():
            return
        import pyopenjtalk
        self.jtalk = pyopenjtalk

    def recognize(self, pcm, language):
        with self.asr_lock:
            segments, _ = self.asr.transcribe(
                np.frombuffer(pcm, np.int16).astype(np.float32) / 32768,
                language=language, beam_size=1, condition_on_previous_text=False,
                vad_filter=False, no_speech_threshold=.6,
                initial_prompt="游戏语音交流。" if language == "zh" else "ゲームのボイスチャット。")
            return "".join(s.text for s in segments if s.no_speech_prob < .7).strip()

    def translate(self, text, source, target):
        if not text.strip():
            return ""
        with self.mt_lock:
            self.tokenizer.src_lang = source
            tokens = self.tokenizer.convert_ids_to_tokens(self.tokenizer.encode(text, truncation=True, max_length=256))
            target_token = self.tokenizer.convert_ids_to_tokens(self.tokenizer.get_lang_id(target))
            result = self.mt.translate_batch([tokens], target_prefix=[[target_token]],
                                            max_decoding_length=160, beam_size=4)
            ids = self.tokenizer.convert_tokens_to_ids(result[0].hypotheses[0][1:])
            return self.tokenizer.decode(ids, skip_special_tokens=True).strip()

    def synthesize(self, text):
        samples, rate = self.jtalk.tts(text)
        return (np.asarray(samples, dtype=np.float32) / 32768, int(rate))
