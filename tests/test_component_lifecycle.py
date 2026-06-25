#!/usr/bin/env python3
"""Behavioral tests for the install-state lifecycle in component_runtime.sh.

Covers the receipts/detect/uninstall/reconfigure contract added on top of the
base install runtime:

  * a successful install writes a per-component receipt;
  * --detect reports installed/absent using the receipt or an optional detect
    function (manifest field 4);
  * --uninstall runs the optional uninstall function (field 5) and clears the
    receipt, and only clears the receipt when no uninstall function exists;
  * --reconfigure re-runs install functions (idempotent re-apply).

Everything runs in isolated Bash subprocesses with a synthetic manifest and a
temporary receipt directory (ISC_RECEIPT_DIR), so no installer runs and no real
system or user state changes.
"""

import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def harness(receipt_dir: Path) -> str:
    """A synthetic component installer whose effects are observable in files.

    comp_* install functions append to $WORK/log. uninstall_* functions append
    too. gamma carries a detect function backed by $WORK/gamma_present so a test
    can flip live system state independently of receipts.
    """
    return f"""
set -uo pipefail
export ISC_RECEIPT_DIR="{receipt_dir}"
export WORK="{receipt_dir.parent}"
source "{REPO}/component_runtime.sh"
comp_a() {{ echo "install:a" >>"$WORK/log"; }}
comp_b() {{ echo "install:b" >>"$WORK/log"; }}
comp_c() {{ echo "install:c" >>"$WORK/log"; }}
un_a()   {{ echo "uninstall:a" >>"$WORK/log"; }}
un_b()   {{ echo "uninstall:b" >>"$WORK/log"; }}
detect_c() {{ [[ -f "$WORK/gamma_present" ]]; }}
ISC_REPO_NAME="demo"
ISC_REPO_LABEL="Demo"
ISC_COMPONENTS=(
  "alpha|Alpha|on|comp_a||un_a"
  "beta|Beta|on|comp_b||un_b"
  "gamma|Gamma|off|comp_c|detect_c"
)
component_main "$@"
"""


def run(receipt_dir: Path, args):
    """Run the harness installer with args; return (rc, stdout)."""
    result = subprocess.run(
        ["bash", "-c", harness(receipt_dir), "bash", *args],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout


def detect_map(receipt_dir: Path) -> dict[str, str]:
    """Return {id: installed|absent} parsed from --detect output."""
    rc, out = run(receipt_dir, ["--detect"])
    assert rc == 0, out
    return dict(
        line.split("\t", 1) for line in out.splitlines() if "\t" in line
    )


def test_install_writes_receipts(tmp_path):
    """--default installs default-on components and writes their receipts."""
    rd = tmp_path / "receipts"
    rc, _ = run(rd, ["--default"])
    assert rc == 0
    assert (rd / "demo" / "alpha").is_file()
    assert (rd / "demo" / "beta").is_file()
    assert not (rd / "demo" / "gamma").exists()


def test_detect_reports_receipt_state(tmp_path):
    """--detect reports absent before install and installed after."""
    rd = tmp_path / "receipts"
    before = detect_map(rd)
    assert before == {"alpha": "absent", "beta": "absent", "gamma": "absent"}
    run(rd, ["--select", "alpha"])
    after = detect_map(rd)
    assert after["alpha"] == "installed"
    assert after["beta"] == "absent"


def test_detect_prefers_detect_function(tmp_path):
    """A component with a detect function reflects live state, not the receipt."""
    rd = tmp_path / "receipts"
    # gamma has detect_c backed by $WORK/gamma_present; no receipt yet.
    assert detect_map(rd)["gamma"] == "absent"
    (tmp_path / "gamma_present").write_text("x")
    assert detect_map(rd)["gamma"] == "installed"


def test_uninstall_runs_function_and_clears_receipt(tmp_path):
    """--uninstall runs the uninstall function and removes the receipt."""
    rd = tmp_path / "receipts"
    run(rd, ["--select", "alpha,beta"])
    rc, out = run(rd, ["--uninstall", "alpha"])
    assert rc == 0, out
    assert "uninstall:a" in (tmp_path / "log").read_text()
    assert not (rd / "demo" / "alpha").exists()
    assert (rd / "demo" / "beta").is_file()


def test_uninstall_reverse_order(tmp_path):
    """Uninstall processes components in reverse manifest order."""
    rd = tmp_path / "receipts"
    run(rd, ["--all"])
    (tmp_path / "log").write_text("")
    run(rd, ["--uninstall", "alpha,beta"])
    lines = [ln for ln in (tmp_path / "log").read_text().splitlines() if ln]
    assert lines == ["uninstall:b", "uninstall:a"], lines


def test_reconfigure_reruns_install(tmp_path):
    """--reconfigure re-runs the install function for the given ids."""
    rd = tmp_path / "receipts"
    run(rd, ["--select", "alpha"])
    (tmp_path / "log").write_text("")
    rc, _ = run(rd, ["--reconfigure", "alpha"])
    assert rc == 0
    assert (tmp_path / "log").read_text().strip() == "install:a"


if __name__ == "__main__":
    tests = [v for n, v in sorted(globals().items()) if n.startswith("test_") and callable(v)]
    failures = 0
    for test in tests:
        with tempfile.TemporaryDirectory() as td:
            try:
                test(Path(td))
                print(f"PASS: {test.__name__}")
            except Exception as error:  # noqa: BLE001
                failures += 1
                print(f"FAIL: {test.__name__} - {error}")
    raise SystemExit(failures)
