"""Reject malformed public component actions before any core or state changes."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='component lifecycle ') as directory:
    temporary = Path(directory)
    marker = temporary / 'actions'
    fixture = temporary / 'install.sh'
    fixture.write_text('''#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$FIXTURE_HOME"
source "$FIXTURE_ROOT/component_loader.sh"
isc_load_helpers
isc_activate_components
# Record a core application without external effects.
# Parameters: none. Returns: zero.
apply_core() { printf 'parameters=none\\n' >&2; printf 'core\\n' >> "$CALLS"; printf '0\\n' >&2; }
# Record installation of alpha.
# Parameters: none. Returns: zero.
apply_alpha() { printf 'parameters=none\\n' >&2; printf 'alpha\\n' >> "$CALLS"; printf '0\\n' >&2; }
# Record installation of beta.
# Parameters: none. Returns: zero.
apply_beta() { printf 'parameters=none\\n' >&2; printf 'beta\\n' >> "$CALLS"; printf '0\\n' >&2; }
# Record a requested alpha reversal.
# Parameters: none. Returns: zero.
remove_alpha() { printf 'parameters=none\\n' >&2; printf 'remove alpha\\n' >> "$CALLS"; printf '0\\n' >&2; }
ISC_REPO_NAME=fixture
ISC_CORE=apply_core
ISC_COMPONENTS=("alpha|Alpha|on|apply_alpha||remove_alpha" "beta|Beta|off|apply_beta")
component_main "$@"
''')
    env = dict(PATH=os.environ['PATH'], HOME=str(temporary/'home'), XDG_STATE_HOME=str(temporary/'state'), XDG_CACHE_HOME=str(temporary/'cache'), FIXTURE_ROOT=str(ROOT), FIXTURE_HOME=str(temporary), CALLS=str(marker))
    bad = (
        ['--select','unknown'], ['--select','alpha,unknown'],
        ['--select','alpha,alpha'], ['--uninstall','unknown'],
        ['--uninstall','alpha,unknown'], ['--uninstall','alpha,alpha'],
        ['--select'], ['--uninstall'], ['--reconfigure'],
        ['--default','unexpected'], ['--list-components','unexpected'],
        ['--select','alpha','--uninstall','beta'],
        ['--default','--all'], ['--select','alpha,,beta'],
        ['--detect','--select','alpha'], ['--config'],
        ['--select','alpha, ,beta'], ['--configure-component'],
        ['--configure-component', 'unknown'], ['--select','../alpha'],
        ['--help', 'extra'], ['--config=', '--detect'],
    )
    for arguments in bad:
        before = marker.read_bytes() if marker.exists() else None
        result = subprocess.run(['bash',str(fixture),*arguments],env=env,text=True,capture_output=True)
        assert result.returncode == 2, (arguments,result.returncode,result.stdout,result.stderr)
        assert (marker.read_bytes() if marker.exists() else None) == before, arguments
    for arguments, expected in (
        (['--select','alpha'], 'core\nalpha\n'),
        (['--reconfigure','alpha'], 'core\nalpha\ncore\nalpha\n'),
        (['--uninstall','alpha'], 'core\nalpha\ncore\nalpha\nremove alpha\n'),
        (['--select',''], 'core\nalpha\ncore\nalpha\nremove alpha\ncore\n'),
    ):
        result=subprocess.run(['bash',str(fixture),*arguments],env=env,text=True,capture_output=True)
        assert result.returncode==0,(arguments,result.stdout,result.stderr)
        assert marker.read_text()==expected,(arguments,marker.read_text())
    before=marker.read_bytes()
    for arguments in (['--list-components'], ['--detect'], ['--help'], ['--export-selection']):
        result=subprocess.run(['bash',str(fixture),*arguments],env=env,text=True,capture_output=True)
        assert result.returncode==0,(arguments,result.stdout,result.stderr)
        assert marker.read_bytes()==before,arguments
    # Retain successful direct forms, normalized lists and stateful detection.
    for arguments, expected_delta in (
        (['--default'], 'core\nalpha\n'),
        (['--all'], 'core\nalpha\nbeta\n'),
        (['--select=beta,alpha'], 'core\nalpha\nbeta\n'),
        (['--reconfigure=beta'], 'core\nbeta\n'),
        (['--uninstall=beta'], ''),
        (['--uninstall', ''], ''),
    ):
        before = marker.read_text()
        result = subprocess.run(['bash', str(fixture), *arguments], env=env, text=True, capture_output=True)
        assert result.returncode == 0, (arguments, result.stdout, result.stderr)
        assert marker.read_text() == before + expected_delta, arguments
    result = subprocess.run(['bash', str(fixture), '--detect'], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ['alpha\tinstalled', 'beta\tabsent'], result.stdout
    # Invalid requests also preserve an existing installed state.
    for arguments in bad:
        before = marker.read_bytes()
        result = subprocess.run(['bash', str(fixture), *arguments], env=env, text=True, capture_output=True)
        assert result.returncode == 2, (arguments, result.stdout, result.stderr)
        assert marker.read_bytes() == before, arguments
    # Owners with an external core must reject before entering that core as well.
    routed = temporary / 'routed-install.sh'
    routed.write_text(fixture.read_text().replace('component_main "$@"', 'if isc_route_readonly_args "$@"; then exit $?; fi\napply_core\ncomponent_main "$@"'))
    for arguments in (*bad, ['--config', 'default.json', '--detect']):
        before = marker.read_bytes()
        result = subprocess.run(['bash', str(routed), *arguments], env=env, text=True, capture_output=True)
        expected_status = 0 if arguments == ['--config', 'default.json', '--detect'] else 2
        assert result.returncode == expected_status, (arguments, result.stdout, result.stderr)
        assert marker.read_bytes() == before, arguments
    configs = temporary / 'installation_configs'
    configs.mkdir()
    (configs / 'mixed.json').write_text(json.dumps({
        'schema_version': 1, 'scope': 'standalone', 'repo': 'fixture',
        'components': {'alpha': {'on': 0, 'uninstall': 1}, 'beta': {'on': 1, 'uninstall': 0}},
    }))
    before = marker.read_text()
    result = subprocess.run(['bash', str(fixture), '--config', 'mixed.json'], env=env, text=True, capture_output=True)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert marker.read_text() == before + 'remove alpha\ncore\nbeta\n', (marker.read_text(), result.stderr)
print('PASS: strict public lifecycle grammar, pre-effect validation, install/reconfigure/removal and read-only queries')
