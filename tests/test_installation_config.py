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


def test_monitor_field_survives_roundtrip():
    """A [m] monitor pin must survive export -> apply -> export unchanged."""
    document = {
        "schema_version": 1,
        "scope": "standalone",
        "repo": "demo",
        "components": {
            "alpha": {"on": 1, "monitor": 2, "config_value": "Super+A"},
            "beta": {"on": 1, "monitor": 0},
        },
    }
    with tempfile.TemporaryDirectory() as directory:
        state = Path(directory) / "state.blob"
        write_state_file(state, document)
        roundtrip = export_json(state)
        assert roundtrip["components"]["alpha"]["monitor"] == 2
        # The config value must not shift into the monitor column.
        assert roundtrip["components"]["alpha"]["config_value"] == "Super+A"
        assert roundtrip["components"]["beta"]["monitor"] == 0


def test_legacy_document_without_monitor_stays_unpinned_in_state():
    """Documents predating [m] must not force a monitor number on apply.

    The state row keeps an empty monitor column, which installation_config.sh
    translates into "leave the repository's own default alone" instead of
    resetting Spotify/Discord to unpinned.
    """
    document = {
        "schema_version": 1,
        "scope": "standalone",
        "repo": "demo",
        "components": {"alpha": {"on": 1, "config_value": "Super+A"}},
    }
    with tempfile.TemporaryDirectory() as directory:
        state = Path(directory) / "state.blob"
        write_state_file(state, document)
        row = [
            line
            for line in state.read_text(encoding="utf-8").splitlines()
            if line.startswith("comp\t")
        ][0]
        fields = row.split("\t")
        assert fields[9] == ""
        assert fields[10] == "Super+A"
        assert "monitor" not in export_json(state)["components"]["alpha"]


def test_diff_reports_monitor_change():
    """Diff output must name a changed monitor assignment."""
    baseline = {
        "schema_version": 1,
        "scope": "standalone",
        "repo": "demo",
        "components": {"alpha": {"on": 1, "monitor": 1}},
    }
    current = {
        "schema_version": 1,
        "scope": "standalone",
        "repo": "demo",
        "components": {"alpha": {"on": 1, "monitor": 2}},
    }
    changes = diff_documents(baseline, current)
    assert any("monitor: 1 -> 2" in change for change in changes)


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


def test_bootstrap_manifest_skips_config_apply():
    """manifest mode must leave CM_* unchanged even when default.json would disable all."""
    fixture = REPO / "tests" / "fixtures" / "minimal_standalone_bootstrap.sh"
    with tempfile.TemporaryDirectory() as directory:
        cfg_dir = Path(directory) / "installation_configs"
        cfg_dir.mkdir()
        (cfg_dir / "default.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "scope": "standalone",
                    "repo": "demo",
                    "components": {"alpha": {"on": 0}, "beta": {"on": 0}},
                }
            ),
            encoding="utf-8",
        )
        harness = f"""
set -uo pipefail
export SCRIPT_DIR="{directory}"
export ISC_CONFIG_REPO_ROOT="{directory}"
export ISC_REPO_NAME=demo
source "{fixture}"
isc_bootstrap_selection manifest
isc_config_export_json standalone demo /dev/stdout
"""
        result = subprocess.run(
            ["bash", "-c", harness],
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr or result.stdout
        exported = json.loads(result.stdout)
        assert exported["components"]["alpha"]["on"] == 1
        assert exported["components"]["beta"]["on"] == 0


def test_bootstrap_config_export_applies_named_config():
    """config_export mode must apply empty.json and zero every component selection."""
    fixture = REPO / "tests" / "fixtures" / "minimal_standalone_bootstrap.sh"
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
export SCRIPT_DIR="{directory}"
export ISC_CONFIG_REPO_ROOT="{directory}"
export ISC_CONFIG_NAME=empty.json
export ISC_REPO_NAME=demo
source "{fixture}"
isc_bootstrap_selection config_export
isc_config_export_json standalone demo /dev/stdout
"""
        result = subprocess.run(
            ["bash", "-c", harness],
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr or result.stdout
        exported = json.loads(result.stdout)
        selected = [
            cid
            for cid, entry in exported.get("components", {}).items()
            if entry.get("on")
        ]
        assert selected == []


def test_bootstrap_config_active_applies_default_json():
    """config_active mode must apply default.json after loading baseline."""
    fixture = REPO / "tests" / "fixtures" / "minimal_standalone_bootstrap.sh"
    with tempfile.TemporaryDirectory() as directory:
        cfg_dir = Path(directory) / "installation_configs"
        cfg_dir.mkdir()
        (cfg_dir / "default.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "scope": "standalone",
                    "repo": "demo",
                    "components": {"alpha": {"on": 0}, "beta": {"on": 1}},
                }
            ),
            encoding="utf-8",
        )
        harness = f"""
set -uo pipefail
export SCRIPT_DIR="{directory}"
export ISC_CONFIG_REPO_ROOT="{directory}"
export ISC_CONFIG_NAME=default.json
export ISC_REPO_NAME=demo
source "{fixture}"
isc_bootstrap_selection config_active
printf "alpha=%s beta=%s" "${{CM_COMP_ON[demo|alpha]:-0}}" "${{CM_COMP_ON[demo|beta]:-0}}"
"""
        result = subprocess.run(
            ["bash", "-c", harness],
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr or result.stdout
        assert "alpha=0 beta=1" in result.stdout


def test_config_apply_does_not_mark_installed_components_for_reconfigure():
    """Config `on` describes desired presence, not a pending reconfigure action."""
    fixture = REPO / "tests" / "fixtures" / "minimal_standalone_bootstrap.sh"
    with tempfile.TemporaryDirectory() as directory:
        state = Path(directory) / "state"
        state.write_text(
            "scope=standalone\n"
            "repo_name=demo\n"
            "comp\tdemo\talpha\t1\t0\t0\t0\t0\t0\t\n",
            encoding="utf-8",
        )
        harness = f'''
set -uo pipefail
export ISC_REPO_NAME=demo
source "{fixture}"
CM_COMP_INSTALLED[demo|alpha]=1
CM_COMP_ON[demo|alpha]=0
isc_config_apply_state_file "{state}"
printf 'alpha=%s' "${{CM_COMP_ON[demo|alpha]:-missing}}"
'''
        result = subprocess.run(
            ["bash", "-c", harness],
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr or result.stdout
        assert "alpha=0" in result.stdout


def test_config_export_records_unchanged_installed_component_as_enabled():
    """Ephemeral menu state must serialize installed presence as `on: 1`."""
    fixture = REPO / "tests" / "fixtures" / "minimal_standalone_bootstrap.sh"
    harness = f'''
set -uo pipefail
export ISC_REPO_NAME=demo
source "{fixture}"
CM_COMP_IDS[demo]=alpha
CM_COMP_INSTALLED[demo|alpha]=1
CM_COMP_ON[demo|alpha]=0
CM_COMP_UNINSTALL[demo|alpha]=0
isc_config_serialize_standalone demo /dev/stdout
'''
    result = subprocess.run(
        ["bash", "-c", harness], cwd=REPO, check=False, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "comp\tdemo\talpha\t1\t0" in result.stdout


def test_config_apply_preserves_live_component_config_value():
    """Persisted selection metadata must not replace repository-reported live state."""
    fixture = REPO / "tests" / "fixtures" / "minimal_standalone_bootstrap.sh"
    with tempfile.TemporaryDirectory() as directory:
        state = Path(directory) / "state"
        state.write_text(
            "scope=standalone\n"
            "repo_name=demo\n"
            "comp\tdemo\talpha\t1\t0\t0\t0\t0\t0\t500 ms\n",
            encoding="utf-8",
        )
        harness = f'''
set -uo pipefail
export ISC_REPO_NAME=demo
source "{fixture}"
CM_COMP_CONFIG_VALUE[demo|alpha]='200 ms'
isc_config_apply_state_file "{state}"
printf 'value=%s' "${{CM_COMP_CONFIG_VALUE[demo|alpha]:-missing}}"
'''
        result = subprocess.run(
            ["bash", "-c", harness], cwd=REPO, check=False, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr or result.stdout
        assert "value=200 ms" in result.stdout


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
