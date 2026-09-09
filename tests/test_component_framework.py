#!/usr/bin/env python3
"""Behavioral tests for the shared installer component framework.

Exercises component_runtime.sh (the per-repository --list-components / --select
/ --default contract), component_menu.sh (count helpers), and
component_loader.sh (library resolution + activation) entirely through isolated
Bash subprocesses with a synthetic manifest. No installers run and no system
state changes.
"""

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from logging_utils import get_logger, log_call

HARNESS = f"""
set -uo pipefail
source "{REPO}/component_runtime.sh"
comp_a() {{ echo "ran:a"; }}
comp_b() {{ echo "ran:b"; }}
comp_c() {{ echo "ran:c"; }}
configure_alpha() {{ echo "configured:alpha"; }}
status_alpha() {{ echo "Super+W"; }}
pre() {{ echo "preflight"; }}
post() {{ echo "postflight"; }}
ISC_REPO_NAME="demo"
ISC_REPO_LABEL="Demo"
ISC_PREFLIGHT="pre"
ISC_POSTFLIGHT="post"
ISC_COMPONENTS=(
  "alpha|Alpha|on|comp_a"
  "beta|Beta|on|comp_b"
  "gamma|Gamma|off|comp_c"
)
component_main "$@"
"""


def run(args):
    """Run the harness installer with args and return (rc, stdout)."""
    result = subprocess.run(
        ["bash", "-c", HARNESS, "bash", *args],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout


def test_framework_files_exist():
    """The framework files should exist in the repository root."""
    for name in (
        "component_menu.sh",
        "component_runtime.sh",
        "component_loader.sh",
        "component_logging.sh",
        "installer_helpers.sh",
    ):
        assert (REPO / name).is_file(), f"missing {name}"


def test_lib_dir_resolves_from_the_loaders_own_location():
    """A sourced loader must find its siblings without SCRIPT_DIR or ~/projects.

    Consumer repos source ``component_loader.sh`` by absolute path after finding
    it themselves. Those that name their root something other than ``SCRIPT_DIR``
    (and any checkout living outside ``~/projects``, including root/sudo runs
    where ``$HOME`` changes) previously fell through to the network. The loader
    knows where it lives, so that location is the authoritative candidate.
    """
    with tempfile.TemporaryDirectory() as directory:
        tmp_path = Path(directory)
        result = subprocess.run(
            ["bash", "-c", f'source "{REPO / "component_loader.sh"}"; isc_component_lib_dir'],
            env={
                **{k: v for k, v in os.environ.items()
                   if k not in ("ISC_FUNCTIONS_DIR", "ISC_COMPONENT_LIB_DIR", "SCRIPT_DIR")},
                "HOME": str(tmp_path / "scratch-home"),
                "XDG_CACHE_HOME": str(tmp_path / "cache"),
                # No network fallback is reachable, so any miss fails loudly.
                "ISC_FUNCTIONS_RAW": f"file://{tmp_path / 'nonexistent'}",
            },
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stderr
        assert Path(result.stdout.strip()) == REPO


def test_download_fallback_includes_repeatable_fields():
    """A lone consumer checkout must receive the Python nested-row helper."""
    with tempfile.TemporaryDirectory() as directory:
        tmp_path = Path(directory)
        raw = tmp_path / "raw"
        raw.mkdir()
        for name in (
                "component_logging.sh", "installer_helpers.sh", "safe_system_action.sh",
                "repeatable_fields.py", "installation_config.py", "installation_config.sh",
            "component_menu.sh", "component_runtime.sh",
        ):
            raw.joinpath(name).write_bytes(REPO.joinpath(name).read_bytes())
        home = tmp_path / "home"
        result = subprocess.run(
            ["bash", "-c", f'source "{REPO / "component_loader.sh"}"; isc_load_helpers; printf "%s" "$ISC_REPEATABLE_FIELDS_PY"'],
            env={**os.environ, "HOME": str(home), "XDG_CACHE_HOME": str(tmp_path / "cache"),
                 "ISC_FUNCTIONS_RAW": f"file://{raw}", "SCRIPT_DIR": str(tmp_path / "consumer")},
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stderr
        assert Path(result.stdout).is_file()
        assert Path(result.stdout).name == "repeatable_fields.py"


def test_list_components_format():
    """--list-components should print id<TAB>label<TAB>default per component."""
    rc, out = run(["--list-components"])
    assert rc == 0, out
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert lines == ["alpha\tAlpha\ton", "beta\tBeta\ton", "gamma\tGamma\toff"], out


def test_list_components_includes_optional_section_metadata():
    """A seventh manifest field should expose a fourth section column."""
    section_harness = HARNESS.replace(
        '"alpha|Alpha|on|comp_a"', '"alpha|Alpha|on|comp_a|||Models"'
    )
    result = subprocess.run(
        ["bash", "-c", section_harness, "bash", "--list-components"],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "alpha\tAlpha\ton\tModels"


def test_list_components_includes_optional_requirement_metadata():
    """An eighth manifest field should expose required component ids."""
    dependency_harness = HARNESS.replace(
        '"beta|Beta|on|comp_b"', '"beta|Beta|on|comp_b|||Agent tools|alpha"'
    )
    result = subprocess.run(
        ["bash", "-c", dependency_harness, "bash", "--list-components"],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[1] == "beta\tBeta\ton\tAgent tools\talpha"


def test_list_components_preserves_empty_section_before_requirement():
    """Requirement metadata must retain an empty fourth section column."""
    dependency_harness = HARNESS.replace(
        '"beta|Beta|on|comp_b"', '"beta|Beta|on|comp_b||||alpha"'
    )
    result = subprocess.run(
        ["bash", "-c", dependency_harness, "bash", "--list-components"],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[1] == "beta\tBeta\ton\t\talpha"


def test_manifest_configurator_is_discoverable_and_invokable():
    """A ninth manifest field should expose a repository-owned nested screen."""
    configurable = HARNESS.replace(
        '"alpha|Alpha|on|comp_a"',
        '"alpha|Alpha|on|comp_a|||||configure_alpha"',
    )
    listed = subprocess.run(
        ["bash", "-c", configurable, "bash", "--list-configurable-components"],
        cwd=REPO, check=False, capture_output=True, text=True,
    )
    invoked = subprocess.run(
        ["bash", "-c", configurable, "bash", "--configure-component", "alpha"],
        cwd=REPO, check=False, capture_output=True, text=True,
    )
    assert listed.returncode == 0 and listed.stdout.splitlines() == ["alpha"]
    assert invoked.returncode == 0 and "configured:alpha" in invoked.stdout
    components = subprocess.run(
        ["bash", "-c", configurable, "bash", "--list-components"],
        cwd=REPO, check=False, capture_output=True, text=True,
    )
    assert components.stdout.splitlines()[0] == "alpha\tAlpha\ton"


def test_manifest_config_status_is_discoverable():
    """A tenth manifest field should expose the current editable value."""
    configurable = HARNESS.replace(
        '"alpha|Alpha|on|comp_a"',
        '"alpha|Alpha|on|comp_a|||||configure_alpha|status_alpha"',
    )
    listed = subprocess.run(
        ["bash", "-c", configurable, "bash", "--list-component-config-values"],
        cwd=REPO, check=False, capture_output=True, text=True,
    )
    assert listed.returncode == 0
    assert listed.stdout.splitlines() == ["alpha\tSuper+W"]


def test_select_rejects_dependency_without_selected_or_installed_requirement():
    """Direct --select calls must enforce the same dependency as the menu."""
    dependency_harness = HARNESS.replace(
        '"beta|Beta|on|comp_b"', '"beta|Beta|on|comp_b|||Agent tools|alpha"'
    )
    with tempfile.TemporaryDirectory() as receipt_dir:
        result = subprocess.run(
            ["bash", "-c", dependency_harness, "bash", "--select", "beta"],
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "ISC_RECEIPT_DIR": receipt_dir},
        )

    assert result.returncode != 0
    assert "requires component 'alpha'" in result.stdout
    assert "ran:b" not in result.stdout


def test_select_accepts_dependency_selected_in_same_run():
    """A dependent may run when its requirement is selected in the same run."""
    dependency_harness = HARNESS.replace(
        '"beta|Beta|on|comp_b"', '"beta|Beta|on|comp_b|||Agent tools|alpha"'
    )
    result = subprocess.run(
        ["bash", "-c", dependency_harness, "bash", "--select", "alpha,beta"],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout
    assert "ran:a" in result.stdout and "ran:b" in result.stdout


def test_failed_requirement_prevents_dependent_execution():
    """Selecting a prerequisite is insufficient when its install function fails."""
    dependency_harness = HARNESS.replace(
        'comp_a() { echo "ran:a"; }', 'comp_a() { echo "failed:a"; return 1; }'
    ).replace(
        '"beta|Beta|on|comp_b"', '"beta|Beta|on|comp_b|||Agent tools|alpha"'
    )
    with tempfile.TemporaryDirectory() as receipt_dir:
        result = subprocess.run(
            ["bash", "-c", dependency_harness, "bash", "--select", "alpha,beta"],
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "ISC_RECEIPT_DIR": receipt_dir},
        )

    assert result.returncode != 0
    assert "failed:a" in result.stdout
    assert "ran:b" not in result.stdout


def test_default_runs_only_default_on():
    """--default should run default-on components and skip default-off ones."""
    rc, out = run(["--default"])
    assert rc == 0, out
    assert "ran:a" in out and "ran:b" in out and "ran:c" not in out


def test_all_runs_every_component():
    """--all should run every component including default-off ones."""
    rc, out = run(["--all"])
    assert rc == 0, out
    assert "ran:a" in out and "ran:b" in out and "ran:c" in out


def test_select_runs_exact_subset_in_manifest_order():
    """--select should run exactly the requested ids in manifest order."""
    rc, out = run(["--select", "gamma,alpha"])
    assert rc == 0, out
    order = [ln.split(":")[1] for ln in out.splitlines() if ln.startswith("ran:")]
    assert order == ["a", "c"], out


def test_preflight_and_postflight_run_once():
    """Preflight runs before and postflight after the selected components."""
    rc, out = run(["--select", "alpha"])
    assert rc == 0, out
    assert out.count("preflight") == 1 and out.count("postflight") == 1
    assert out.index("preflight") < out.index("ran:a") < out.index("postflight")


def test_no_match_is_a_noop():
    """An unmatched selection runs nothing, including the preflight."""
    rc, out = run(["--select", "nonexistent"])
    assert rc == 0, out
    assert "preflight" not in out and "postflight" not in out


def test_count_helpers():
    """The menu should report enabled/total counts like the '5/8' indicator."""
    script = f"""
set -uo pipefail
source "{REPO}/component_menu.sh"
CM_COMP_IDS[r]="x1 x2 x3 x4"
CM_COMP_ON["r|x1"]=1; CM_COMP_ON["r|x2"]=0; CM_COMP_ON["r|x3"]=1; CM_COMP_ON["r|x4"]=0
printf '%s/%s\\n' "$(cm_repo_on_count r)" "$(cm_repo_total_count r)"
"""
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "2/4"


def test_logging_writes_leveled_lines_to_log_dir():
    """isc_log should write timestamped, leveled, tagged lines into ISC_LOG_DIR."""
    with tempfile.TemporaryDirectory() as tmp:
        logdir = Path(tmp) / ".log"
        script = f"""
set -uo pipefail
export ISC_LOG_DIR="{logdir}"
export ISC_LOG_TAG="demo"
source "{REPO}/component_logging.sh"
isc_log_info "hello world"
isc_log_error "boom happened"
printf 'file:%s\\n' "$(isc_log_file)"
"""
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        log_file = logdir / "installer_components.log"
        assert log_file.is_file(), result.stdout
        text = log_file.read_text()
        assert "[INFO" in text and "hello world" in text
        assert "[ERROR" in text and "boom happened" in text
        assert "[demo]" in text


def test_logging_respects_level_threshold():
    """Messages below ISC_LOG_LEVEL should be dropped, higher ones recorded."""
    with tempfile.TemporaryDirectory() as tmp:
        logdir = Path(tmp) / ".log"
        script = f"""
set -uo pipefail
export ISC_LOG_DIR="{logdir}"
export ISC_LOG_LEVEL="warn"
source "{REPO}/component_logging.sh"
isc_log_debug "should-not-appear"
isc_log_warn "should-appear"
"""
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        text = (logdir / "installer_components.log").read_text()
        assert "should-appear" in text
        assert "should-not-appear" not in text


def test_loader_resolves_sibling_checkout():
    """isc_activate_components should find the framework via a sibling checkout."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        # Sibling layout: base/linux_installation_scripts_functions + base/consumer
        sib = base / "linux_installation_scripts_functions"
        sib.mkdir()
        for name in (
            "component_menu.sh",
            "component_runtime.sh",
            "component_loader.sh",
            "component_logging.sh",
        ):
            (sib / name).write_text((REPO / name).read_text())
        consumer = base / "consumer"
        consumer.mkdir()
        script = f"""
set -uo pipefail
SCRIPT_DIR="{consumer}"
source "{sib}/component_loader.sh"
isc_activate_components
declare -F component_main >/dev/null && echo "runtime:ok"
echo "libdir:$ISC_COMPONENT_LIB_DIR"
"""
        # Run with HOME pointed away so only the sibling path can satisfy it.
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=consumer,
            env={"PATH": "/usr/bin:/bin", "HOME": str(base / "nohome")},
            capture_output=True,
            text=True,
        )
    assert result.returncode == 0, result.stderr
    assert "runtime:ok" in result.stdout, result.stdout
    assert str(sib) in result.stdout, result.stdout


def test_installer_helpers_use_root_optional_run_as_target():
    """The shared run_as_target must avoid unconditional sudo (sudo-free path)."""
    source = (REPO / "installer_helpers.sh").read_text()
    # Same-user branch runs without sudo; only a differing user escalates.
    assert 'if [ "$(PATH="$command_path" id -un)" = "$TARGET_USER" ]; then' in source
    assert "sudo -H -u" in source
    assert 'source "$_isc_helpers_dir/component_logging.sh"' in source
    for fn in (
        "run_as_target()",
        "msg()",
        "need_cmd()",
        "apt_install()",
        "ensure_session_bus()",
        "installer_auth_enabled()",
        "ensure_linked_repository()",
    ):
        assert fn in source, f"missing {fn}"


def test_installer_helpers_route_internal_logs_through_isc_api():
    """installer_helpers should keep log() only as a compatibility alias."""
    source = (REPO / "installer_helpers.sh").read_text()
    body_after_bootstrap = source.split("# msg - Print", maxsplit=1)[1]
    assert 'log "' not in body_after_bootstrap
    assert "log() { isc_log" in source
    assert "isc_log_warn" in body_after_bootstrap


def test_installer_helpers_log_sudo_deferrals_to_shared_log():
    """Root-optional helper deferrals should be observable in the shared log."""
    with tempfile.TemporaryDirectory() as tmp:
        logdir = Path(tmp) / ".log"
        script = f"""
set -uo pipefail
export ISC_LOG_DIR="{logdir}"
export ISC_LOG_TAG="helpers"
source "{REPO}/installer_helpers.sh"
note_sudo_required "install demo package"
report_sudo_required
"""
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert "SKIP (requires sudo): install demo package" in result.stdout
        text = (logdir / "installer_components.log").read_text()
        assert "[WARN" in text
        assert "root-only step deferred: install demo package" in text
        assert "root-only steps still pending: install demo package" in text


def test_run_as_target_adds_system_path_for_commands():
    """run_as_target should preserve commands when PATH is stripped."""
    script = f"""
set -uo pipefail
source "{REPO}/installer_helpers.sh"
TARGET_USER="$(id -un)"; TARGET_HOME="$HOME"
RUNTIME_DIR="/run/user/$(id -u)"; USER_BUS="unix:path=$RUNTIME_DIR/bus"; DISPLAY_VAL=":0"
PATH=/tmp
run_as_target sh -c 'printf "%s\\n" "$PATH"; command -v sh >/dev/null'
"""
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "/usr/bin" in result.stdout
    assert "/bin" in result.stdout


def test_run_as_target_clears_sudo_identity_for_target_commands():
    """Target-user commands should not inherit a parent sudo identity."""
    script = f"""
set -uo pipefail
source "{REPO}/installer_helpers.sh"
TARGET_USER="$(id -un)"; TARGET_HOME="$HOME"
RUNTIME_DIR="/run/user/$(id -u)"; USER_BUS="unix:path=$RUNTIME_DIR/bus"; DISPLAY_VAL=":0"
export SUDO_USER=root SUDO_UID=0 SUDO_GID=0
run_as_target sh -c 'printf "sudo_user=%s\\nsudo_uid=%s\\nsudo_gid=%s\\n" "${{SUDO_USER-unset}}" "${{SUDO_UID-unset}}" "${{SUDO_GID-unset}}"'
"""
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "sudo_user=\nsudo_uid=\nsudo_gid=\n"


def test_run_as_target_clears_sudo_identity_in_sudo_branch():
    """The sudo -u branch should scrub sudo identity variables too."""
    with tempfile.TemporaryDirectory() as tmp:
        bin_dir = Path(tmp) / "bin"
        bin_dir.mkdir()
        (bin_dir / "id").write_text(
            "#!/bin/sh\nif [ \"$1\" = \"-un\" ]; then printf 'root\\n'; else /usr/bin/id \"$@\"; fi\n",
            encoding="utf-8",
        )
        (bin_dir / "sudo").write_text(
            """#!/bin/sh
if [ "$1" = "-H" ]; then shift; fi
if [ "$1" = "-u" ]; then shift 2; fi
exec "$@"
""",
            encoding="utf-8",
        )
        (bin_dir / "id").chmod(0o755)
        (bin_dir / "sudo").chmod(0o755)
        script = f"""
set -uo pipefail
source "{REPO}/installer_helpers.sh"
TARGET_USER=demo; TARGET_HOME=/home/demo
RUNTIME_DIR="/run/user/1001"; USER_BUS="unix:path=$RUNTIME_DIR/bus"; DISPLAY_VAL=":0"
export SUDO_USER=root SUDO_UID=0 SUDO_GID=0
PATH="{bin_dir}"
run_as_target sh -c 'printf "sudo_user=%s\\nsudo_uid=%s\\nsudo_gid=%s\\n" "${{SUDO_USER-unset}}" "${{SUDO_UID-unset}}" "${{SUDO_GID-unset}}"'
"""
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "sudo_user=\nsudo_uid=\nsudo_gid=\n"


def test_linked_repository_helper_uses_existing_checkout_without_auth():
    """Linked repo helper should not pull existing siblings unless auth is on."""
    with tempfile.TemporaryDirectory() as tmp:
        checkout = Path(tmp) / "linked"
        (checkout / ".git").mkdir(parents=True)
        script = f"""
set -uo pipefail
source "{REPO}/installer_helpers.sh"
TARGET_USER="$(id -un)"; TARGET_HOME="$HOME"
RUNTIME_DIR="/run/user/$(id -u)"; USER_BUS="unix:path=$RUNTIME_DIR/bus"; DISPLAY_VAL=":0"
run_as_target() {{
  printf 'RUN'
  printf ' <%s>' "$@"
  printf '\\n'
}}
ensure_linked_repository "linked repo" "{checkout}" "https://example.invalid/linked.git"
"""
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "Using existing linked repo repository" in result.stdout
    assert "RUN <git>" not in result.stdout


def test_linked_repository_helper_updates_existing_checkout_with_auth():
    """Linked repo helper should pull existing siblings when auth is on."""
    with tempfile.TemporaryDirectory() as tmp:
        checkout = Path(tmp) / "linked"
        (checkout / ".git").mkdir(parents=True)
        script = f"""
set -uo pipefail
INSTALLER_AUTH=1
source "{REPO}/installer_helpers.sh"
TARGET_USER="$(id -un)"; TARGET_HOME="$HOME"
RUNTIME_DIR="/run/user/$(id -u)"; USER_BUS="unix:path=$RUNTIME_DIR/bus"; DISPLAY_VAL=":0"
run_as_target() {{
  printf 'RUN'
  printf ' <%s>' "$@"
  printf '\\n'
}}
ensure_linked_repository "linked repo" "{checkout}" "https://example.invalid/linked.git"
"""
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "Updating existing linked repo repository" in result.stdout
    assert f"RUN <env> <GIT_TERMINAL_PROMPT=0> <git> <-C> <{checkout}> <pull>" in result.stdout


def test_linked_repository_helper_blocks_missing_checkout_without_auth():
    """Linked repo helper should not clone private siblings unless auth is on."""
    with tempfile.TemporaryDirectory() as tmp:
        checkout = Path(tmp) / "linked"
        script = f"""
set -uo pipefail
source "{REPO}/installer_helpers.sh"
TARGET_USER="$(id -un)"; TARGET_HOME="$HOME"
RUNTIME_DIR="/run/user/$(id -u)"; USER_BUS="unix:path=$RUNTIME_DIR/bus"; DISPLAY_VAL=":0"
run_as_target() {{
  printf 'RUN'
  printf ' <%s>' "$@"
  printf '\\n'
}}
ensure_linked_repository "linked repo" "{checkout}" "https://example.invalid/linked.git"
"""
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 1
    assert "pass --auth or set INSTALLER_AUTH=1 to clone it" in result.stdout
    assert "RUN <git>" not in result.stdout


def test_linked_repository_helper_clones_missing_checkout_with_auth():
    """Linked repo helper should clone missing siblings when auth is on."""
    with tempfile.TemporaryDirectory() as tmp:
        checkout = Path(tmp) / "linked"
        script = f"""
set -uo pipefail
INSTALLER_AUTH=1
source "{REPO}/installer_helpers.sh"
TARGET_USER="$(id -un)"; TARGET_HOME="$HOME"
RUNTIME_DIR="/run/user/$(id -u)"; USER_BUS="unix:path=$RUNTIME_DIR/bus"; DISPLAY_VAL=":0"
run_as_target() {{
  printf 'RUN'
  printf ' <%s>' "$@"
  printf '\\n'
  if [ "$1" = env ] && [ "$3" = git ] && [ "$4" = clone ]; then
    mkdir -p "{checkout}/.git"
  fi
}}
ensure_linked_repository "linked repo" "{checkout}" "https://example.invalid/linked.git"
"""
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "Cloning linked repo repository" in result.stdout
    assert f"RUN <env> <GIT_TERMINAL_PROMPT=0> <git> <clone> <https://example.invalid/linked.git> <{checkout}>" in result.stdout


def test_component_runtime_accepts_auth_argument():
    """component_main should consume --auth and export INSTALLER_AUTH."""
    with tempfile.TemporaryDirectory() as tmp:
        script = f"""
set -uo pipefail
source "{REPO}/component_runtime.sh"
ISC_REPO_NAME=test_repo
ISC_COMPONENTS=("show|Show auth|on|show_auth")
show_auth() {{ printf 'AUTH=%s\\n' "${{INSTALLER_AUTH:-0}}"; }}
component_main --auth --default
"""
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "AUTH=1" in result.stdout
    assert "ignoring unknown argument: --auth" not in result.stdout


def test_loader_sources_shared_helpers_from_sibling():
    """isc_load_helpers should make run_as_target/msg available from a sibling."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        sib = base / "linux_installation_scripts_functions"
        sib.mkdir()
        for name in (
            "component_menu.sh",
            "component_runtime.sh",
            "component_loader.sh",
            "component_logging.sh",
            "installer_helpers.sh",
        ):
            (sib / name).write_text((REPO / name).read_text())
        consumer = base / "consumer"
        consumer.mkdir()
        script = f"""
set -uo pipefail
SCRIPT_DIR="{consumer}"
TARGET_USER="$(id -un)"; TARGET_HOME="$HOME"
RUNTIME_DIR="/run/user/$(id -u)"; USER_BUS="unix:path=$RUNTIME_DIR/bus"; DISPLAY_VAL=":0"
source "{sib}/component_loader.sh"
isc_load_helpers
declare -F run_as_target >/dev/null && echo "helpers:ok"
run_as_target id -un
"""
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=consumer,
            env={"PATH": "/usr/bin:/bin", "HOME": str(base / "nohome")},
            capture_output=True,
            text=True,
        )
    assert result.returncode == 0, result.stderr
    assert "helpers:ok" in result.stdout, result.stdout


def test_python_logging_get_logger_is_idempotent():
    """get_logger should attach one best-effort handler per logger name."""
    name = f"component-framework-test-{uuid.uuid4()}"
    logger = get_logger(name, "python_logging_tests.log")
    again = get_logger(name, "python_logging_tests.log")
    assert logger is again
    assert len(logger.handlers) == 1
    logger.info("idempotent logger test")
    log_file = REPO / ".log" / "python_logging_tests.log"
    assert log_file.is_file()
    assert "idempotent logger test" in log_file.read_text()


def test_python_log_call_records_arguments_and_return_value():
    """log_call should record ENTER args and EXIT return value."""
    name = f"component-framework-trace-test-{uuid.uuid4()}"
    logger = get_logger(name, "python_trace_tests.log")

    @log_call(logger)
    def combine(prefix, count=1):
        return f"{prefix}:{count}"

    assert combine("alpha", count=3) == "alpha:3"
    text = (REPO / ".log" / "python_trace_tests.log").read_text()
    assert "ENTER test_component_framework.py:test_python_log_call_records_arguments_and_return_value.<locals>.combine(prefix='alpha', count=3)" in text
    assert "EXIT test_component_framework.py:test_python_log_call_records_arguments_and_return_value.<locals>.combine -> 'alpha:3'" in text


def test_interactive_submenu_is_not_redirected_to_devnull():
    """The standalone interactive submenu must render to the terminal.

    Regression: `_isc_interactive_select >/dev/null` sent the whole menu to
    /dev/null (it only sets result globals, echoing nothing), leaving the user
    staring at a blank screen while the menu silently waited for keypresses.
    """
    runtime = (REPO / "component_runtime.sh").read_text(encoding="utf-8")
    assert "_isc_interactive_select >/dev/null" not in runtime
    assert 'cm_single_submenu "$repo"; rc=$?' in runtime


def test_hotkey_capture_is_opt_in():
    """Interactive hotkey capture must be gated behind ISC_HOTKEY_INTERACTIVE.

    A plain install (including `sudo bash install.sh` and the master run) must
    apply the shown defaults non-interactively and never open an evdev grab, so
    it can never appear to hang.
    """
    capture = (REPO / "hotkey_capture.sh").read_text(encoding="utf-8")
    assert 'ISC_HOTKEY_INTERACTIVE:-0' in capture


def test_no_arg_no_tty_run_survives_set_e_without_menu_module():
    """No-arg component_main under `set -e` must apply defaults without a TTY.

    Child installers run with `set -euo pipefail`. When stdin is not a TTY the
    menu module is never loaded, so _isc_prepare_selection_state's trailing
    cm_reconcile_dependencies guard must not surface a non-zero status —
    otherwise every no-arg master/child run aborts before any component runs.
    """
    harness = HARNESS.replace("set -uo pipefail", "set -euo pipefail")
    with tempfile.TemporaryDirectory() as tmp:
        config_dir = Path(tmp) / "installation_configs"
        config_dir.mkdir()
        row = {"config_value": "", "favorite": 0, "on": 1, "startup": 0,
               "sticky": 0, "uninstall": 0, "workspace": 0}
        (config_dir / "default.json").write_text(json.dumps({
            "components": {"alpha": dict(row), "beta": dict(row, on=0),
                           "gamma": dict(row, on=0)},
            "repo": "demo", "schema_version": 1, "scope": "standalone",
        }), encoding="utf-8")
        result = subprocess.run(
            ["bash", "-c", harness, "bash"],
            cwd=tmp,
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            env={**os.environ, "ISC_RECEIPT_DIR": str(Path(tmp) / "receipts")},
        )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ran:a" in result.stdout
    assert "ran:b" not in result.stdout
    assert "ran:c" not in result.stdout


CORE_HARNESS = """
set -uo pipefail
source "{repo}/component_runtime.sh"
comp_a() {{ echo "ran:a"; }}
comp_b() {{ echo "ran:b"; }}
pre() {{ echo "preflight"; }}
core() {{ echo "core"; return {core_rc}; }}
ISC_REPO_NAME="demo"
ISC_REPO_LABEL="Demo"
ISC_PREFLIGHT="pre"
ISC_CORE="core"
ISC_COMPONENTS=(
  "alpha|Alpha|on|comp_a"
  "beta|Beta|off|comp_b"
)
component_main "$@"
"""


def run_core(args, core_rc=0):
    """Run a harness that declares an ISC_CORE hook; return (rc, stdout)."""
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            ["bash", "-c", CORE_HARNESS.format(repo=REPO, core_rc=core_rc), "bash", *args],
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            env={**os.environ, "ISC_RECEIPT_DIR": str(Path(tmp) / "receipts")},
        )
    return result.returncode, result.stdout + result.stderr


def test_core_hook_runs_even_for_a_blank_selection():
    """ISC_CORE must install the repo core even when no component is selected."""
    rc, out = run_core(["--select", ""])
    assert rc == 0, out
    assert "core" in out, out
    assert "No components selected" in out, out
    assert "ran:a" not in out, out


def test_core_hook_runs_once_before_any_component():
    """ISC_CORE runs exactly once, ahead of the first component and the preflight."""
    rc, out = run_core(["--all"])
    assert rc == 0, out
    lines = [line for line in out.splitlines() if line in ("core", "preflight", "ran:a", "ran:b")]
    assert lines.count("core") == 1, out
    assert lines.index("core") < lines.index("preflight") < lines.index("ran:a"), out
    assert "ran:b" in out, out


def test_core_hook_failure_aborts_before_components_run():
    """A failing ISC_CORE is fatal: components must not install on a broken core."""
    rc, out = run_core(["--all"], core_rc=1)
    assert rc == 2, out
    assert "ran:a" not in out, out
    assert "ran:b" not in out, out


def test_preflight_is_still_skipped_for_a_blank_selection():
    """ISC_PREFLIGHT keeps its per-run semantics: a no-op run starts nothing."""
    rc, out = run_core(["--select", ""])
    assert rc == 0, out
    assert "preflight" not in out, out


def test_core_hook_runs_when_the_config_selection_is_empty():
    """A no-argument (non-TTY) run whose saved/derived selection is empty is
    still an install of the repository core — the same guarantee `--select ''`
    gives. Without this, deselecting every row leaves a dead repo."""
    harness = CORE_HARNESS.replace('"alpha|Alpha|on|comp_a"', '"alpha|Alpha|off|comp_a"')
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            ["bash", "-c", harness.format(repo=REPO, core_rc=0), "bash"],
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            env={**os.environ, "ISC_RECEIPT_DIR": str(Path(tmp) / "receipts")},
        )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    assert "core" in out, out
    assert "No components selected" in out, out
    assert "ran:a" not in out, out
    assert "ran:b" not in out, out


def test_default_skips_dependent_whose_requirement_is_off_without_failing():
    """`--default` must stay installable when a default-on entry depends on a
    default-off one: the dependent is skipped with a warning, like the
    interactive menu's silent reconcile, and the run still succeeds."""
    dependency_harness = HARNESS.replace(
        '"alpha|Alpha|on|comp_a"', '"alpha|Alpha|off|comp_a"'
    ).replace(
        '"beta|Beta|on|comp_b"', '"beta|Beta|on|comp_b|||Agent tools|alpha"'
    )
    with tempfile.TemporaryDirectory() as receipt_dir:
        result = subprocess.run(
            ["bash", "-c", dependency_harness, "bash", "--default"],
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "ISC_RECEIPT_DIR": receipt_dir},
        )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "requires component 'alpha'" in result.stdout
    assert "ran:b" not in result.stdout
    assert "Components with failures" not in result.stdout


if __name__ == "__main__":
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


def test_component_runtime_rejects_unknown_option():
    """A mistyped flag must abort instead of silently running a default install."""
    script = f"""
set -uo pipefail
source "{REPO}/component_runtime.sh"
ISC_REPO_NAME=test_repo
ISC_COMPONENTS=("alpha|Alpha|on|install_alpha" "beta|Beta|on|install_beta")
install_alpha() {{ printf 'RAN alpha\\n'; }}
install_beta() {{ printf 'RAN beta\\n'; }}
component_main --slect alpha
"""
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "RAN alpha" not in result.stdout
    assert "RAN beta" not in result.stdout
    assert "unknown option" in (result.stdout + result.stderr).lower()


def test_component_runtime_still_ignores_stray_positional_token():
    """Non-option leftovers stay non-fatal so existing callers keep working."""
    script = f"""
set -uo pipefail
source "{REPO}/component_runtime.sh"
ISC_REPO_NAME=test_repo
ISC_COMPONENTS=("alpha|Alpha|on|install_alpha")
install_alpha() {{ printf 'RAN alpha\\n'; }}
component_main --select alpha stray-token
"""
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RAN alpha" in result.stdout


def test_unused_monitor_label_helper_is_gone():
    """Menu render uses connector names; the unused label accessor must stay gone."""
    menu = (REPO / "component_menu.sh").read_text(encoding="utf-8")
    assert "cm_monitor_label()" not in menu
    assert "CM_MONITOR_LABELS" not in menu
    assert "CM_MONITOR_CONNECTORS" in menu


def test_unused_selected_from_state_helper_is_gone():
    """Selection is resolved by component_main; the unused helper must stay gone."""
    runtime = (REPO / "component_runtime.sh").read_text(encoding="utf-8")
    assert "_isc_selected_from_state()" not in runtime
    assert "isc_route_readonly_args()" in runtime
