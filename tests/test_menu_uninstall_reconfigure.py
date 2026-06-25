#!/usr/bin/env python3
"""Interaction tests for the install-aware component submenu (component_menu.sh).

Drives cm_single_submenu with a scripted keystroke stream (read from a pipe, so
no real TTY is needed) and inspects the resulting CM_* selection arrays. This
locks the state machine for the three actions the menu must support on top of
plain install selection: reconfigure of an installed component (SPACE), marking
an installed component for uninstall ([u]), and reconfigure-all ([r]).
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Key tokens -> raw bytes the menu's cm_read_key consumes.
KEYS = {
    "DOWN": "\x1b[B",
    "UP": "\x1b[A",
    "SPACE": " ",
    "U": "u",
    "R": "r",
    "ENTER": "\n",
    "Q": "q",
}


def drive(keys: list[str]) -> dict[str, str]:
    """Run the submenu with two components (alpha installed, beta absent).

    Feeds `keys` and returns the resolved per-component state as a dict of
    "<id>.on" / "<id>.uninstall" -> value.
    """
    keystream = "".join(KEYS[k] for k in keys)
    script = f"""
set -uo pipefail
source "{REPO}/component_menu.sh"
repo=demo
CM_REPOS=("$repo")
CM_REPO_LABEL[$repo]=Demo
CM_REPO_ENABLED[$repo]=1
CM_COMP_IDS[$repo]="alpha beta"
CM_COMP_LABEL[$repo|alpha]=Alpha
CM_COMP_LABEL[$repo|beta]=Beta
CM_COMP_INSTALLED[$repo|alpha]=1
CM_COMP_INSTALLED[$repo|beta]=0
CM_COMP_ON[$repo|alpha]=0
CM_COMP_ON[$repo|beta]=1
CM_COMP_UNINSTALL[$repo|alpha]=0
CM_COMP_UNINSTALL[$repo|beta]=0
cm_single_submenu "$repo" >/dev/null 2>&1
for id in alpha beta; do
  printf '%s.on=%s\\n' "$id" "${{CM_COMP_ON[$repo|$id]:-}}"
  printf '%s.uninstall=%s\\n' "$id" "${{CM_COMP_UNINSTALL[$repo|$id]:-}}"
done
"""
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=REPO,
        input=keystream,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def test_space_reconfigures_installed_component():
    """SPACE on the installed alpha row selects it for reconfigure (on=1)."""
    state = drive(["SPACE", "ENTER"])
    assert state["alpha.on"] == "1"
    assert state["alpha.uninstall"] == "0"


def test_u_marks_installed_for_uninstall_and_clears_apply():
    """[u] on alpha marks uninstall and clears any apply selection."""
    # SPACE first selects reconfigure, then U must flip to uninstall.
    state = drive(["SPACE", "U", "ENTER"])
    assert state["alpha.uninstall"] == "1"
    assert state["alpha.on"] == "0"


def test_u_is_ignored_for_absent_component():
    """[u] on the absent beta row does nothing (cannot uninstall what's absent)."""
    state = drive(["DOWN", "U", "ENTER"])
    assert state["beta.uninstall"] == "0"


def test_reconfigure_all_selects_only_installed():
    """[r] selects every installed component for reconfigure, not absent ones."""
    state = drive(["R", "ENTER"])
    assert state["alpha.on"] == "1"
    # beta started on=1 (absent default) and [r] must not touch it.
    assert state["beta.on"] == "1"
    assert state["beta.uninstall"] == "0"


if __name__ == "__main__":
    import tempfile  # noqa: F401

    tests = [v for n, v in sorted(globals().items()) if n.startswith("test_") and callable(v)]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"PASS: {test.__name__}")
        except Exception as error:  # noqa: BLE001
            failures += 1
            print(f"FAIL: {test.__name__} - {error}")
    raise SystemExit(failures)
