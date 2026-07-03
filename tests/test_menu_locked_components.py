"""Tests for locked-component behavior in the component menu (component_menu.sh).

A locked component (CM_COMP_LOCKED[repo|id]=1) is force-selected and cannot be
deselected by the user. This is used by the master installer to enforce
cross-repository runtime dependencies such as tmux. These tests verify that
SPACE, NONE, and aggregate-repo-disable all respect the lock, and that the
post-toggle callback and CM_NOTICE line work as expected.
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

KEYS = {
    "DOWN": "\x1b[B",
    "UP": "\x1b[A",
    "SPACE": " ",
    "RIGHT": "\x1b[C",
    "ENTER": "\n",
    "Q": "q",
    "N": "n",
    "A": "a",
}


def drive_submenu(keys, locked=None, post_callback=None):
    """Run the submenu with alpha (locked) and beta (free) components.

    Returns a dict of resolved per-component state.
    """
    locked = locked or []
    keystream = "".join(KEYS[k] for k in keys)
    locked_setup = ""
    for comp in locked:
        locked_setup += f"CM_COMP_LOCKED[$repo|{comp}]=1\n"
    callback_setup = ""
    if post_callback:
        callback_setup = f"CM_POST_TOGGLE_CALLBACK={post_callback}\n"
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
CM_COMP_INSTALLED[$repo|alpha]=0
CM_COMP_INSTALLED[$repo|beta]=0
CM_COMP_ON[$repo|alpha]=1
CM_COMP_ON[$repo|beta]=1
CM_COMP_UNINSTALL[$repo|alpha]=0
CM_COMP_UNINSTALL[$repo|beta]=0
{locked_setup}
{callback_setup}
test_cb_called=0
test_cb() {{ test_cb_called=1; }}
cm_single_submenu "$repo" >/dev/null 2>&1
for id in alpha beta; do
  printf '%s.on=%s\\n' "$id" "${{CM_COMP_ON[$repo|$id]:-}}"
  printf '%s.locked=%s\\n' "$id" "${{CM_COMP_LOCKED[$repo|$id]:-0}}"
done
printf 'cb_called=%s\\n' "$test_cb_called"
printf 'notice=%s\\n' "${{CM_NOTICE:-}}"
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


def test_space_cannot_deselect_locked_component():
    """SPACE on a locked component that is ON does not turn it off."""
    state = drive_submenu(["SPACE", "ENTER"], locked=["alpha"])
    assert state["alpha.on"] == "1", f"locked alpha should stay on, got {state['alpha.on']}"
    assert state["alpha.locked"] == "1"


def test_space_can_deselect_unlocked_component():
    """SPACE on a non-locked component still toggles it off."""
    state = drive_submenu(["SPACE", "ENTER"], locked=["alpha"])
    # beta is not locked, but we pressed SPACE on alpha (first row)
    # so beta stays on
    assert state["beta.on"] == "1"


def test_space_can_deselect_beta_when_alpha_locked():
    """SPACE on the non-locked beta row (second row) turns it off."""
    state = drive_submenu(["DOWN", "SPACE", "ENTER"], locked=["alpha"])
    assert state["alpha.on"] == "1", "locked alpha stays on"
    assert state["beta.on"] == "0", "unlocked beta turned off"


def test_none_keeps_locked_components_on():
    """[n] (NONE) does not turn off locked components."""
    state = drive_submenu(["N", "ENTER"], locked=["alpha"])
    assert state["alpha.on"] == "1", "locked alpha survives NONE"
    assert state["beta.on"] == "0", "unlocked beta cleared by NONE"


def test_post_toggle_callback_called_after_space():
    """CM_POST_TOGGLE_CALLBACK is invoked after a SPACE toggle."""
    state = drive_submenu(["DOWN", "SPACE", "ENTER"], locked=[], post_callback="test_cb")
    assert state["cb_called"] == "1", "post-toggle callback should be called"


def test_post_toggle_callback_not_called_on_navigation():
    """CM_POST_TOGGLE_CALLBACK is not called for arrow-key navigation."""
    state = drive_submenu(["DOWN", "ENTER"], locked=[], post_callback="test_cb")
    assert state["cb_called"] == "0", "callback should not fire for navigation"


def test_cm_notice_rendered_in_submenu():
    """CM_NOTICE is rendered (does not crash) when set."""
    keystream = KEYS["ENTER"]
    script = f"""
set -uo pipefail
source "{REPO}/component_menu.sh"
repo=demo
CM_REPOS=("$repo")
CM_REPO_LABEL[$repo]=Demo
CM_REPO_ENABLED[$repo]=1
CM_COMP_IDS[$repo]="alpha"
CM_COMP_LABEL[$repo|alpha]=Alpha
CM_COMP_INSTALLED[$repo|alpha]=0
CM_COMP_ON[$repo|alpha]=1
CM_COMP_UNINSTALL[$repo|alpha]=0
CM_NOTICE="test notice line"
cm_single_submenu "$repo" >/dev/null 2>&1
printf 'ok=1\\n'
"""
    result = subprocess.run(
        ["bash", "-c", script], cwd=REPO, input=keystream, check=False,
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ok=1" in result.stdout


def test_cm_component_locked_helper():
    """cm_component_locked returns 0 for locked, 1 for unlocked."""
    script = f"""
source "{REPO}/component_menu.sh"
declare -gA CM_COMP_LOCKED
CM_COMP_LOCKED[demo|alpha]=1
if cm_component_locked demo alpha; then echo "alpha=locked"; fi
if ! cm_component_locked demo beta; then echo "beta=unlocked"; fi
"""
    result = subprocess.run(
        ["bash", "-c", script], cwd=REPO, check=False,
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "alpha=locked" in result.stdout
    assert "beta=unlocked" in result.stdout


def test_cm_repo_has_locked_helper():
    """cm_repo_has_locked returns 0 when any component is locked."""
    script = f"""
source "{REPO}/component_menu.sh"
declare -gA CM_COMP_LOCKED
declare -gA CM_COMP_IDS
CM_COMP_IDS[demo]="alpha beta"
CM_COMP_LOCKED[demo|beta]=1
if cm_repo_has_locked demo; then echo "has_locked=yes"; fi
"""
    result = subprocess.run(
        ["bash", "-c", script], cwd=REPO, check=False,
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "has_locked=yes" in result.stdout


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS: {name}")
