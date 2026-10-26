"""Verify synthetic Chinese/Japanese/English speech and non-speech rejection offline."""
import sys,json,time,threading
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from speak_sound.config import Settings
from speak_sound.models import LocalModels
from speak_sound.audio import to_mono16
import argparse
parser=argparse.ArgumentParser(description='Synthetic offline speech checks; no live recording or audio playback')
parser.add_argument('--fast',action='store_true')
args=parser.parse_args()
settings=Settings(target_language='en',incoming_language='en',speed_mode='fast' if args.fast else 'balanced',asr_threads=8 if args.fast else 4)
m=LocalModels(settings,lambda s:print(s,flush=True))
(ROOT/'work').mkdir(exist_ok=True)
rows=[]
for language,text in [('en','Enemy on the right. Stay with me.'),('ja','敵が右にいます。一緒に行こう。'),('zh','队友在右边，一起走吧。')]:
    samples,rate=m.synthesize(text,language)
    pcm=to_mono16((np.clip(samples,-1,1)*32767).astype(np.int16).tobytes(),rate,1)
    start=time.perf_counter()
    recognized=m.recognize(pcm,language)
    translated=m.translate(recognized,language,'en' if language=='zh' else 'zh')
    elapsed=time.perf_counter()-start
    audio,out_rate=m.synthesize(translated,'en' if language=='zh' else 'zh')
    row=dict(language=language,input=text,recognized=recognized,translated=translated,processing_seconds=round(elapsed,3),output_seconds=round(len(audio)/out_rate,2))
    rows.append(row)
    print(json.dumps(row,ensure_ascii=False),flush=True)
    assert recognized and translated and len(audio)>0
for name,samples in [('silence',np.zeros(48000,np.float32)),('tone',.2*np.sin(2*np.pi*440*np.arange(48000)/16000).astype(np.float32)),('noise',np.random.default_rng(123).normal(0,.12,48000).astype(np.float32))]:
    start=time.perf_counter()
    recognized=m.recognize((np.clip(samples,-1,1)*32767).astype(np.int16).tobytes(),'en')
    elapsed=time.perf_counter()-start
    print(name,repr(recognized),round(elapsed,3),flush=True)
    assert not recognized
    rows.append(dict(input=name,recognized=recognized,processing_seconds=round(elapsed,3)))
(ROOT/('work/v07-model-fast-check.json' if args.fast else 'work/v07-model-check.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
