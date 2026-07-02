#!/usr/bin/env python3
"""Behavioral tests for this repository's own install.sh.

linux_installation_scripts_functions is the shared framework, and it ships a
component-based install.sh that deploys its files as installable modules. These
tests run install.sh against a throwaway ISC_INSTALL_DIR and assert:

  - the CORE (loader + logging) is always installed, even with no optional
    modules selected, so the framework core works no matter what;
  - the OPTIONAL modules are all default-on and individually selectable;
  - --list-components is side-effect free (the master installer parses it);
  - re-running is idempotent.

No system state outside the temporary directory changes.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from logging_utils import get_logger, log_call

INSTALL = REPO / "install.sh"

CORE_FILES = (
    "component_loader.sh",
    "component_logging.sh",
    "logging_utils.py",
    "safe_system_action.sh",
)
OPTIONAL_FILES = {
    "menu": "component_menu.sh",
    "runtime": "component_runtime.sh",
    "installer_helpers": "installer_helpers.sh",
}


def test_safe_system_action_contract_is_abortable_and_audible():
    """The destructive helper must retain its ten-second safety boundary."""
    content = (REPO / "safe_system_action.sh").read_text(encoding="utf-8")

    assert "for second in {10..1}" in content
    assert "INT TERM" in content
    assert "sounds/command.mp3" in content
    assert 'printf "0 %s\\n"' in content
    assert 'exec "${action_command[@]}"' in content


def test_loader_downloads_safe_system_action_for_standalone_installs():
    """Download fallback users need the same guarded action helper."""
    content = (REPO / "component_loader.sh").read_text(encoding="utf-8")

    assert "safe_system_action.sh" in content


def run_install(args, install_dir):
    """Run install.sh with args, deploying into install_dir. Returns (rc, out, err)."""
    env = dict(os.environ)
    env["ISC_INSTALL_DIR"] = str(install_dir)
    result = subprocess.run(
        ["bash", str(INSTALL), *args],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def test_install_sh_syntax_is_valid():
    """install.sh and its libraries must parse cleanly."""
    for rel in (
        "install.sh",
        "lib/framework_install.sh",
        "installer/components.sh",
        "safe_system_action.sh",
    ):
        result = subprocess.run(
            ["bash", "-n", str(REPO / rel)], capture_output=True, text=True
        )
        assert result.returncode == 0, f"{rel}: {result.stderr}"


def test_list_components_lists_optional_modules_default_on():
    """--list-components prints exactly the optional modules, all default-on."""
    with tempfile.TemporaryDirectory() as tmp:
        install_dir = Path(tmp) / "components"
        rc, out, err = run_install(["--list-components"], install_dir)
        assert rc == 0, err
        lines = [ln for ln in out.splitlines() if ln.strip()]
        assert lines == [
            "menu\tInteractive selection menu engine (component_menu.sh)\ton",
            "runtime\tPer-repository installer runtime contract (component_runtime.sh)\ton",
            "installer_helpers\tShared install-time helpers + hotkey-capture engine\ton",
        ], out
        # Listing must be side-effect free: nothing deployed.
        assert not install_dir.exists(), "listing must not create the install dir"


def test_core_installed_even_with_no_optional_modules():
    """The core deploys even when the optional selection is empty."""
    with tempfile.TemporaryDirectory() as tmp:
        install_dir = Path(tmp) / "components"
        rc, out, err = run_install(["--select", ""], install_dir)
        assert rc == 0, err
        for name in CORE_FILES:
            assert (install_dir / name).is_file(), f"core file missing: {name}\n{out}"
        # No optional module should have been deployed.
        for name in OPTIONAL_FILES.values():
            assert not (install_dir / name).exists(), f"unexpected optional file: {name}"


def test_default_installs_core_plus_all_optional_modules():
    """--default deploys the core and every default-on optional module."""
    with tempfile.TemporaryDirectory() as tmp:
        install_dir = Path(tmp) / "components"
        rc, out, err = run_install(["--default"], install_dir)
        assert rc == 0, err
        for name in (*CORE_FILES, *OPTIONAL_FILES.values()):
            assert (install_dir / name).is_file(), f"missing after --default: {name}\n{out}"
        # The installer_helpers module also ships the shared hotkey-capture engine
        # so configurable hotkeys work on the download-cache path (no checkout).
        for name in ("hotkey_capture.sh", "hotkey_capture.py", "repeatable_fields.py"):
            assert (install_dir / name).is_file(), f"missing after --default: {name}\n{out}"


def test_select_single_module_installs_core_plus_only_that_module():
    """--select menu deploys the core plus only the menu module."""
    with tempfile.TemporaryDirectory() as tmp:
        install_dir = Path(tmp) / "components"
        rc, out, err = run_install(["--select", "menu"], install_dir)
        assert rc == 0, err
        for name in CORE_FILES:
            assert (install_dir / name).is_file(), f"core missing: {name}"
        assert (install_dir / OPTIONAL_FILES["menu"]).is_file(), out
        assert not (install_dir / OPTIONAL_FILES["runtime"]).exists(), out
        assert not (install_dir / OPTIONAL_FILES["installer_helpers"]).exists(), out


def test_install_is_idempotent():
    """Running --default twice succeeds and leaves identical content."""
    with tempfile.TemporaryDirectory() as tmp:
        install_dir = Path(tmp) / "components"
        rc1, _, err1 = run_install(["--default"], install_dir)
        assert rc1 == 0, err1
        first = {p.name: p.read_text() for p in install_dir.iterdir()}
        rc2, _, err2 = run_install(["--default"], install_dir)
        assert rc2 == 0, err2
        second = {p.name: p.read_text() for p in install_dir.iterdir()}
        assert first == second, "second run changed deployed content"


def test_installed_framework_matches_source():
    """Deployed files are byte-identical copies of the repository sources."""
    with tempfile.TemporaryDirectory() as tmp:
        install_dir = Path(tmp) / "components"
        rc, _, err = run_install(["--all"], install_dir)
        assert rc == 0, err
        deployed = (*CORE_FILES, *OPTIONAL_FILES.values(), "installation_config.sh", "installation_config.py")
        for name in deployed:
            assert (install_dir / name).read_text() == (REPO / name).read_text(), name


def test_deployed_cache_resolves_without_a_checkout():
    """A consuming loader resolves the framework from the installed cache alone."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        install_dir = base / "cache" / "installation_scripts" / "components"
        rc, _, err = run_install(["--default"], install_dir)
        assert rc == 0, err
        # Point a consumer with no sibling checkout at the populated cache via
        # XDG_CACHE_HOME, and confirm the loader activates the runtime from it.
        consumer = base / "consumer"
        consumer.mkdir()
        script = f"""
set -uo pipefail
SCRIPT_DIR="{consumer}"
source "{install_dir}/component_loader.sh"
isc_activate_components
declare -F component_main >/dev/null && echo "runtime:ok"
echo "libdir:$ISC_COMPONENT_LIB_DIR"
"""
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=consumer,
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": str(base / "nohome"),
                "XDG_CACHE_HOME": str(base / "cache"),
            },
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "runtime:ok" in result.stdout, result.stdout
        assert str(install_dir) in result.stdout, result.stdout


@log_call(get_logger("install-tests", "install_tests.log"))
def _selfcheck():
    """Trace marker so the install suite exercises the shared logging helper."""
    return "ok"


if __name__ == "__main__":
    _selfcheck()
    tests = [v for n, v in globals().items() if n.startswith("test_") and callable(v)]
    failures = 0
    for test in sorted(tests, key=lambda item: item.__name__):
        try:
            test()
            print(f"PASS: {test.__doc__}")
        except Exception as error:  # noqa: BLE001
            failures += 1
            print(f"FAIL: {test.__doc__} - {error}")
    raise SystemExit(failures)
