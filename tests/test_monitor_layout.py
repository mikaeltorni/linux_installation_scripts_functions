#!/usr/bin/env python3
"""Unit tests for monitor_layout.py (Mutter DisplayConfig -> monitor rows).

Drives the pure parsing function with a synthetic GetCurrentState payload, so
the numbering contract ("monitor N is the Nth entry of the DisplayConfig
monitors array, exactly like the GNOME Displays panel") is locked without a
live session bus. Also covers the bash wrapper's ISC_MONITOR_LIST override.
"""

import importlib.util
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("monitor_layout", REPO / "monitor_layout.py")
monitor_layout = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor_layout)


def mode(mode_id, width, height, current=False):
    """Build one DisplayConfig mode tuple.

    Args:
        mode_id: Mode identifier string.
        width: Physical mode width in pixels.
        height: Physical mode height in pixels.
        current: Whether this is the monitor's current mode.

    Returns:
        tuple: (id, width, height, refresh, preferred-scale, scales, props).
    """
    props = {"is-current": True} if current else {}
    return (mode_id, width, height, 60.0, 1.0, [1.0, 2.0], props)


def state(transform=0, scale=1.0):
    """Build a two-monitor GetCurrentState payload (DP-0 left, HDMI-0 right).

    Args:
        transform: Mutter transform applied to the second monitor.
        scale: Logical scale applied to the second monitor.

    Returns:
        tuple: (serial, monitors, logical_monitors, properties).
    """
    monitors = [
        (("DP-0", "GSM", "LG", "s1"), [mode("a", 3840, 2160, current=True)], {"display-name": "Left"}),
        (("HDMI-0", "SAM", "SAM", "s2"), [mode("b", 3840, 2160, current=True)], {"display-name": "Right"}),
    ]
    logical = [
        (0, 0, 1.0, 0, False, [("DP-0", "GSM", "LG", "s1")], {}),
        (3840, 100, scale, transform, True, [("HDMI-0", "SAM", "SAM", "s2")], {}),
    ]
    return (1, monitors, logical, {})


def test_numbering_follows_the_display_config_order():
    """Monitor numbers are 1-based positions in the DisplayConfig monitors list."""
    rows = monitor_layout.monitors_from_state(state())
    assert [row["number"] for row in rows] == [1, 2]
    assert [row["connector"] for row in rows] == ["DP-0", "HDMI-0"]
    assert [row["name"] for row in rows] == ["Left", "Right"]


def test_primary_flag_comes_from_the_logical_monitor():
    """Exactly the logical monitor marked primary is reported as primary."""
    rows = monitor_layout.monitors_from_state(state())
    assert rows[0]["primary"] == 0
    assert rows[1]["primary"] == 1


def test_geometry_uses_logical_position_and_size():
    """Geometry matches Meta.Display.get_monitor_geometry (logical coordinates)."""
    rows = monitor_layout.monitors_from_state(state())
    assert (rows[0]["x"], rows[0]["y"], rows[0]["width"], rows[0]["height"]) == (0, 0, 3840, 2160)
    assert (rows[1]["x"], rows[1]["y"]) == (3840, 100)


def test_rotated_monitor_swaps_width_and_height():
    """A 90-degree rotated panel reports its on-screen (portrait) extent."""
    rows = monitor_layout.monitors_from_state(state(transform=1))
    assert (rows[1]["width"], rows[1]["height"]) == (2160, 3840)


def test_scaled_monitor_reports_logical_size():
    """A scaled monitor reports mode size divided by the scale factor."""
    rows = monitor_layout.monitors_from_state(state(scale=2.0))
    assert (rows[1]["width"], rows[1]["height"]) == (1920, 1080)


def test_bash_wrapper_honors_the_injected_layout():
    """isc_list_monitors returns ISC_MONITOR_LIST verbatim without DBus."""
    injected = "1\tDP-9\tInjected\t1\t0\t0\t800\t600"
    result = subprocess.run(
        ["bash", "-c", f'source "{REPO}/monitor_layout.sh"; isc_monitor_count; isc_monitor_label 1'],
        env={"PATH": "/usr/bin:/bin", "ISC_MONITOR_LIST": injected},
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.splitlines() == ["1", "1: DP-9 (Injected) [primary]"]


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
    print("All monitor-layout tests passed.")


if __name__ == "__main__":
    main()
