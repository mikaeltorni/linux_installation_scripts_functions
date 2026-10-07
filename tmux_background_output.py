#!/usr/bin/env python3
"""Preserve background console output on disk and bound its tmux history.

start --target SESSION:WINDOW --archive-dir DIR [--cwd DIR] -- COMMAND...
record --file FILE reads raw console bytes from stdin (used by pipe-pane).
Read archives with: gzip -cd DIR/*.gz | less -R
"""

import argparse
from datetime import datetime, timezone
import gzip
import os
from pathlib import Path
import shlex
import subprocess
import sys
import uuid

HISTORY_LIMIT = 2000


def parse_command(argv):
    """Parse the complete public command before performing operations.

    Parameters: argv - command-line argument list.
    Returns: validated argparse namespace.
    """
    print(f"argv={argv}")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    record = commands.add_parser("record")
    record.add_argument("--file", required=True, type=Path)
    start = commands.add_parser("start")
    start.add_argument("--target", required=True)
    start.add_argument("--archive-dir", required=True, type=Path)
    start.add_argument("--cwd", type=Path)
    start.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.operation == "start":
        if args.command and args.command[0] == "--":
            args.command = args.command[1:]
        if not args.command:
            parser.error("start requires a command after --")
        if ":" not in args.target or any(not part for part in args.target.split(":", 1)):
            parser.error("target must be SESSION:WINDOW")
        args.session, args.window = args.target.split(":", 1)
    print(args)
    return args


def record_stream(stream, path):
    """Append complete gzip members without accumulating console history.

    Parameters: stream - binary input stream; path - output archive path.
    Returns: None.
    """
    print(f"stream={stream} path={path}")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "ab", buffering=0) as output:
        if os.fstat(output.fileno()).st_size == 0:
            output.write(gzip.compress(b"", compresslevel=1, mtime=0))
        while chunk := stream.read1(65536):
            # Each member is finalized before its bytes are published. A killed
            # recorder cannot invalidate earlier chunks, and live archives read
            # without waiting for this long-running pane to exit.
            member = memoryview(gzip.compress(chunk, compresslevel=1, mtime=0))
            while member:
                written = output.write(member)
                member = member[written:]
    print(None)


def tmux(*arguments):
    """Run one tmux operation against the caller's server.

    Parameters: arguments - tmux argument sequence.
    Returns: stripped stdout text.
    """
    print(f"arguments={arguments}")
    result = subprocess.check_output(["tmux", *map(str, arguments)], text=True).strip()
    print(result)
    return result


def archive_path(directory, suffix):
    """Reserve a private uniquely named archive without deleting old ones.

    Parameters: directory - archive directory; suffix - archive role.
    Returns: reserved archive path.
    """
    print(f"directory={directory} suffix={suffix}")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = directory / f"{stamp}-{uuid.uuid4().hex[:8]}-{suffix}.gz"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(gzip.compress(b"", compresslevel=1, mtime=0))
    print(path)
    return path


def connect_recorder(pane, directory):
    """Attach raw output recording before launching or replacing a process.

    Parameters: pane - exact tmux pane id; directory - archive directory.
    Returns: None.
    """
    print(f"pane={pane} directory={directory}")
    path = archive_path(directory, "output")
    command = shlex.join([sys.executable, str(Path(__file__).resolve()), "record", "--file", str(path)])
    tmux("pipe-pane", "-O", "-t", pane, command + " >/dev/null")
    print(None)


def snapshot_history(pane, directory):
    """Save existing visible/history text before any pane replacement.

    Parameters: pane - exact tmux pane id; directory - archive directory.
    Returns: None.
    """
    print(f"pane={pane} directory={directory}")
    path = archive_path(directory, "snapshot")
    process = subprocess.Popen(["tmux", "capture-pane", "-p", "-e", "-S", "-", "-t", pane], stdout=subprocess.PIPE)
    with process.stdout:
        record_stream(process.stdout, path)
    if process.wait():
        raise RuntimeError("Cannot preserve existing pane history; pane left running")
    print(None)


def start_background(args):
    """Archive and restart one dedicated background window safely.

    Parameters: args - parsed target, directory, cwd and command values.
    Returns: zero on successful launch.
    """
    print(f"args={args}")
    if args.cwd is not None and not args.cwd.is_dir():
        raise ValueError(f"Working directory does not exist: {args.cwd}")
    args.archive_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    session, window = args.session, args.window
    windows = tmux("list-windows", "-t", session, "-F", "#{window_name}").splitlines()
    if window not in windows:
        tmux("new-window", "-d", "-t", session, "-n", window, "sleep infinity")
    panes = tmux("list-panes", "-t", args.target, "-F", "#{pane_id} #{history_limit}").splitlines()
    if len(panes) != 1:
        raise RuntimeError("Refusing to replace a window with multiple panes")
    old_pane, old_limit = panes[0].split()
    # Record ongoing output before taking a snapshot; this closes the gap
    # between capture and restart. Snapshot/live overlap intentionally preserves
    # everything rather than deduplicating terminal control sequences.
    connect_recorder(old_pane, args.archive_dir)
    snapshot_history(old_pane, args.archive_dir)
    tmux("set-window-option", "-t", args.target, "history-limit", str(HISTORY_LIMIT))
    pane = old_pane
    try:
        if int(old_limit) > HISTORY_LIMIT:
            # respawn-pane keeps its old grid limit. Allocate a bounded grid
            # first; a tiny split avoids reflowing the large old history.
            pane = tmux("split-window", "-d", "-l", "1", "-P", "-F", "#{pane_id}", "-t", old_pane, "sleep infinity")
            connect_recorder(pane, args.archive_dir)
        command = shlex.join(args.command)
        cwd = ["-c", str(args.cwd)] if args.cwd else []
        tmux("respawn-pane", "-k", "-t", pane, *cwd, command)
    except Exception:
        if pane != old_pane:
            tmux("kill-pane", "-t", pane)
        raise
    if pane != old_pane:
        tmux("kill-pane", "-t", old_pane)
    print(0)
    return 0


def main(argv):
    """Dispatch parsed commands to their operation owners.

    Parameters: argv - raw CLI arguments.
    Returns: process exit status.
    """
    print(f"argv={argv}")
    args = parse_command(argv)
    if args.operation == "record":
        record_stream(sys.stdin.buffer, args.file)
        result = 0
    else:
        result = start_background(args)
    print(result)
    return result


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
