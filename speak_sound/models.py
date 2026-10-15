import io
import os
import threading
import wave

# Only the explicit setup tool may download models. Runtime is offline.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

import numpy as np
import requests

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
        self.asr = WhisperModel(str(model_root / "whisper"), device=settings.asr_device,
                                compute_type="float16" if settings.asr_device == "cuda" else "int8",
                                cpu_threads=4, local_files_only=True)
        if cancelled():
            return
        report("正在载入本地中日翻译模型…")
        self.tokenizer = AutoTokenizer.from_pretrained(model_root / "tokenizer", local_files_only=True)
        self.mt = ctranslate2.Translator(str(model_root / "translation"), device="cpu",
                                        compute_type="int8", inter_threads=1, intra_threads=4)
        if cancelled():
            return
        if settings.tts == "openjtalk":
            import pyopenjtalk
            self.jtalk = pyopenjtalk
        else:
            self.session = requests.Session()
            self.session.trust_env = False
            self.session.get("http://127.0.0.1:50021/version", timeout=3).raise_for_status()

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
            result = self.mt.translate_batch([tokens], target_prefix=[[target]],
                                            max_decoding_length=160, beam_size=4)
            ids = self.tokenizer.convert_tokens_to_ids(result[0].hypotheses[0][1:])
            return self.tokenizer.decode(ids, skip_special_tokens=True).strip()

    def synthesize(self, text):
        if self.settings.tts == "openjtalk":
            samples, rate = self.jtalk.tts(text)
            return (np.asarray(samples, dtype=np.float32) / 32768, int(rate))
        speaker = self.settings.voicevox_speaker
        query = self.session.post("http://127.0.0.1:50021/audio_query",
                                  params={"text": text, "speaker": speaker}, timeout=10)
        query.raise_for_status()
        response = self.session.post("http://127.0.0.1:50021/synthesis",
                                     params={"speaker": speaker}, json=query.json(), timeout=30)
        response.raise_for_status()
        with wave.open(io.BytesIO(response.content)) as wav:
            if wav.getsampwidth() != 2:
                raise ValueError("VOICEVOX 必须返回 16 位 PCM WAV")
            samples = np.frombuffer(wav.readframes(wav.getnframes()), np.int16).astype(np.float32)
            return samples.reshape(-1, wav.getnchannels()).mean(axis=1) / 32768, wav.getframerate()
