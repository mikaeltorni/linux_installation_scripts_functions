"""Export or verify licensed installer support for an independent consumer."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    'component_loader.sh', 'component_logging.sh', 'component_menu.sh',
    'component_runtime.sh', 'installer_helpers.sh', 'safe_system_action.sh',
    'logging_utils.py', 'tmux_background_output.py', 'hotkey_capture.sh',
    'hotkey_capture.py', 'monitor_layout.sh', 'monitor_layout.py',
    'repeatable_fields.py', 'installation_config.sh', 'installation_config.py',
    'LICENSE.md',
)


def parse_arguments(arguments):
    """Convert the export command's options once.

    Parameters: arguments - raw argument strings.
    Returns: the resolved destination Path and verification-only flag.
    """
    print(f'arguments={arguments!r}', file=sys.stderr)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=lambda value: Path(value).expanduser().absolute(), required=True)
    parser.add_argument('--check', action='store_true', help='verify without changing the export')
    options = parser.parse_args(arguments)
    result = options.output, options.check
    print(result, file=sys.stderr)
    return result


def validate_destination(destination):
    """Reject destinations that could overwrite source or follow a symlink.

    Parameters: destination - parsed absolute support directory.
    Returns: the accepted destination unchanged.
    """
    print(f'destination={destination!r}', file=sys.stderr)
    if destination == ROOT or destination in ROOT.parents:
        raise ValueError('support export cannot replace the framework source or its parents')
    if any(path.is_symlink() for path in (destination, *destination.parents)):
        raise ValueError('support export cannot follow symlink directories')
    if destination.exists() and not destination.is_dir():
        raise ValueError('support output must be a directory')
    print(destination, file=sys.stderr)
    return destination


def validate_export(destination, expected):
    """Require an exact generated export before accepting a verification run.

    Parameters: destination - support directory; expected - named byte contents.
    Returns: None when all files match and no unowned files are present.
    """
    print(f'destination={destination!r} expected_names={tuple(expected)!r}', file=sys.stderr)
    if not destination.is_dir() or {path.name for path in destination.iterdir()} != set(expected):
        raise ValueError('support file set differs; regenerate the export')
    for name, content in expected.items():
        path = destination / name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
            raise ValueError(f'stale or altered support file: {name}')
    print(None, file=sys.stderr)


def build_export():
    """Build the maintained source subset and its provenance manifest.

    Parameters: none.
    Returns: a mapping of support filenames to complete byte contents.
    """
    print('parameters=none', file=sys.stderr)
    result = {name: (ROOT / name).read_bytes() for name in FILES}
    result['bootstrap.sh'] = (ROOT / 'standalone_bootstrap.sh').read_bytes()
    revision = hashlib.sha256(b''.join(name.encode() + b'\0' + content for name, content in sorted(result.items()))).hexdigest()
    manifest = {
        'schema': 1,
        'source_repository': 'https://github.com/mikaeltorni/linux_installation_scripts_functions',
        'source_revision': 'sha256:' + revision,
        'license': 'MIT',
        'files': {name: hashlib.sha256(content).hexdigest() for name, content in sorted(result.items())},
    }
    result['manifest.json'] = (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()
    print(result, file=sys.stderr)
    return result


def export_support(destination, check):
    """Copy or verify the exact maintained installer support subset.

    Parameters: destination - parsed output Path; check - verify without writes.
    Returns: None after a complete verified export.
    """
    print(f'destination={destination!r} check={check!r}', file=sys.stderr)
    validate_destination(destination)
    expected = build_export()
    if not check:
        destination.mkdir(parents=True, exist_ok=True)
        # A generated directory is replaced only after rejecting unowned content.
        previous = destination / 'manifest.json'
        owned = set(expected)
        if previous.is_file() and not previous.is_symlink():
            owned.update(json.loads(previous.read_text()).get('files', {}))
        validate_owned_paths(destination, owned)
        for name, content in expected.items():
            (destination / name).write_bytes(content)
        for path in destination.iterdir():
            if path.name not in expected:
                path.unlink()
    validate_export(destination, expected)
    print(None, file=sys.stderr)


def validate_owned_paths(destination, owned):
    """Protect unowned files from replacement in a generated support directory.

    Parameters: destination - existing support directory; owned - allowed filenames.
    Returns: None when every existing entry is a regular owned file.
    """
    print(f'destination={destination!r} owned={sorted(owned)!r}', file=sys.stderr)
    for path in destination.iterdir():
        if path.name not in owned or path.is_symlink() or not path.is_file():
            raise ValueError(f'refusing to overwrite unowned support entry: {path.name}')
    print(None, file=sys.stderr)


def main(arguments):
    """Dispatch the converted export request and report failures.

    Parameters: arguments - raw command-line arguments.
    Returns: zero on success, two on rejected or failed exports.
    """
    print(f'arguments={arguments!r}', file=sys.stderr)
    destination, check = parse_arguments(arguments)
    try:
        export_support(destination, check)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        print(2, file=sys.stderr)
        return 2
    print(0, file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
