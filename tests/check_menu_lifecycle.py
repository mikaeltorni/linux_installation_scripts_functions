"""Verify accepted, cancelled and removal selections under a real strict Bash terminal."""
import os
from pathlib import Path
import pty
import select
import subprocess
import tempfile
import time

def run_terminal(command, environment, keys):
    """Drive a real standalone component menu in an isolated terminal.

    Parameters: command - public installer argv; environment - isolated subprocess variables; keys - menu input bytes.
    Returns: exit status and complete terminal output.
    """
    print(f'command={command!r} environment={environment!r} keys={keys!r}')
    master, slave = pty.openpty()
    process = subprocess.Popen(command, env=environment, stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
    os.close(slave)
    output = bytearray()
    sent = False
    saved = False
    deadline = time.monotonic() + 20
    try:
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                output.extend(chunk)
                if not sent and b'Named task workspaces' in output:
                    os.write(master, keys)
                    sent = True
                if not saved and b'Choice [1/2/3]' in output:
                    os.write(master, b'3\r')
                    saved = True
            elif process.poll() is not None:
                break
        if process.poll() is None:
            process.wait(timeout=2)
        assert sent, output.decode(errors='replace')
        result = process.returncode, output.decode(errors='replace')
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
    print(result)
    return result


ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='strict-menu-') as directory:
    temporary = Path(directory)
    fixture = temporary / 'install.sh'
    marker = temporary / 'effects'
    fixture.write_text('''#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$FIXTURE_DIRECTORY"
source "$FIXTURE_ROOT/component_runtime.sh"
# Apply the isolated component.
# Parameters: none. Returns: zero.
install_component() { printf 'parameters=none\\n' >&2; printf 'installed\\n' >> "$MARKER"; printf '0\\n' >&2; }
# Remove the isolated component.
# Parameters: none. Returns: zero.
remove_component() { printf 'parameters=none\\n' >&2; printf 'removed\\n' >> "$MARKER"; printf '0\\n' >&2; }
ISC_REPO_NAME=fixture
ISC_COMPONENTS=("task_workspaces|Named task workspaces|on|install_component||remove_component")
component_main "$@"
''')
    environment = dict(PATH=os.environ['PATH'], HOME=str(temporary/'home'), XDG_STATE_HOME=str(temporary/'state'), FIXTURE_ROOT=str(ROOT), FIXTURE_DIRECTORY=str(temporary), MARKER=str(marker), TERM='xterm')
    command = ['bash', str(fixture)]
    status, output = run_terminal(command, environment, b'q')
    assert status == 0 and not marker.exists(), output
    status, output = run_terminal(command, environment, b'\r')
    assert status == 0 and marker.read_text() == 'installed\n', output
    status, output = run_terminal(command, environment, b'u\r')
    assert status == 0 and marker.read_text() == 'installed\nremoved\n', output
print('PASS: standalone menu cancellation, installation and removal with strict Bash')
