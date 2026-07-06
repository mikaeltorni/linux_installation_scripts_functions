"""Tests for select-configure components in the component menu.

A component flagged CM_COMP_CONFIGURE_ON_SELECT[repo|id]=1 cannot install
without a typed setting (e.g. a repository name), so toggling it on with
SPACE must immediately open its nested configurator via
CM_CONFIGURE_CALLBACK. A cancelled or failed configurator reverts the toggle
so the component is never applied unconfigured.
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

KEYS = {
    "DOWN": "\x1b[B",
    "SPACE": " ",
    "ENTER": "\n",
}


def drive_submenu(keys, callback_exit=0, on_select=True, initially_on=False):
    """Drive a one-component submenu and report toggle/callback state."""
    keystream = "".join(KEYS[k] for k in keys)
    script = f"""
set -uo pipefail
source "{REPO}/component_menu.sh"
repo=demo
CM_REPOS=("$repo")
CM_REPO_LABEL[$repo]=Demo
CM_REPO_ENABLED[$repo]=1
CM_COMP_IDS[$repo]="notes"
CM_COMP_LABEL[$repo|notes]=Notes
CM_COMP_INSTALLED[$repo|notes]=0
CM_COMP_ON[$repo|notes]={1 if initially_on else 0}
CM_COMP_UNINSTALL[$repo|notes]=0
CM_COMP_CONFIGURE_ELIGIBLE[$repo|notes]=1
CM_COMP_CONFIGURE_ON_SELECT[$repo|notes]={1 if on_select else 0}
callback_calls=0
demo_configure() {{ callback_calls=$((callback_calls + 1)); return {callback_exit}; }}
CM_CONFIGURE_CALLBACK=demo_configure
cm_single_submenu "$repo" >/dev/null 2>&1
printf 'on=%s\\n' "${{CM_COMP_ON[$repo|notes]:-}}"
printf 'calls=%s\\n' "$callback_calls"
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


def test_space_on_opens_configurator_and_keeps_selection():
    state = drive_submenu(["SPACE", "ENTER"])
    assert state["calls"] == "1", "configurator must open on select"
    assert state["on"] == "1", "successful configure keeps the toggle on"


def test_cancelled_configurator_reverts_toggle():
    state = drive_submenu(["SPACE", "ENTER"], callback_exit=2)
    assert state["calls"] == "1"
    assert state["on"] == "0", "cancelled configure must revert the toggle"


def test_space_off_does_not_open_configurator():
    state = drive_submenu(["SPACE", "ENTER"], initially_on=True)
    assert state["calls"] == "0", "toggling off must not open the configurator"
    assert state["on"] == "0"


def test_plain_component_toggles_without_configurator():
    state = drive_submenu(["SPACE", "ENTER"], on_select=False)
    assert state["calls"] == "0"
    assert state["on"] == "1"
