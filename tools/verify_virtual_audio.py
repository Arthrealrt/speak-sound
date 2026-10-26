"""Opt-in synthetic render -> virtual microphone test. Never opens a physical mic."""
import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np
import pyaudiowpatch as pa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from speak_sound.virtual_mic import VirtualMicrophone
from speak_sound.voice import VoiceProcessor


def main():
    manager = VirtualMicrophone()
    p = capture = output = None
    recorded = []
    recording = [False]
    try:
        manager.start()
        p = pa.PyAudio()
        api = p.get_host_api_info_by_type(pa.paWASAPI)['index']
        devices = [d for d in p.get_device_info_generator()
                   if d['hostApi'] == api and 'Speak Sound Virtual' in d['name'] and not d.get('isLoopbackDevice')]
        microphone = next(d for d in devices if d['maxInputChannels'] > 0)
        speaker = next(d for d in devices if d['maxOutputChannels'] > 0)
        rate = int(speaker['defaultSampleRate'])
        assert rate == int(microphone['defaultSampleRate']) == 48000
        def receive(data, frames, info, status):
            if recording[0]:
                recorded.append(data)
            return None, pa.paContinue
        capture = p.open(format=pa.paInt16, channels=2, rate=rate, input=True,
                         input_device_index=int(microphone['index']), frames_per_buffer=960, stream_callback=receive)
        output = p.open(format=pa.paInt16, channels=2, rate=rate, output=True,
                        output_device_index=int(speaker['index']), frames_per_buffer=960)
        for _ in range(25):
            output.write(bytes(960 * 4))
        processor = VoiceProcessor(rate)
        recording[0] = True
        for i in range(150):
            samples = (.2*np.sin(2*np.pi*440*(np.arange(960)+i*960)/rate)).astype(np.float32)
            changed = processor.process(samples, -5)
            output.write(np.repeat((changed*32767).astype(np.int16)[:, None],2,axis=1).tobytes())
        for _ in range(20):
            output.write(bytes(960 * 4))
        recording[0] = False
        samples = np.frombuffer(b''.join(recorded),np.int16).reshape(-1,2).mean(axis=1)/32768
        samples = samples[rate//3:-rate//3]
        spectrum = np.abs(np.fft.rfft(samples*np.hanning(len(samples))))
        dominant = float(np.argmax(spectrum)*rate/len(samples))
        rms = float(np.sqrt(np.mean(samples*samples)))
        result = dict(sample_rate=rate, captured_frames=len(samples), rms=round(rms,5),
                      source_hz=440, pitch_semitones=-5, expected_hz=round(440*2**(-5/12),2),
                      captured_peak_hz=round(dominant,2), physical_microphone_opened=False,
                      raw_capture_saved=False)
        assert rms > .001, 'Virtual microphone returned silence'
        assert abs(dominant - 440*2**(-5/12)) < 15, result
        (ROOT/'work').mkdir(exist_ok=True)
        (ROOT/'work/virtual-audio-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result),flush=True)
    finally:
        for stream in (output,capture):
            if stream is not None:
                stream.stop_stream()
                stream.close()
        if p is not None:
            p.terminate()
        manager.stop()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',help='Create a temporary virtual cable and test synthetic audio')
    args=parser.parse_args()
    if args.run:
        main()
    else:
        parser.print_help()
