#!/usr/bin/env python3
"""Integration tests for shared press-to-capture hotkey configuration fields."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

# Kitty keyboard protocol: Super+u then Enter.
SUPER_U_BYTES = b"\x1b[117;8u\n"
SUPER_ALONE_THEN_U = b"\x1b[57423u\x1b[117u\n"
SUPER_MODIFIER_ONLY = b"\x1b[57421u\n"  # left Ctrl


def test_press_capture_super_u_persists_and_displays(tmp_path):
    """Press-to-capture accepts Super+u and persists the GTK accelerator."""
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
        input=SUPER_U_BYTES,
        text=False,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr.decode()
    assert b"Super+U" in proc.stdout
    assert "WORKSPACE_SWITCH_2=<Super>u" in config.read_text(encoding="utf-8")


def test_press_capture_super_then_u_separately(tmp_path):
    """Modifiers pressed one-by-one still build the final chord."""
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
        input=SUPER_ALONE_THEN_U,
        text=False,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr.decode()
    assert b"Super+U" in proc.stdout
    assert "WORKSPACE_SWITCH_1=<Super>u" in config.read_text(encoding="utf-8")


def test_empty_enter_keeps_current_without_overwriting(tmp_path):
    """Enter on an empty capture keeps the persisted value unchanged."""
    config = tmp_path / "hotkeys.conf"
    config.write_text("WORKSPACE_SWITCH_1=<Super>z\n", encoding="utf-8")
    script = f"""
set -euo pipefail
source {str(ROOT / 'hotkey_capture.sh')!r}
run_as_target() {{ "$@"; }}
isc_prompt_hotkey_field {str(config)!r} WORKSPACE_SWITCH_1 'Switch to workspace 1' '<Super>z'
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        input=b"\n",
        text=False,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr.decode()
    assert proc.stdout.strip() == b""
    assert config.read_text(encoding="utf-8") == "WORKSPACE_SWITCH_1=<Super>z\n"


def test_modifier_field_persists_one_modifier_only(tmp_path):
    """Modifier fields accept exactly one pressed modifier."""
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
        input=SUPER_MODIFIER_ONLY,
        text=False,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr.decode()
    assert proc.stdout.strip().endswith(b"Ctrl")
    assert "WORKSPACE_MOVE_MODIFIER=Control" in config.read_text(encoding="utf-8")