#!/usr/bin/env python3
"""Integration tests for shared typed hotkey configuration fields."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_typed_hotkey_field_validates_persists_and_displays(tmp_path):
    """A typed field accepts many modifiers plus exactly one key."""
    config = tmp_path / "hotkeys.conf"
    script = f"""
set -euo pipefail
source {str(ROOT / 'hotkey_capture.sh')!r}
run_as_target() {{ "$@"; }}
isc_prompt_hotkey_field {str(config)!r} WORKSPACE_SWITCH_2 'Switch to workspace 2' '<Super>x'
isc_hotkey_field_status {str(config)!r} WORKSPACE_SWITCH_2 '<Super>x'
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        input="ctrl+alt+w\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "Ctrl+Alt+W" in proc.stdout
    assert "WORKSPACE_SWITCH_2=<Control><Alt>w" in config.read_text(encoding="utf-8")


def test_invalid_typed_hotkey_reprompts_without_overwriting(tmp_path):
    """Malformed input cannot replace the current persisted value."""
    config = tmp_path / "hotkeys.conf"
    script = f"""
set -euo pipefail
source {str(ROOT / 'hotkey_capture.sh')!r}
run_as_target() {{ "$@"; }}
isc_prompt_hotkey_field {str(config)!r} WORKSPACE_SWITCH_1 'Switch to workspace 1' '<Super>z'
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        input="super+z+x\nalt+q\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "Invalid hotkey" in proc.stderr
    assert "WORKSPACE_SWITCH_1=<Alt>q" in config.read_text(encoding="utf-8")


def test_modifier_field_persists_one_modifier_only(tmp_path):
    """Modifier fields reject chords and save a single canonical modifier."""
    config = tmp_path / "hotkeys.conf"
    script = f"""
set -euo pipefail
source {str(ROOT / 'hotkey_capture.sh')!r}
run_as_target() {{ "$@"; }}
isc_prompt_modifier_field {str(config)!r} WORKSPACE_MOVE_MODIFIER 'Move modifier' Shift
isc_modifier_field_status {str(config)!r} WORKSPACE_MOVE_MODIFIER Shift
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        input="ctrl+alt\nctrl\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "Invalid modifier" in proc.stderr
    assert proc.stdout.strip().endswith("Ctrl")
    assert "WORKSPACE_MOVE_MODIFIER=Control" in config.read_text(encoding="utf-8")
