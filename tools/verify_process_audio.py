"""Opt-in audio isolation probe: two quiet synthetic tones, never microphone audio."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from speak_sound.process_audio import ProcessTarget, open_process_loopback


def tone(frequency):
    import pyaudiowpatch as pa
    print(os.getpid(), flush=True)
    time.sleep(2)
    with pa.PyAudio() as p:
        index = int(p.get_host_api_info_by_type(pa.paWASAPI)['defaultOutputDevice'])
        device = p.get_device_info_by_index(index)
        rate, channels = int(device['defaultSampleRate']), min(2, int(device['maxOutputChannels']))
        block = rate // 50
        stream = p.open(format=pa.paInt16, channels=channels, rate=rate, output=True, output_device_index=index)
        try:
            for i in range(250):
                samples = (.025 * 32767 * np.sin(2*np.pi*frequency*(np.arange(block)+i*block)/rate)).astype(np.int16)
                stream.write(np.repeat(samples[:, None], channels, axis=1).tobytes())
        finally:
            stream.stop_stream()
            stream.close()


def probe():
    children = [subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--test-tone', str(freq)],
                    creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, encoding='utf-8',
                    env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}) for freq in (440, 880)]
    native = None
    try:
        actual_pids = [int(child.stdout.readline().strip()) for child in children]
        # Select the launcher to also exercise capture of an existing child process.
        process = psutil.Process(children[0].pid)
        target = ProcessTarget(process.pid, process.create_time(), 'synthetic-440-tree')
        native = open_process_loopback(target)
        native.start()
        fmt = native.get_format()
        chunks, until = [], time.monotonic() + 6
        while time.monotonic() < until:
            data = native.read()
            if data:
                chunks.append(data)
            time.sleep(.005)
        dtype = np.float32 if fmt['bits_per_sample'] == 32 else np.int16
        signal = np.frombuffer(b''.join(chunks), dtype).reshape(-1, fmt['channels']).mean(axis=1)
        spectrum = np.abs(np.fft.rfft(signal))
        frequencies = np.fft.rfftfreq(len(signal), 1/fmt['sample_rate'])
        levels = {freq: float(spectrum[np.abs(frequencies-freq) < 2].max()) for freq in (440, 880)}
        isolation = float(20*np.log10(max(levels[440], 1e-9)/max(levels[880], 1e-9)))
        print(json.dumps(dict(format=fmt, target_frames=len(signal), isolation_db=isolation,
                              launcher_pid=target.pid, renderer_pid=actual_pids[0])), flush=True)
        assert levels[440] > 0 and isolation > 30, 'Target tone missing or non-target tone was captured'
    finally:
        if native is not None:
            native.stop()
        for child in children:
            try:
                output, error = child.communicate(timeout=8)
                if child.returncode:
                    raise RuntimeError(error or output or f'Test renderer failed: {child.returncode}')
            except subprocess.TimeoutExpired:
                child.terminate()
                child.wait(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Plays two quiet test tones for five seconds to verify PID isolation.')
    parser.add_argument('--run', action='store_true', help='Run the audible test explicitly')
    parser.add_argument('--test-tone', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.test_tone:
        tone(args.test_tone)
    elif args.run:
        probe()
    else:
        parser.print_help()
