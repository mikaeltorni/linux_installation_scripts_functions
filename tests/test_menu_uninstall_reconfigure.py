#!/usr/bin/env python3
"""Interaction tests for the install-aware component submenu (component_menu.sh).

Drives cm_single_submenu with a scripted keystroke stream (read from a pipe, so
no real TTY is needed) and inspects the resulting CM_* selection arrays. This
locks the state machine for the three actions the menu must support on top of
plain install selection: reconfigure of an installed component (SPACE), marking
an installed component for uninstall ([u]), and reconfigure-all ([r]).
"""

import subprocess
import re
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Key tokens -> raw bytes the menu's cm_read_key consumes.
KEYS = {
    "DOWN": "\x1b[B",
    "UP": "\x1b[A",
    "SPACE": " ",
    "L": "l",
    "U": "u",
    "R": "r",
    "F": "f",
    "S": "s",
    "P": "p",
    "RIGHT": "\x1b[C",
    **{str(number): str(number) for number in range(10)},
    "ENTER": "\n",
    "Q": "q",
}


def drive(keys: list[str], sticky_eligible: bool = True) -> dict[str, str]:
    """Run the submenu with two components (alpha installed, beta absent).

    Feeds `keys` and returns the resolved per-component state as a dict of
    "<id>.on" / "<id>.uninstall" -> value. `sticky_eligible` controls whether
    the fixture components advertise [p] all-workspaces eligibility.
    """
    keystream = "".join(KEYS[k] for k in keys)
    sticky_flag = "1" if sticky_eligible else "0"
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
CM_COMP_FAVORITE_ELIGIBLE[$repo|alpha]=1
CM_COMP_FAVORITE_ELIGIBLE[$repo|beta]=1
CM_COMP_FAVORITE_ON[$repo|alpha]=0
CM_COMP_FAVORITE_ON[$repo|beta]=1
CM_COMP_STARTUP_ELIGIBLE[$repo|alpha]=1
CM_COMP_STARTUP_ELIGIBLE[$repo|beta]=1
CM_COMP_STARTUP_ON[$repo|alpha]=0
CM_COMP_STARTUP_ON[$repo|beta]=1
CM_COMP_WORKSPACE_ELIGIBLE[$repo|alpha]=1
CM_COMP_WORKSPACE_ELIGIBLE[$repo|beta]=1
CM_COMP_WORKSPACE[$repo|alpha]=0
CM_COMP_WORKSPACE[$repo|beta]=4
CM_COMP_STICKY_ELIGIBLE[$repo|alpha]={sticky_flag}
CM_COMP_STICKY_ELIGIBLE[$repo|beta]={sticky_flag}
CM_COMP_STICKY_ON[$repo|alpha]=0
CM_COMP_STICKY_ON[$repo|beta]=0
CM_COMP_CONFIGURE_ELIGIBLE[$repo|alpha]=1
CM_COMP_CONFIGURE_ELIGIBLE[$repo|beta]=0
CM_COMP_CONFIG_VALUE[$repo|alpha]='Super+W'
CONFIGURED=""
test_configure_callback() {{ CONFIGURED="$1|$2"; }}
CM_CONFIGURE_CALLBACK=test_configure_callback
cm_single_submenu "$repo" >/dev/null 2>&1
for id in alpha beta; do
  printf '%s.on=%s\\n' "$id" "${{CM_COMP_ON[$repo|$id]:-}}"
  printf '%s.uninstall=%s\\n' "$id" "${{CM_COMP_UNINSTALL[$repo|$id]:-}}"
  printf '%s.favorite=%s\\n' "$id" "${{CM_COMP_FAVORITE_ON[$repo|$id]:-}}"
  printf '%s.startup=%s\\n' "$id" "${{CM_COMP_STARTUP_ON[$repo|$id]:-}}"
  printf '%s.workspace=%s\\n' "$id" "${{CM_COMP_WORKSPACE[$repo|$id]:-}}"
  printf '%s.sticky=%s\\n' "$id" "${{CM_COMP_STICKY_ON[$repo|$id]:-}}"
done
printf 'configured=%s\n' "$CONFIGURED"
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
    """[u] clears apply, favourite, and startup selection."""
    # SPACE first selects reconfigure, then U must flip to uninstall.
    state = drive(["F", "S", "SPACE", "U", "ENTER"])
    assert state["alpha.uninstall"] == "1"
    assert state["alpha.on"] == "0"
    assert state["alpha.favorite"] == "0"
    assert state["alpha.startup"] == "0"


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


def test_f_toggles_favorite_without_changing_install_selection():
    """[f] toggles dock favourite selection independently of install state."""
    state = drive(["F", "ENTER"])
    assert state["alpha.favorite"] == "1"
    assert state["alpha.on"] == "0"
    assert state["alpha.uninstall"] == "0"


def test_f_toggles_existing_favorite_off():
    """[f] can remove the favourite marker from an absent selected component."""
    state = drive(["DOWN", "F", "ENTER"])
    assert state["beta.favorite"] == "0"
    assert state["beta.on"] == "1"


def test_s_toggles_startup_without_changing_install_selection():
    """[s] toggles startup independently of install and favourite state."""
    state = drive(["S", "ENTER"])
    assert state["alpha.startup"] == "1"
    assert state["alpha.favorite"] == "0"
    assert state["alpha.on"] == "0"


def test_s_toggles_existing_startup_off():
    """[s] can remove startup from an absent selected component."""
    state = drive(["DOWN", "S", "ENTER"])
    assert state["beta.startup"] == "0"
    assert state["beta.on"] == "1"


def test_number_assigns_workspace_without_changing_install_state():
    state = drive(["3", "ENTER"])
    assert state["alpha.workspace"] == "3"
    assert state["alpha.on"] == "0"


def test_zero_clears_workspace_assignment():
    state = drive(["DOWN", "0", "ENTER"])
    assert state["beta.workspace"] == "0"


def test_p_toggles_all_workspaces_persistence():
    """[p] marks an eligible app persistent on all workspaces without touching install state."""
    state = drive(["P", "ENTER"])
    assert state["alpha.sticky"] == "1"
    assert state["alpha.on"] == "0"
    assert state["alpha.uninstall"] == "0"


def test_p_toggles_persistence_off():
    """A second [p] clears the all-workspaces marker."""
    state = drive(["P", "P", "ENTER"])
    assert state["alpha.sticky"] == "0"


def test_p_clears_single_workspace_assignment():
    """[p] on a workspace-pinned app clears the [1-9] pin (mutually exclusive)."""
    state = drive(["DOWN", "P", "ENTER"])
    assert state["beta.sticky"] == "1"
    assert state["beta.workspace"] == "0"


def test_workspace_number_clears_persistence():
    """Pinning to one workspace clears a previous all-workspaces selection."""
    state = drive(["P", "3", "ENTER"])
    assert state["alpha.workspace"] == "3"
    assert state["alpha.sticky"] == "0"


def test_u_clears_persistence_selection():
    """[u] on an installed app clears the all-workspaces marker with the others."""
    state = drive(["P", "U", "ENTER"])
    assert state["alpha.uninstall"] == "1"
    assert state["alpha.sticky"] == "0"


def test_p_is_ignored_for_ineligible_component():
    """[p] must be a no-op when the component exposes no desktop metadata."""
    state = drive(["P", "ENTER"], sticky_eligible=False)
    assert state["alpha.sticky"] == "0"


def test_submenu_renders_persistent_marker():
    """A sticky-selected app shows the [P] marker and the all-workspaces label."""
    script = f"""
set -uo pipefail
source "{REPO}/component_menu.sh"
repo=demo
CM_REPO_LABEL[$repo]=Demo
CM_COMP_IDS[$repo]="alpha"
CM_COMP_LABEL[$repo|alpha]=Alpha
CM_COMP_ON[$repo|alpha]=1
CM_COMP_STICKY_ON[$repo|alpha]=1
out="$(cm_render_submenu "$repo" 0 "Configure components" "[p] all workspaces")"
printf '%s' "$out"
"""
    result = subprocess.run(
        ["bash", "-c", script], cwd=REPO, check=False, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    assert "[P] Alpha" in plain
    assert "(all workspaces)" in plain


def test_right_opens_nested_component_configurator_and_selects_reconfigure():
    """RIGHT should open eligible detail UI and mark the component for apply."""
    state = drive(["RIGHT", "ENTER"])
    assert state["configured"] == "demo|alpha"
    assert state["alpha.on"] == "1"


def test_right_inline_rebind_keeps_submenu_and_updates_value():
    """RIGHT in cm_submenu_loop captures Super+U without escape garbage or stacked UI."""
    super_u_enter = b"\x1b[117;8u\n"
    keystream = KEYS["RIGHT"].encode("latin-1") + super_u_enter + KEYS["ENTER"].encode("latin-1")
    with tempfile.TemporaryDirectory() as tmp:
        config = Path(tmp) / "hotkeys.conf"
        transcript = Path(tmp) / "capture.transcript"
        script = f"""
set -uo pipefail
export ISC_CAPTURE_TRANSCRIPT="{transcript}"
source "{REPO}/component_menu.sh"
source "{REPO}/hotkey_capture.sh"
run_as_target() {{ "$@"; }}
repo=demo
CM_REPO_LABEL[$repo]=Demo
CM_COMP_IDS[$repo]=ws1
CM_COMP_LABEL[$repo|ws1]='Switch to workspace 1'
CM_COMP_INSTALLED[$repo|ws1]=1
CM_COMP_ON[$repo|ws1]=0
CM_COMP_CONFIGURE_ELIGIBLE[$repo|ws1]=1
CM_COMP_CONFIG_VALUE[$repo|ws1]='Super+Z'
inline_configure() {{
  local callback_repo="$1" callback_id="$2"
  [[ "$callback_repo" == "$repo" && "$callback_id" == "ws1" ]] || return 2
  value="$(isc_prompt_hotkey_field {config} WORKSPACE_SWITCH_1 'Switch to workspace 1' '<Super>z')"
  [[ -n "$value" ]] && CM_COMP_CONFIG_VALUE[$repo|ws1]="$value"
}}
CM_CONFIGURE_CALLBACK=inline_configure
cm_submenu_loop "$repo" standalone
printf 'value=%s\\n' "${{CM_COMP_CONFIG_VALUE[$repo|ws1]:-}}"
printf 'transcript=%s\\n' "$(cat "{transcript}" 2>/dev/null || true)"
"""
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=REPO,
            input=keystream,
            text=False,
            capture_output=True,
            check=False,
        )
        stdout = result.stdout.decode(errors="replace")
        stderr = result.stderr.decode(errors="replace")
        assert result.returncode == 0, stderr
        plain = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", stdout)
        assert "Configure components" in plain
        assert "edit" in plain.lower()
        assert "[Super+U]" in plain
        assert "value=Super+U" in stdout
        assert "107;9u" not in stderr
        assert "107;9u" not in stdout
        assert "Modifiers:" in stderr
        assert "Key:" in stderr
        assert "\033[3A" in stderr, "capture overlay should refresh in place, not stack new lines"
        transcript_text = transcript.read_text(encoding="utf-8") if transcript.exists() else ""
        assert "modifiers='Super'" in transcript_text
        assert "key='U'" in transcript_text
        assert "WORKSPACE_SWITCH_1=<Super>u" in config.read_text(encoding="utf-8")


def test_right_inline_control_toggle_remove_rebind():
    """RIGHT rebind: left Ctrl on, right Ctrl off, left Ctrl on again, then key."""
    capture = b"\x1b[57421u\x1b[57422u\x1b[57421u\x1b[117u\n"
    keystream = KEYS["RIGHT"].encode("latin-1") + capture + KEYS["ENTER"].encode("latin-1")
    with tempfile.TemporaryDirectory() as tmp:
        config = Path(tmp) / "hotkeys.conf"
        transcript = Path(tmp) / "capture.transcript"
        script = f"""
set -uo pipefail
export ISC_CAPTURE_TRANSCRIPT="{transcript}"
source "{REPO}/component_menu.sh"
source "{REPO}/hotkey_capture.sh"
run_as_target() {{ "$@"; }}
repo=demo
CM_REPO_LABEL[$repo]=Demo
CM_COMP_IDS[$repo]=ws1
CM_COMP_LABEL[$repo|ws1]='Switch to workspace 1'
CM_COMP_INSTALLED[$repo|ws1]=1
CM_COMP_CONFIGURE_ELIGIBLE[$repo|ws1]=1
CM_COMP_CONFIG_VALUE[$repo|ws1]='Super+Z'
inline_configure() {{
  value="$(isc_prompt_hotkey_field {config} WORKSPACE_SWITCH_1 'Switch to workspace 1' '<Super>z')"
  [[ -n "$value" ]] && CM_COMP_CONFIG_VALUE[$repo|ws1]="$value"
}}
CM_CONFIGURE_CALLBACK=inline_configure
cm_submenu_loop "$repo" standalone
printf 'value=%s\\n' "${{CM_COMP_CONFIG_VALUE[$repo|ws1]:-}}"
"""
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=REPO,
            input=keystream,
            text=False,
            capture_output=True,
            check=False,
        )
        stdout = result.stdout.decode(errors="replace")
        stderr = result.stderr.decode(errors="replace")
        transcript_text = transcript.read_text(encoding="utf-8") if transcript.exists() else ""
        assert result.returncode == 0, stderr
        plain = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", stdout)
        assert "Configure components" in plain
        assert "[Ctrl+U]" in plain
        assert "value=Ctrl+U" in stdout
        assert "modifiers='(none)'" in transcript_text
        assert "107;9u" not in stderr
        assert "WORKSPACE_SWITCH_1=<Control>u" in config.read_text(encoding="utf-8")


def test_right_inline_v2_modifier_rebind():
    """RIGHT rebind registers kitty v2 lone modifier presses and persists Ctrl+U."""
    capture = b"\x1b[57421;5:1u\x1b[57422;5:1u\x1b[57421;5:1u\x1b[117u\n"
    keystream = KEYS["RIGHT"].encode("latin-1") + capture + KEYS["ENTER"].encode("latin-1")
    with tempfile.TemporaryDirectory() as tmp:
        config = Path(tmp) / "hotkeys.conf"
        transcript = Path(tmp) / "capture.transcript"
        script = f"""
set -uo pipefail
export ISC_CAPTURE_TRANSCRIPT="{transcript}"
source "{REPO}/component_menu.sh"
source "{REPO}/hotkey_capture.sh"
run_as_target() {{ "$@"; }}
repo=demo
CM_REPO_LABEL[$repo]=Demo
CM_COMP_IDS[$repo]=ws1
CM_COMP_LABEL[$repo|ws1]='Switch to workspace 1'
CM_COMP_INSTALLED[$repo|ws1]=1
CM_COMP_CONFIGURE_ELIGIBLE[$repo|ws1]=1
CM_COMP_CONFIG_VALUE[$repo|ws1]='Super+Z'
inline_configure() {{
  value="$(isc_prompt_hotkey_field {config} WORKSPACE_SWITCH_1 'Switch to workspace 1' '<Super>z')"
  [[ -n "$value" ]] && CM_COMP_CONFIG_VALUE[$repo|ws1]="$value"
}}
CM_CONFIGURE_CALLBACK=inline_configure
cm_submenu_loop "$repo" standalone
printf 'value=%s\\n' "${{CM_COMP_CONFIG_VALUE[$repo|ws1]:-}}"
"""
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=REPO,
            input=keystream,
            text=False,
            capture_output=True,
            check=False,
        )
        stdout = result.stdout.decode(errors="replace")
        stderr = result.stderr.decode(errors="replace")
        transcript_text = transcript.read_text(encoding="utf-8") if transcript.exists() else ""
        assert result.returncode == 0, stderr
        plain = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", stdout)
        assert "Configure components" in plain
        assert "[Ctrl+U]" in plain
        assert "value=Ctrl+U" in stdout
        assert "modifiers='Ctrl'" in transcript_text
        assert "WORKSPACE_SWITCH_1=<Control>u" in config.read_text(encoding="utf-8")


def test_right_inline_sequential_modifier_rebind():
    """RIGHT rebind accepts modifiers pressed one at a time (Ctrl+Shift+U)."""
    capture = b"\x1b[57421u\x1b[57417u\x1b[117u\n"
    keystream = KEYS["RIGHT"].encode("latin-1") + capture + KEYS["ENTER"].encode("latin-1")
    with tempfile.TemporaryDirectory() as tmp:
        config = Path(tmp) / "hotkeys.conf"
        script = f"""
set -uo pipefail
source "{REPO}/component_menu.sh"
source "{REPO}/hotkey_capture.sh"
run_as_target() {{ "$@"; }}
repo=demo
CM_REPO_LABEL[$repo]=Demo
CM_COMP_IDS[$repo]=ws1
CM_COMP_LABEL[$repo|ws1]='Switch to workspace 1'
CM_COMP_INSTALLED[$repo|ws1]=1
CM_COMP_CONFIGURE_ELIGIBLE[$repo|ws1]=1
CM_COMP_CONFIG_VALUE[$repo|ws1]='Super+Z'
inline_configure() {{
  value="$(isc_prompt_hotkey_field {config} WORKSPACE_SWITCH_1 'Switch to workspace 1' '<Super>z')"
  [[ -n "$value" ]] && CM_COMP_CONFIG_VALUE[$repo|ws1]="$value"
}}
CM_CONFIGURE_CALLBACK=inline_configure
cm_submenu_loop "$repo" standalone
printf 'value=%s\\n' "${{CM_COMP_CONFIG_VALUE[$repo|ws1]:-}}"
"""
        result = subprocess.run(
            ["bash", "-c", script],
            cwd=REPO,
            input=keystream,
            text=False,
            capture_output=True,
            check=False,
        )
        stdout = result.stdout.decode(errors="replace")
        stderr = result.stderr.decode(errors="replace")
        assert result.returncode == 0, stderr
        plain = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", stdout)
        assert "Configure components" in plain
        assert "[Ctrl+Shift+U]" in plain
        assert "value=Ctrl+Shift+U" in stdout
        assert "107;9u" not in stderr
        assert "Modifiers:" in stderr
        assert "WORKSPACE_SWITCH_1=<Control><Shift>u" in config.read_text(encoding="utf-8")


def test_configurable_value_is_rendered_with_edit_action():
    """Editable components show their current value and a generic edit affordance."""
    script = f"""
source "{REPO}/component_menu.sh"
repo=demo
CM_REPOS=("$repo")
CM_REPO_LABEL[$repo]=Demo
CM_REPO_ENABLED[$repo]=1
CM_COMP_IDS[$repo]=alpha
CM_COMP_LABEL[$repo|alpha]='Switch to workspace 1'
CM_COMP_INSTALLED[$repo|alpha]=1
CM_COMP_ON[$repo|alpha]=0
CM_COMP_CONFIGURE_ELIGIBLE[$repo|alpha]=1
CM_COMP_CONFIG_VALUE[$repo|alpha]='Super+W'
LINES=40 cm_render_submenu "$repo" 0 'Configure components' 'footer'
"""
    result = subprocess.run(
        ["bash", "-c", script], cwd=REPO, check=False, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "[Super+W]" in result.stdout
    assert "edit" in result.stdout


def test_footer_only_advertises_actions_exposed_by_component_metadata():
    """Repository-neutral metadata controls which optional actions are shown."""
    script = f"""
source "{REPO}/component_menu.sh"
repo=demo
CM_COMP_IDS[$repo]='alpha beta'
CM_COMP_CONFIGURE_ELIGIBLE[$repo|alpha]=1
CM_COMP_CONFIG_VALUE[$repo|alpha]='Super+W'
CM_COMP_FAVORITE_ELIGIBLE[$repo|beta]=1
CM_COMP_STARTUP_ELIGIBLE[$repo|beta]=1
CM_COMP_WORKSPACE_ELIGIBLE[$repo|beta]=1
CM_COMP_STICKY_ELIGIBLE[$repo|beta]=1
CM_COMP_INSTALLED[$repo|alpha]=1
cm_submenu_footer "$repo" embedded
"""
    result = subprocess.run(
        ["bash", "-c", script], cwd=REPO, check=False, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr
    assert "[↑/↓] move" in result.stdout
    assert "[space] toggle" in result.stdout
    assert "[→] edit" in result.stdout
    assert "[f] favourite" in result.stdout
    assert "[s] startup" in result.stdout
    assert "[1-9] workspace" in result.stdout
    assert "[p] all workspaces" in result.stdout
    assert "[u] uninstall" in result.stdout
    assert "[←/enter] back" in result.stdout


def test_footer_omits_optional_actions_when_no_component_exposes_them():
    """Plain repository installers retain only navigation and toggling labels."""
    script = f"""
source "{REPO}/component_menu.sh"
repo=demo
CM_COMP_IDS[$repo]='alpha'
CM_COMP_INSTALLED[$repo|alpha]=0
cm_submenu_footer "$repo" standalone
"""
    result = subprocess.run(
        ["bash", "-c", script], cwd=REPO, check=False, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[↑/↓] move  [space] toggle  [enter] apply"


def test_footer_calls_empty_configurable_fields_details_not_edit():
    """RIGHT says edit only when a configurable field returns a value."""
    script = f"""
source "{REPO}/component_menu.sh"
repo=demo
CM_COMP_IDS[$repo]='alpha'
CM_COMP_CONFIGURE_ELIGIBLE[$repo|alpha]=1
CM_COMP_CONFIG_VALUE[$repo|alpha]=''
cm_submenu_footer "$repo" embedded
"""
    result = subprocess.run(
        ["bash", "-c", script], cwd=REPO, check=False, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr
    assert "[→] details" in result.stdout
    assert "edit" not in result.stdout


def test_submenu_renders_combined_favorite_and_startup_marker():
    """A component selected for both actions should display the compact FS marker."""
    script = f"""
set -uo pipefail
source "{REPO}/component_menu.sh"
repo=demo
CM_REPO_LABEL[$repo]=Demo
CM_COMP_IDS[$repo]="alpha"
CM_COMP_LABEL[$repo|alpha]=Alpha
CM_COMP_ON[$repo|alpha]=1
CM_COMP_FAVORITE_ON[$repo|alpha]=1
CM_COMP_STARTUP_ON[$repo|alpha]=1
out="$(cm_render_submenu "$repo" 0 "Configure components" "[s] startup")"
printf '%s' "$out"
"""
    result = subprocess.run(
        ["bash", "-c", script], cwd=REPO, check=False, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    assert "[FS] Alpha" in plain
    assert "[s] startup" in plain


def test_submenu_render_scrolls_long_component_lists():
    """Long submenus should keep the selected row visible on small terminals."""
    script = f"""
set -uo pipefail
source "{REPO}/component_menu.sh"
repo=demo
CM_REPO_LABEL[$repo]=Demo
for i in $(seq 1 12); do
  id="item$i"
  CM_COMP_IDS[$repo]="${{CM_COMP_IDS[$repo]:-}} $id"
  CM_COMP_LABEL[$repo|$id]="Item $i"
  CM_COMP_ON[$repo|$id]=1
done
LINES=10 cm_render_submenu "$repo" 9 "Configure components" "footer"
"""
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Item 10" in result.stdout
    assert "more above" in result.stdout
    assert not re.search(r"Item 1(?![0-9])", result.stdout)


def test_submenu_render_reserves_rows_for_scroll_hints():
    """Scroll hints must not push the selected row off-screen."""
    script = f"""
set -uo pipefail
source "{REPO}/component_menu.sh"
repo=demo
CM_REPO_LABEL[$repo]=Demo
for i in $(seq 1 12); do
  id="item$i"
  CM_COMP_IDS[$repo]="${{CM_COMP_IDS[$repo]:-}} $id"
  CM_COMP_LABEL[$repo|$id]="Item $i"
  CM_COMP_ON[$repo|$id]=1
done
out="$(LINES=10 cm_render_submenu "$repo" 9 "Configure components" "footer")"
line_count=$(printf '%s' "$out" | wc -l)
printf 'lines=%s\\n' "$line_count"
printf '%s' "$out"
"""
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    lines = int(result.stdout.splitlines()[0].split("=", 1)[1])
    assert lines <= 10, result.stdout
    assert "Item 10" in result.stdout


def test_embedded_submenu_toggles_component_and_returns():
    """Embedded submenu must accept keys and return to the aggregate menu."""
    keystream = KEYS["DOWN"] + KEYS["SPACE"] + KEYS["ENTER"]
    script = f"""
set -uo pipefail
source "{REPO}/component_menu.sh"
repo=demo
CM_REPO_LABEL[$repo]=Demo
CM_COMP_IDS[$repo]="alpha beta"
CM_COMP_LABEL[$repo|alpha]=Alpha
CM_COMP_LABEL[$repo|beta]=Beta
CM_COMP_ON[$repo|alpha]=1
CM_COMP_ON[$repo|beta]=1
CM_COMP_INSTALLED[$repo|alpha]=0
CM_COMP_INSTALLED[$repo|beta]=0
cm_submenu_loop "$repo" embedded >/dev/null
printf 'alpha=%s beta=%s\\n' "${{CM_COMP_ON[$repo|alpha]:-0}}" "${{CM_COMP_ON[$repo|beta]:-0}}"
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
    assert "alpha=1" in result.stdout
    assert "beta=0" in result.stdout


def test_dependent_component_is_disabled_until_requirement_is_selected():
    """A dependency row cannot be selected while its required CLI is absent."""
    keystream = KEYS["DOWN"] + KEYS["SPACE"] + KEYS["ENTER"]
    script = f"""
set -uo pipefail
source "{REPO}/component_menu.sh"
repo=demo
CM_REPO_LABEL[$repo]=Demo
CM_COMP_IDS[$repo]="cli status"
CM_COMP_LABEL[$repo|cli]="CLI"
CM_COMP_LABEL[$repo|status]="Status bar"
CM_COMP_REQUIRES[$repo|status]="cli"
CM_COMP_ON[$repo|cli]=0
CM_COMP_ON[$repo|status]=0
CM_COMP_INSTALLED[$repo|cli]=0
CM_COMP_INSTALLED[$repo|status]=0
cm_submenu_loop "$repo" embedded >/dev/null
printf 'cli=%s status=%s\n' "${{CM_COMP_ON[$repo|cli]:-0}}" "${{CM_COMP_ON[$repo|status]:-0}}"
"""
    result = subprocess.run(
        ["bash", "-c", script], cwd=REPO, input=keystream,
        check=False, capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "cli=0 status=0" in result.stdout


def test_dependent_component_accepts_autodetected_installed_requirement():
    """An already-installed CLI unlocks its dependent during modification."""
    keystream = KEYS["DOWN"] + KEYS["SPACE"] + KEYS["ENTER"]
    script = f"""
set -uo pipefail
source "{REPO}/component_menu.sh"
repo=demo
CM_REPO_LABEL[$repo]=Demo
CM_COMP_IDS[$repo]="cli status"
CM_COMP_LABEL[$repo|cli]="CLI"
CM_COMP_LABEL[$repo|status]="Status bar"
CM_COMP_REQUIRES[$repo|status]="cli"
CM_COMP_ON[$repo|cli]=0
CM_COMP_ON[$repo|status]=0
CM_COMP_INSTALLED[$repo|cli]=1
CM_COMP_INSTALLED[$repo|status]=0
cm_submenu_loop "$repo" embedded >/dev/null
printf 'cli=%s status=%s\n' "${{CM_COMP_ON[$repo|cli]:-0}}" "${{CM_COMP_ON[$repo|status]:-0}}"
"""
    result = subprocess.run(
        ["bash", "-c", script], cwd=REPO, input=keystream,
        check=False, capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "cli=0 status=1" in result.stdout


def test_deselecting_requirement_clears_pending_dependent_selection():
    """Turning off a CLI must also clear its not-yet-installed dependent."""
    keystream = KEYS["SPACE"] + KEYS["ENTER"]
    script = f"""
set -uo pipefail
source "{REPO}/component_menu.sh"
repo=demo
CM_REPO_LABEL[$repo]=Demo
CM_COMP_IDS[$repo]="cli status"
CM_COMP_LABEL[$repo|cli]="CLI"
CM_COMP_LABEL[$repo|status]="Status bar"
CM_COMP_REQUIRES[$repo|status]="cli"
CM_COMP_ON[$repo|cli]=1
CM_COMP_ON[$repo|status]=1
CM_COMP_INSTALLED[$repo|cli]=0
CM_COMP_INSTALLED[$repo|status]=0
cm_submenu_loop "$repo" embedded >/dev/null
printf 'cli=%s status=%s\n' "${{CM_COMP_ON[$repo|cli]:-0}}" "${{CM_COMP_ON[$repo|status]:-0}}"
"""
    result = subprocess.run(
        ["bash", "-c", script], cwd=REPO, input=keystream,
        check=False, capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "cli=0 status=0" in result.stdout


def test_submenu_skips_blank_component_ids():
    """Blank ids from malformed manifests must not create dead menu rows."""
    script = f"""
set -uo pipefail
source "{REPO}/component_menu.sh"
repo=demo
CM_COMP_IDS[$repo]="alpha  beta"
CM_COMP_LABEL[$repo|alpha]=Alpha
CM_COMP_LABEL[$repo|beta]=Beta
CM_COMP_ON[$repo|alpha]=1
CM_COMP_ON[$repo|beta]=1
out="$(cm_render_submenu "$repo" 1 "Configure components" "footer")"
printf '%s' "$out"
"""
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Alpha" in result.stdout
    assert "Beta" in result.stdout
    assert result.stdout.count("›") == 1


def test_submenu_renders_named_sections_in_component_order():
    """Section metadata should render headings without becoming selectable rows."""
    script = f"""
set -uo pipefail
source "{REPO}/component_menu.sh"
repo=demo
CM_REPO_LABEL[$repo]=Demo
CM_COMP_IDS[$repo]="model app plugin"
CM_COMP_LABEL[$repo|model]="Ornstein model"
CM_COMP_LABEL[$repo|app]="Codex CLI"
CM_COMP_LABEL[$repo|plugin]="Commit plugin"
CM_COMP_SECTION[$repo|model]="Models"
CM_COMP_SECTION[$repo|app]="Agent tools"
CM_COMP_SECTION[$repo|plugin]="Plugins"
for id in model app plugin; do CM_COMP_ON[$repo|$id]=1; done
out="$(LINES=20 cm_render_submenu "$repo" 0 "Configure components" "footer")"
printf '%s' "$out"
"""
    result = subprocess.run(
        ["bash", "-c", script], cwd=REPO, check=False, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.index("Models") < result.stdout.index("Ornstein model")
    assert result.stdout.index("Agent tools") < result.stdout.index("Codex CLI")
    assert result.stdout.index("Plugins") < result.stdout.index("Commit plugin")
    assert result.stdout.count("›") == 1


def test_debug_aggregate_log_key_writes_component_state():
    """Debug-only [l] should log every repo/component state without stdout dump."""
    keystream = KEYS["L"] + KEYS["ENTER"]
    with tempfile.TemporaryDirectory() as tmp:
        log_dir = Path(tmp) / "menu-log"
        script = f"""
set -uo pipefail
export ISC_MENU_DEBUG=1
export ISC_LOG_DIR="{log_dir}"
source "{REPO}/component_menu.sh"
repo=demo
CM_REPOS=("$repo")
CM_REPO_LABEL[$repo]=Demo
CM_REPO_ENABLED[$repo]=1
CM_COMP_IDS[$repo]="alpha beta gamma"
CM_COMP_LABEL[$repo|alpha]=Alpha
CM_COMP_LABEL[$repo|beta]=Beta
CM_COMP_LABEL[$repo|gamma]=Gamma
CM_COMP_INSTALLED[$repo|alpha]=1
CM_COMP_INSTALLED[$repo|beta]=0
CM_COMP_INSTALLED[$repo|gamma]=1
CM_COMP_ON[$repo|alpha]=0
CM_COMP_ON[$repo|beta]=1
CM_COMP_ON[$repo|gamma]=0
CM_COMP_UNINSTALL[$repo|gamma]=1
CM_COMP_FAVORITE_ON[$repo|beta]=1
cm_aggregate_menu
printf 'log=%s\\n' "$(isc_log_file)"
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
        assert "component_state repo=demo component=alpha" not in result.stdout
        log_line = next(line for line in result.stdout.splitlines() if "log=" in line)
        log_file = Path(log_line.split("log=", 1)[1])
        text = log_file.read_text()
        assert "component state snapshot begin" in text
        assert "repo=demo enabled=1 selected=1 total=3 installed=2" in text
        assert "component=alpha label=Alpha state=installed" in text
        assert "component=beta label=Beta state=pending_install favorite=1" in text
        assert "component=gamma label=Gamma state=pending_uninstall" in text


def test_aggregate_log_key_is_ignored_without_debug():
    """Without ISC_MENU_DEBUG, [l] should be hidden and should not write state logs."""
    keystream = KEYS["L"] + KEYS["ENTER"]
    with tempfile.TemporaryDirectory() as tmp:
        log_dir = Path(tmp) / "menu-log"
        script = f"""
set -uo pipefail
export ISC_LOG_DIR="{log_dir}"
source "{REPO}/component_menu.sh"
repo=demo
CM_REPOS=("$repo")
CM_REPO_LABEL[$repo]=Demo
CM_REPO_ENABLED[$repo]=1
CM_COMP_IDS[$repo]="alpha"
CM_COMP_LABEL[$repo|alpha]=Alpha
CM_COMP_ON[$repo|alpha]=1
cm_aggregate_menu
printf 'log=%s\\n' "$(isc_log_file)"
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
        assert "[l] log state" not in result.stdout
        log_line = next(line for line in result.stdout.splitlines() if "log=" in line)
        log_file = Path(log_line.split("log=", 1)[1])
        text = log_file.read_text() if log_file.exists() else ""
        assert "component state snapshot begin" not in text


if __name__ == "__main__":
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
