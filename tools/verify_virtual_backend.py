"""Check the compiled local USB/IP backend without installing or attaching drivers."""
from pathlib import Path
import json
import socket
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    process = subprocess.Popen([str(ROOT / 'bin/speak-sound-mic.exe')], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        ready = json.loads(process.stdout.readline())
        assert ready.get('ready') is True
        with socket.create_connection(('127.0.0.1', 32401), timeout=3) as connection:
            connection.sendall(struct.pack('!HHI', 0x111, 0x8005, 0))
            response = b''
            while len(response) < 12:
                chunk = connection.recv(12-len(response))
                if not chunk:
                    raise RuntimeError('Incomplete USB/IP device list reply')
                response += chunk
            version, operation, status, count = struct.unpack('!HHII', response)
            assert (version, operation, status, count) == (0x111, 5, 0, 1)
        print('Compiled backend exports one USB audio device only on localhost; no driver attached.')
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=3)
        process.stdout.close()
        process.stderr.close()
    assert process.returncode == 0
    print('Backend exits cleanly on owner EOF.')


if __name__ == '__main__':
    main()
