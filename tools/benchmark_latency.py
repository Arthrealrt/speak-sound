import json
import os
from pathlib import Path
import sys
import time
import numpy as np
from faster_whisper import WhisperModel
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from speak_sound.audio import to_mono16
from speak_sound.config import Settings
from speak_sound.models import LocalModels

settings = Settings()
model = LocalModels(settings, print)
fixtures = []
for lang,text in [('zh','敌人在右边，我们一起去吧。'),('zh','敌人在左边，快撤退。'),
                  ('ja','敵が右にいます。一緒に行こう。'),('ja','敵が左にいます。気をつけて。')]:
    samples,rate = model.synthesize(text,lang)
    pcm = to_mono16((np.clip(samples,-1,1)*32767).astype(np.int16).tobytes(),rate,1)
    fixtures.append((lang,text,pcm))
rows=[]
for repetition in range(2):
    for mode in ('balanced','fast'):
        settings.speed_mode=mode
        settings.asr_threads=min(8,max(1,(os.cpu_count() or 4)//2)) if mode=='fast' else 4
        model.asr=WhisperModel(str(ROOT/'models/whisper'),device='cpu',compute_type='int8',
                               cpu_threads=settings.asr_threads,local_files_only=True)
        for lang,text,pcm in fixtures:
            begin=time.perf_counter()
            source=model.recognize(pcm,lang)
            asr=time.perf_counter()-begin
            begin=time.perf_counter()
            target=model.translate(source,lang,'ja' if lang=='zh' else 'zh')
            mt=time.perf_counter()-begin
            begin=time.perf_counter()
            model.synthesize(target,'ja' if lang=='zh' else 'zh')
            tts=time.perf_counter()-begin
            row=dict(repeat=repetition,mode=mode,language=lang,input=text,recognized=source,
                     translated=target,asr=round(asr,3),mt=round(mt,3),tts=round(tts,3),
                     text_total=round(asr+mt,3),voice_total=round(asr+mt+tts,3))
            rows.append(row)
            print(json.dumps(row,ensure_ascii=False),flush=True)
(ROOT/'work').mkdir(exist_ok=True)
(ROOT/'work/latency-benchmark.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
