"""Shell-free command capture with bounded memory and wall-clock timeout."""
import os
from pathlib import Path
import platform
import subprocess
import threading
import time

from .evidence import redact


def run_command(command, cwd, timeout=60, limit=6000):
    if not command or not all(isinstance(s, str) for s in command):
        raise ValueError('command must be a nonempty argv list')
    record = {'command': [redact(s) for s in command], 'cwd': redact(Path(cwd).resolve()),
              'host_python': platform.python_version(), 'exit_code': None, 'status': 'BLOCKED',
              'label': 'BLOCKED', 'output': '', 'truncated': False}
    started = time.monotonic()
    captured = bytearray()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    try:
        process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, shell=False, env=env)
        def drain():
            try:
                while True:
                    chunk = process.stdout.read(1024)
                    if not chunk:
                        break
                    remaining = max(0, limit - len(captured))
                    captured.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        record['truncated'] = True
            finally:
                process.stdout.close()
        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        try:
            record['exit_code'] = process.wait(timeout=timeout)
            record['status'] = 'PASS' if record['exit_code'] == 0 else 'FAIL'
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
            record['exit_code'] = process.returncode
            record['status'] = 'TIMEOUT'
        reader.join(timeout=2)
        record['label'] = 'VERIFIED_BY_EXECUTION'
    except OSError as exc:
        record['output'] = redact(exc)[:limit]
    if captured:
        record['output'] = redact(captured.decode('utf-8', errors='replace').replace('\r\r\n', '\n').replace('\r\n', '\n'))
    record['duration_seconds'] = round(time.monotonic() - started, 3)
    return record
