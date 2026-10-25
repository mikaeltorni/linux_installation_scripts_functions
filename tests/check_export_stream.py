"""Export selection through the public runtime without truncating caller output."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='framework-export-stream-') as directory:
    temporary = Path(directory)
    fixture = temporary/'install.sh'
    fixture.write_text('''#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$FIXTURE_DIRECTORY"
source "$FRAMEWORK_ROOT/component_runtime.sh"
ISC_REPO_NAME=fixture
ISC_COMPONENTS=("alpha|Alpha|on|apply_alpha|detect_alpha")
# Keep the fixture operation free of external effects.
# Parameters: none. Returns: zero.
apply_alpha() { printf 'parameters=none\\n0\\n' >&2; }
# Report a noisy detection result as legacy owners do.
# Parameters: none. Returns: one because the fixture component is absent.
detect_alpha() { printf 'parameters=none\\n1\\n'; return 1; }
component_main "$@"
''')
    environment = dict(PATH=os.environ['PATH'], HOME=str(temporary/'home'),
                       XDG_STATE_HOME=str(temporary/'state'), XDG_CACHE_HOME=str(temporary/'cache'),
                       FRAMEWORK_ROOT=str(ROOT), FIXTURE_DIRECTORY=str(temporary))
    output = temporary/'combined-output'
    marker = b'earlier installation output\n'
    with output.open('wb') as stream:
        stream.write(marker)
        stream.flush()
        result = subprocess.run(['bash', str(fixture), '--export-selection'], env=environment,
                                stdout=stream, stderr=subprocess.PIPE, timeout=30)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    data = output.read_bytes()
    assert data.startswith(marker), ('export truncated prior caller output', data[:100])
    assert b'\0' not in data, 'export introduced holes in redirected output'
    document = json.loads(data[len(marker):])
    assert document['scope'] == 'standalone' and document['components']['alpha']['on'] == 1, document
    result = subprocess.run(['bash', str(fixture), '--detect'], env=environment, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0 and result.stdout == 'alpha\tabsent\n', (result.stdout,result.stderr)
print('PASS: public selection export preserves preceding output and valid JSON on redirected stdout')
