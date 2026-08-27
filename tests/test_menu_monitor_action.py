#!/usr/bin/env python3
"""Interaction tests for the [m] per-application monitor action (component_menu.sh).

Drives cm_single_submenu with a scripted keystroke stream and inspects
CM_COMP_MONITOR, which the master installer serializes into the app-monitor
placement rules. Also covers monitor-layout detection (cm_detect_monitors) and
the footer hint, which must stay hidden when there is nothing to choose from.
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

KEYS = {
    "DOWN": "\x1b[B",
    "UP": "\x1b[A",
    "SPACE": " ",
    "M": "m",
    "U": "u",
    "P": "p",
    "ENTER": "\n",
    "Q": "q",
    **{str(number): str(number) for number in range(10)},
}

# Two fake monitors so [m] has something to cycle through.
FAKE_MONITORS = "1\\tDP-0\\tLeft Screen\\t0\\t0\\t0\\t3840\\t2160\\n2\\tHDMI-0\\tRight Screen\\t1\\t3840\\t0\\t1920\\t1080"


def drive(keys, monitor_eligible=True, monitors=FAKE_MONITORS):
    """Run the submenu over two components and return the resolved state.

    Args:
        keys: Key tokens fed to the menu.
        monitor_eligible: Whether the fixture rows advertise [m] eligibility.
        monitors: TSV monitor layout injected through ISC_MONITOR_LIST.

    Returns:
        dict: "<id>.<field>" -> value pairs plus the rendered footer.
    """
    keystream = "".join(KEYS[k] for k in keys)
    eligible = "1" if monitor_eligible else "0"
    script = f"""
set -uo pipefail
export ISC_MONITOR_LIST=$'{monitors}'
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
CM_COMP_MONITOR_ELIGIBLE[$repo|alpha]={eligible}
CM_COMP_MONITOR_ELIGIBLE[$repo|beta]={eligible}
CM_COMP_MONITOR[$repo|alpha]=0
CM_COMP_MONITOR[$repo|beta]=2
cm_detect_monitors || true
printf 'monitor_count=%s\\n' "$CM_MONITOR_COUNT"
printf 'footer=%s\\n' "$(cm_submenu_footer "$repo" embedded)"
cm_single_submenu "$repo" >/dev/null 2>&1
for id in alpha beta; do
  printf '%s.monitor=%s\\n' "$id" "${{CM_COMP_MONITOR[$repo|$id]:-}}"
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


def test_detects_injected_monitor_layout():
    """cm_detect_monitors reads ISC_MONITOR_LIST and counts the monitors."""
    state = drive(["ENTER"])
    assert state["monitor_count"] == "2"


def test_m_cycles_monitor_assignment_and_wraps():
    """[m] steps 0 -> 1 -> 2 -> 0 so every monitor and "no pin" is reachable."""
    assert drive(["M", "ENTER"])["alpha.monitor"] == "1"
    assert drive(["M", "M", "ENTER"])["alpha.monitor"] == "2"
    assert drive(["M", "M", "M", "ENTER"])["alpha.monitor"] == "0"


def test_m_is_ignored_for_ineligible_component():
    """A component without [m] metadata keeps its monitor value untouched."""
    state = drive(["M", "ENTER"], monitor_eligible=False)
    assert state["alpha.monitor"] == "0"


def test_m_is_ignored_without_a_detected_multi_monitor_layout():
    """A single-monitor (or undetectable) layout offers nothing to cycle."""
    state = drive(["M", "ENTER"], monitors="1\\tDP-0\\tOnly Screen\\t1\\t0\\t0\\t1920\\t1080")
    assert state["alpha.monitor"] == "0"
    assert "[m] monitor" not in state["footer"]


def test_footer_advertises_the_action_on_a_multi_monitor_layout():
    """The [m] hint appears only when eligible rows and >1 monitor exist."""
    assert "[m] monitor" in drive(["ENTER"])["footer"]
    assert "[m] monitor" not in drive(["ENTER"], monitor_eligible=False)["footer"]


def test_uninstall_clears_the_monitor_pin():
    """[u] on an installed row clears its monitor assignment with the rest."""
    state = drive(["M", "U", "ENTER"])
    assert state["alpha.uninstall"] == "1"
    assert state["alpha.monitor"] == "0"


def main():
    """Run every test function in this module and report failures."""
    failures = 0
    for name, function in sorted(globals().items()):
        if not name.startswith("test_") or not callable(function):
            continue
        try:
            function()
            print(f"  PASS {name}")
        except AssertionError as error:
            failures += 1
            print(f"  FAIL {name}: {error}")
    if failures:
        raise SystemExit(f"{failures} test(s) failed")
    print("All monitor-action tests passed.")


if __name__ == "__main__":
    main()
