"""Offline synthetic benchmark; no microphone, virtual output or local playback.

Use --baseline to disable the new glossary, Chinese recognizer and caches.
Use the same --fixtures directory for before/after comparisons. Synthetic TTS
errors and the small fixture set must not be presented as game accuracy scores.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import queue
import sys
import threading
import time

import numpy as np
import webrtcvad
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from speak_sound.config import Settings
from speak_sound.models import LocalModels
from speak_sound.audio import to_mono16
from speak_sound.segmenter import make_segmenter
from speak_sound.streaming import SpeechQueue, ResultCache, PreviewBusy

PHRASES = [('zh', '敌人在右边。'), ('zh', '我倒了，救我。'), ('zh', '没有敌人，别开枪。'),
           ('ja', '敵が右にいる。'), ('ja', 'リロード中。'), ('ja', '敵はいない。撃たないで。'),
           ('en', 'Enemy on the right.'), ('en', "I'm down. Help me."), ('en', "No enemies. Don't shoot.")]


def replay(model, pcm, language, streaming):
    settings = Settings(streaming_enabled=streaming, silence_ms=160, max_speech_seconds=3)
    work = SpeechQueue(min_preview_ms=1800, zero_tail_only=language != 'zh' or model.zh_asr is None)
    segmenter = make_segmenter(settings, work)
    finished, stop = threading.Event(), threading.Event()
    result, errors = {}, []
    cache = ResultCache()
    target = 'ja' if language == 'zh' else 'zh'
    def run():
        try:
            while not stop.is_set():
                try:
                    packet = work.get(.1)
                except queue.Empty:
                    continue
                try:
                    cached = cache.get(packet.pcm)
                    if cached:
                        original, translated = cached
                    else:
                        kwargs = {} if packet.final else {'preview': True}
                        original = model.recognize(packet.pcm, language, **kwargs)
                        translated = model.translate(original, language, target, **kwargs) if original else ''
                        if original and translated:
                            cache.put(packet.pcm, (original, translated))
                    if packet.final:
                        result.update(recognized=original, translated=translated,
                            reused_preview=bool(cached), end_to_text_ms=round((time.monotonic()-packet.speech_end)*1000),
                            submit_to_text_ms=round((time.monotonic()-packet.created)*1000))
                        finished.set()
                        return
                except PreviewBusy:
                    pass
        except Exception as exc:
            errors.append(str(exc))
            finished.set()
    thread = threading.Thread(target=run)
    thread.start()
    vad = webrtcvad.Vad(2)
    data = pcm + bytes(16000)
    try:
        next_frame = time.monotonic()
        for offset in range(0, len(data) - 639, 640):
            frame = data[offset:offset+640]
            utterance = segmenter.push(frame, vad.is_speech(frame, 16000))
            if utterance:
                work.put_nowait(utterance)
            next_frame += .02
            time.sleep(max(0, next_frame - time.monotonic()))
        if not finished.wait(10):
            raise TimeoutError('Replay inference did not finish')
        if errors:
            raise RuntimeError(errors[0])
        return result
    finally:
        stop.set()
        thread.join(15)
        if thread.is_alive():
            raise RuntimeError('Inference did not stop')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--fixtures', type=Path, default=ROOT/'work/v11-audio')
    parser.add_argument('--output', type=Path, default=ROOT/'work/v11-final-models.json')
    parser.add_argument('--skip-replay', action='store_true')
    args = parser.parse_args()
    settings = Settings(target_language='en', incoming_language='en', asr_threads=args.threads,
        game_glossary=not args.baseline, chinese_asr='whisper' if args.baseline else 'auto')
    model = LocalModels(settings, lambda value: print(value, flush=True))
    args.fixtures.mkdir(exist_ok=True, parents=True)
    rows = []
    for index, (language, reference) in enumerate(PHRASES):
        path = args.fixtures/f'{index}.pcm'
        if not path.exists():
            samples, rate = model.synthesize(reference, language)
            path.write_bytes(to_mono16((np.clip(samples,-1,1)*32767).astype(np.int16).tobytes(),rate,1))
        pcm = path.read_bytes()
        entry = dict(id=index, language=language, input=reference, runs=[])
        for repeat in range(2):
            if args.baseline:
                model.translation_cache.clear()
                model.speech_cache.clear()
                model.speech_cache_bytes = 0
            a=time.perf_counter(); original=model.recognize(pcm,language); b=time.perf_counter()
            target='en' if language=='zh' else 'zh'
            translated=model.translate(original,language,target); c=time.perf_counter()
            samples,rate=model.synthesize(translated,target); d=time.perf_counter()
            entry['runs'].append(dict(recognized=original, translated=translated,
                asr_ms=round((b-a)*1000), mt_ms=round((c-b)*1000), tts_ms=round((d-c)*1000), processing_ms=round((d-a)*1000)))
        rows.append(entry)
        print(json.dumps(entry,ensure_ascii=False),flush=True)
    replays=[]
    if not args.skip_replay:
        for index in (2,4,7):
            language=PHRASES[index][0]
            pcm=(args.fixtures/f'{index}.pcm').read_bytes()
            for streaming in (False,True):
                row=dict(input=PHRASES[index][1], language=language, streaming=streaming,
                    **replay(model,pcm,language,streaming))
                replays.append(row)
                print(json.dumps(row,ensure_ascii=False),flush=True)
    report=dict(scope='Synthetic PCM, CPU int8. No microphone, game, simultaneous real speakers, network or playback. '
        'Replay tail latency excludes physical audio and Qt rendering. No general accuracy or esports guarantee.',
        baseline=args.baseline, threads=args.threads, models=rows, replays=replays)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
