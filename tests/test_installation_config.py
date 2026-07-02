#!/usr/bin/env python3
"""Tests for installation_config.py and installation_config.sh helpers."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from installation_config import (
    apply_json,
    diff_documents,
    export_json,
    load_json_file,
    parse_state_file,
    save_json_file,
    write_state_file,
)


def test_roundtrip_standalone_state_file():
    """Standalone state should survive export -> apply -> export."""
    document = {
        "schema_version": 1,
        "scope": "standalone",
        "repo": "demo",
        "components": {
            "alpha": {"on": 1, "uninstall": 0, "config_value": "Super+A"},
            "beta": {"on": 0, "uninstall": 1},
        },
    }
    with tempfile.TemporaryDirectory() as directory:
        state = Path(directory) / "state.blob"
        applied = Path(directory) / "applied.blob"
        write_state_file(state, document)
        roundtrip = export_json(state)
        assert roundtrip["components"]["alpha"]["on"] == 1
        assert roundtrip["components"]["alpha"]["config_value"] == "Super+A"
        assert roundtrip["components"]["beta"]["on"] == 0
        assert roundtrip["components"]["beta"]["uninstall"] == 1
        apply_json(document, applied)
        again = export_json(applied)
        assert again["components"]["alpha"]["on"] == 1
        assert again["components"]["beta"]["uninstall"] == 1


def test_diff_detects_changed_field():
    """Diff must name a changed component selection field."""
    baseline = {
        "schema_version": 1,
        "scope": "standalone",
        "repo": "demo",
        "components": {"alpha": {"on": 1}},
    }
    current = {
        "schema_version": 1,
        "scope": "standalone",
        "repo": "demo",
        "components": {"alpha": {"on": 0}},
    }
    changes = diff_documents(baseline, current)
    assert any("alpha" in line and "selected" in line for line in changes)


def test_empty_and_default_fixtures(tmp_path: Path):
    """empty.json and default.json fixtures round-trip through the Python CLI."""
    empty = {
        "schema_version": 1,
        "scope": "standalone",
        "repo": "demo",
        "components": {},
    }
    default = {
        "schema_version": 1,
        "scope": "standalone",
        "repo": "demo",
        "components": {"alpha": {"on": 1, "uninstall": 0}},
    }
    empty_path = tmp_path / "empty.json"
    default_path = tmp_path / "default.json"
    save_json_file(empty_path, empty)
    save_json_file(default_path, default)
    assert load_json_file(empty_path)["components"] == {}
    assert load_json_file(default_path)["components"]["alpha"]["on"] == 1


def test_bash_apply_explicit_empty_zeros_unspecified():
    """empty.json with components:{} must zero every component selection."""
    harness = f"""
set -uo pipefail
source "{REPO}/component_menu.sh"
source "{REPO}/installation_config.sh"
declare -gA CM_REPO_LABEL CM_REPO_ENABLED CM_REPO_AWARE
declare -gA CM_COMP_IDS CM_COMP_LABEL CM_COMP_SECTION CM_COMP_REQUIRES CM_COMP_ON
declare -gA CM_COMP_INSTALLED CM_COMP_UNINSTALL
declare -gA CM_COMP_FAVORITE_ELIGIBLE CM_COMP_FAVORITE_ON CM_COMP_FAVORITE_DESKTOPS
declare -gA CM_COMP_STARTUP_ELIGIBLE CM_COMP_STARTUP_ON CM_COMP_STARTUP_SPECS
declare -gA CM_COMP_WORKSPACE_ELIGIBLE CM_COMP_WORKSPACE CM_COMP_WORKSPACE_SPECS
declare -gA CM_COMP_STICKY_ELIGIBLE CM_COMP_STICKY_ON CM_COMP_STICKY_SPECS
declare -gA CM_COMP_CONFIGURE_ELIGIBLE CM_COMP_CONFIG_VALUE
declare -ga CM_REPOS
repo="demo"
CM_REPOS=("$repo")
CM_REPO_ENABLED[$repo]=1
CM_COMP_IDS[$repo]="alpha beta"
CM_COMP_ON[$repo|alpha]=1
CM_COMP_ON[$repo|beta]=1
for id in alpha beta; do
  CM_COMP_UNINSTALL[$repo|$id]=0
  CM_COMP_FAVORITE_ON[$repo|$id]=0
  CM_COMP_STARTUP_ON[$repo|$id]=0
  CM_COMP_WORKSPACE[$repo|$id]=0
  CM_COMP_STICKY_ON[$repo|$id]=0
  CM_COMP_CONFIG_VALUE[$repo|$id]=""
done
isc_config_apply_json_file "$1"
on=0
for id in alpha beta; do
  [[ "${{CM_COMP_ON[$repo|$id]:-0}}" == "1" ]] && on=$((on+1))
done
printf "selected=%s" "$on"
"""
    empty = {
        "schema_version": 1,
        "scope": "standalone",
        "repo": "demo",
        "components": {},
    }
    with tempfile.TemporaryDirectory() as directory:
        cfg = Path(directory) / "empty.json"
        cfg.write_text(json.dumps(empty), encoding="utf-8")
        result = subprocess.run(
            ["bash", "-c", harness, "bash", str(cfg)],
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "selected=0" in result.stdout


def test_bash_apply_populated_default_preserves_entries():
    """Populated default.json must not zero components omitted from finalize."""
    harness = f"""
set -uo pipefail
source "{REPO}/component_menu.sh"
source "{REPO}/installation_config.sh"
declare -gA CM_REPO_LABEL CM_REPO_ENABLED CM_REPO_AWARE
declare -gA CM_COMP_IDS CM_COMP_LABEL CM_COMP_SECTION CM_COMP_REQUIRES CM_COMP_ON
declare -gA CM_COMP_INSTALLED CM_COMP_UNINSTALL
declare -gA CM_COMP_FAVORITE_ELIGIBLE CM_COMP_FAVORITE_ON CM_COMP_FAVORITE_DESKTOPS
declare -gA CM_COMP_STARTUP_ELIGIBLE CM_COMP_STARTUP_ON CM_COMP_STARTUP_SPECS
declare -gA CM_COMP_WORKSPACE_ELIGIBLE CM_COMP_WORKSPACE CM_COMP_WORKSPACE_SPECS
declare -gA CM_COMP_STICKY_ELIGIBLE CM_COMP_STICKY_ON CM_COMP_STICKY_SPECS
declare -gA CM_COMP_CONFIGURE_ELIGIBLE CM_COMP_CONFIG_VALUE
declare -ga CM_REPOS
repo="demo"
CM_REPOS=("$repo")
CM_REPO_ENABLED[$repo]=1
CM_COMP_IDS[$repo]="alpha beta"
CM_COMP_ON[$repo|alpha]=0
CM_COMP_ON[$repo|beta]=0
for id in alpha beta; do
  CM_COMP_UNINSTALL[$repo|$id]=0
  CM_COMP_FAVORITE_ON[$repo|$id]=0
  CM_COMP_STARTUP_ON[$repo|$id]=0
  CM_COMP_WORKSPACE[$repo|$id]=0
  CM_COMP_STICKY_ON[$repo|$id]=0
  CM_COMP_CONFIG_VALUE[$repo|$id]=""
done
isc_config_apply_json_file "$1"
printf "alpha=%s beta=%s" "${{CM_COMP_ON[$repo|alpha]:-0}}" "${{CM_COMP_ON[$repo|beta]:-0}}"
"""
    default = {
        "schema_version": 1,
        "scope": "standalone",
        "repo": "demo",
        "components": {"alpha": {"on": 1}, "beta": {"on": 1}},
    }
    with tempfile.TemporaryDirectory() as directory:
        cfg = Path(directory) / "default.json"
        cfg.write_text(json.dumps(default), encoding="utf-8")
        result = subprocess.run(
            ["bash", "-c", harness, "bash", str(cfg)],
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "alpha=1 beta=1" in result.stdout


def test_bash_apply_updates_cm_arrays():
    """installation_config.sh must apply explicit off entries from empty selections."""
    harness = f"""
set -uo pipefail
source "{REPO}/component_menu.sh"
source "{REPO}/installation_config.sh"
declare -gA CM_REPO_LABEL CM_REPO_ENABLED CM_REPO_AWARE
declare -gA CM_COMP_IDS CM_COMP_LABEL CM_COMP_SECTION CM_COMP_REQUIRES CM_COMP_ON
declare -gA CM_COMP_INSTALLED CM_COMP_UNINSTALL
declare -gA CM_COMP_FAVORITE_ELIGIBLE CM_COMP_FAVORITE_ON CM_COMP_FAVORITE_DESKTOPS
declare -gA CM_COMP_STARTUP_ELIGIBLE CM_COMP_STARTUP_ON CM_COMP_STARTUP_SPECS
declare -gA CM_COMP_WORKSPACE_ELIGIBLE CM_COMP_WORKSPACE CM_COMP_WORKSPACE_SPECS
declare -gA CM_COMP_STICKY_ELIGIBLE CM_COMP_STICKY_ON CM_COMP_STICKY_SPECS
declare -gA CM_COMP_CONFIGURE_ELIGIBLE CM_COMP_CONFIG_VALUE
declare -ga CM_REPOS
repo="demo"
CM_REPOS=("$repo")
CM_REPO_ENABLED[$repo]=1
CM_COMP_IDS[$repo]="alpha beta"
CM_COMP_ON[$repo|alpha]=1
CM_COMP_ON[$repo|beta]=1
for id in alpha beta; do
  CM_COMP_UNINSTALL[$repo|$id]=0
  CM_COMP_FAVORITE_ON[$repo|$id]=0
  CM_COMP_STARTUP_ON[$repo|$id]=0
  CM_COMP_WORKSPACE[$repo|$id]=0
  CM_COMP_STICKY_ON[$repo|$id]=0
  CM_COMP_CONFIG_VALUE[$repo|$id]=""
done
isc_config_apply_json_file "$1"
on=0
for id in alpha beta; do
  [[ "${{CM_COMP_ON[$repo|$id]:-0}}" == "1" ]] && on=$((on+1))
done
printf "selected=%s" "$on"
"""
    empty = {
        "schema_version": 1,
        "scope": "standalone",
        "repo": "demo",
        "components": {
            "alpha": {"on": 0},
            "beta": {"on": 0},
        },
    }
    with tempfile.TemporaryDirectory() as directory:
        cfg = Path(directory) / "empty.json"
        cfg.write_text(json.dumps(empty), encoding="utf-8")
        result = subprocess.run(
            ["bash", "-c", harness, "bash", str(cfg)],
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "selected=0" in result.stdout


def test_framework_default_fixture_is_populated():
    """Framework default.json must list every optional module default-on."""
    default = load_json_file(REPO / "installation_configs" / "default.json")
    empty = load_json_file(REPO / "installation_configs" / "empty.json")
    assert default["components"] != empty["components"]
    assert sum(1 for entry in default["components"].values() if entry.get("on")) >= 3


def test_component_main_export_selection_empty():
    """component_main --export-selection after empty.json apply reports no selections."""
    with tempfile.TemporaryDirectory() as directory:
        cfg_dir = Path(directory) / "installation_configs"
        cfg_dir.mkdir()
        (cfg_dir / "empty.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "scope": "standalone",
                    "repo": "demo",
                    "components": {},
                }
            ),
            encoding="utf-8",
        )
        harness = f"""
set -uo pipefail
source "{REPO}/component_menu.sh"
source "{REPO}/component_runtime.sh"
comp_a() {{ :; }}
comp_b() {{ :; }}
ISC_REPO_NAME="demo"
ISC_REPO_LABEL="Demo"
ISC_COMPONENTS=(
  "alpha|Alpha|on|comp_a"
  "beta|Beta|on|comp_b"
)
export SCRIPT_DIR="{directory}"
export ISC_CONFIG_REPO_ROOT="{directory}"
unset ISC_CONFIG_SKIP_APPLY
component_main --config empty.json --export-selection
"""
        result = subprocess.run(
            ["bash", "-c", harness],
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        exported = json.loads(result.stdout)
        selected = [
            cid
            for cid, entry in exported.get("components", {}).items()
            if entry.get("on")
        ]
        assert selected == []


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))