#!/usr/bin/env bash
# component_runtime.sh - Shared per-repository installer component runtime.
#
# This is the single source of truth for the standalone installer contract every
# child repository implements. A repository's install.sh sources its step
# libraries, declares a component manifest, and calls component_main "$@". This
# runtime then provides a uniform command-line interface that both humans and
# the master installer rely on:
#
#   install.sh                 # interactive submenu on a TTY, else defaults
#   install.sh --default       # install every default-on component, no prompts
#   install.sh --all           # install every component, no prompts
#   install.sh --select a,b,c  # install exactly these component ids, no prompts
#   install.sh --list-components  # print "id\tlabel\tdefault" lines and exit
#   install.sh --help          # usage
#
# The manifest is an array named ISC_COMPONENTS whose entries are
# "id|label|default|function", where default is "on" or "off" and function is
# the shell function that installs that component (already defined by the
# repository's sourced libraries):
#
#   ISC_REPO_NAME="linux_configuration_setup"
#   ISC_REPO_LABEL="GNOME desktop configuration"
#   ISC_COMPONENTS=(
#     "dark_mode|Dark mode and themes|on|configure_dark_mode"
#     "easyeffects|EasyEffects EQ presets|off|configure_easyeffects_autostart"
#   )
#   component_main "$@"
#
# The master installer discovers components with --list-components and drives
# installation with --select, so disabled repositories are skipped and partially
# selected repositories install only their chosen components.
#
# Usage:
#   source "<dir>/component_runtime.sh"

if [[ -n "${ISC_RUNTIME_SOURCED:-}" ]]; then
  return 0 2>/dev/null || true
fi
ISC_RUNTIME_SOURCED=1

# Ensure the centralized logging helpers exist. Source component_logging.sh from
# next to this runtime when present, otherwise define silent no-op stubs so every
# isc_log* call below is always safe (logging must never abort an installer).
if ! declare -F isc_log >/dev/null 2>&1; then
  _isc_rt_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd 2>/dev/null)" || _isc_rt_dir=""
  if [[ -n "$_isc_rt_dir" && -f "$_isc_rt_dir/component_logging.sh" ]]; then
    # shellcheck source=/dev/null
    source "$_isc_rt_dir/component_logging.sh"
  fi
  unset _isc_rt_dir
fi
if ! declare -F isc_log >/dev/null 2>&1; then
  isc_log()         { :; }
  isc_log_verbose() { :; }
  isc_log_debug()   { :; }
  isc_log_info()    { :; }
  isc_log_warn()    { :; }
  isc_log_error()   { :; }
fi

# Fallback status printer if the repository did not define msg().
if ! declare -F msg >/dev/null 2>&1; then
  msg() { printf "\n==> %s\n" "$*"; }
fi

###############################################################################
# Manifest accessors
###############################################################################

# Echo the field at index $2 (0-based) of the manifest entry for id $1.
#
# Arguments:
#   $1 - component id to look up.
#   $2 - field index: 0=id, 1=label, 2=default, 3=function.
#
# Returns:
#   0 and prints the requested field when the id exists; 1 when no entry matches.
_isc_field() {
  local want_id="$1" field="$2" entry id label def fn
  for entry in "${ISC_COMPONENTS[@]}"; do
    IFS='|' read -r id label def fn <<<"$entry"
    if [[ "$id" == "$want_id" ]]; then
      case "$field" in
        0) printf '%s' "$id" ;;
        1) printf '%s' "$label" ;;
        2) printf '%s' "$def" ;;
        3) printf '%s' "$fn" ;;
      esac
      return 0
    fi
  done
  return 1
}

# Echo all component ids in manifest order, one per line.
#
# Arguments:
#   none (reads the ISC_COMPONENTS manifest).
#
# Returns:
#   0; prints every component id on its own line.
_isc_all_ids() {
  local entry id rest
  for entry in "${ISC_COMPONENTS[@]}"; do
    IFS='|' read -r id rest <<<"$entry"
    printf '%s\n' "$id"
  done
}

# Echo the ids whose default field is "on", in manifest order, one per line.
#
# Arguments:
#   none (reads the ISC_COMPONENTS manifest).
#
# Returns:
#   0; prints each default-on component id on its own line.
_isc_default_ids() {
  local entry id label def rest
  for entry in "${ISC_COMPONENTS[@]}"; do
    IFS='|' read -r id label def rest <<<"$entry"
    [[ "$def" == "on" ]] && printf '%s\n' "$id"
  done
}

###############################################################################
# Sub-commands
###############################################################################

# Print "id<TAB>label<TAB>default" for every component. Consumed by the master
# installer to build the aggregate menu without sourcing repo internals.
#
# Arguments:
#   none (reads the ISC_COMPONENTS manifest).
#
# Returns:
#   0; prints one tab-separated line per component.
_isc_list_components() {
  local entry id label def rest
  for entry in "${ISC_COMPONENTS[@]}"; do
    IFS='|' read -r id label def rest <<<"$entry"
    printf '%s\t%s\t%s\n' "$id" "$label" "$def"
  done
}

# Run the install functions for the given space/newline-separated ids, in
# manifest order, continuing past failures and reporting them at the end.
#
# Arguments:
#   $1 - whitespace-separated list of selected component ids
#
# Returns:
#   0 when all selected components succeeded; 1 when one or more failed.
_isc_run_selected() {
  local selected=" $(tr ',\n' '  ' <<<"$1") "
  local entry id label def fn ran=0
  local -a failed=()
  isc_log_info "run_selected requested ids:${selected}"
  for entry in "${ISC_COMPONENTS[@]}"; do
    IFS='|' read -r id label def fn <<<"$entry"
    [[ "$selected" == *" $id "* ]] || continue
    # Run the optional one-time preflight (e.g. ensuring the session bus) just
    # before the first real component, so an empty/unmatched selection is a
    # genuine no-op.
    if (( ran == 0 )) && [[ -n "${ISC_PREFLIGHT:-}" ]] \
       && declare -F "$ISC_PREFLIGHT" >/dev/null 2>&1; then
      isc_log_debug "running preflight '$ISC_PREFLIGHT'"
      "$ISC_PREFLIGHT" || {
        isc_log_warn "preflight '$ISC_PREFLIGHT' reported a problem (continuing)"
        msg "WARN: preflight '$ISC_PREFLIGHT' reported a problem (continuing)"
      }
    fi
    ran=$((ran + 1))
    if [[ -z "$fn" ]]; then
      isc_log_warn "component '$id' has no install function — skipping"
      msg "WARN: component '$id' has no install function — skipping"
      continue
    fi
    if ! declare -F "$fn" >/dev/null 2>&1; then
      isc_log_warn "install function '$fn' for component '$id' is not defined — skipping"
      msg "WARN: install function '$fn' for component '$id' is not defined — skipping"
      failed+=("$id")
      continue
    fi
    isc_log_info "installing component: $label ($id) via $fn"
    msg "[$ISC_REPO_NAME] Installing component: $label ($id)"
    if ! "$fn"; then
      isc_log_error "component '$id' failed (continuing)"
      msg "WARN: component '$id' failed (continuing)"
      failed+=("$id")
    else
      isc_log_info "component '$id' completed"
    fi
  done
  # Optional postflight (e.g. audits, sudo-required summaries) after components.
  if (( ran > 0 )) && [[ -n "${ISC_POSTFLIGHT:-}" ]] \
     && declare -F "$ISC_POSTFLIGHT" >/dev/null 2>&1; then
    isc_log_debug "running postflight '$ISC_POSTFLIGHT'"
    "$ISC_POSTFLIGHT" || {
      isc_log_warn "postflight '$ISC_POSTFLIGHT' reported a problem (continuing)"
      msg "WARN: postflight '$ISC_POSTFLIGHT' reported a problem (continuing)"
    }
  fi

  if (( ran == 0 )); then
    isc_log_info "no components selected — nothing to do"
    msg "[$ISC_REPO_NAME] No components selected — nothing to do."
  fi
  if (( ${#failed[@]} > 0 )); then
    isc_log_error "components with failures: ${failed[*]}"
    msg "[$ISC_REPO_NAME] Components with failures: ${failed[*]}"
    return 1
  fi
  isc_log_info "run_selected completed successfully ($ran component(s))"
  return 0
}

# Print usage.
_isc_usage() {
  cat <<EOF
${ISC_REPO_NAME:-installer} — component-based installer

Usage:
  bash install.sh                 Interactive component selection (TTY), else defaults
  bash install.sh --default       Install all default-on components, no prompts
  bash install.sh --all           Install every component, no prompts
  bash install.sh --select a,b,c  Install exactly these component ids, no prompts
  bash install.sh --list-components  List components as: id<TAB>label<TAB>default
  bash install.sh --help          Show this help

Components:
$(_isc_list_components | sed 's/^/  /')
EOF
}

###############################################################################
# Interactive submenu (standalone, on a TTY)
###############################################################################

# Locate and source the shared menu engine, downloading it if necessary.
#
# Looks next to this runtime file first (the vendored copy), then falls back to
# downloading from the installation_scripts repository. Returns non-zero if the
# engine could not be made available.
_isc_load_menu() {
  declare -F cm_single_submenu >/dev/null 2>&1 && return 0
  local here menu
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  # Prefer the directory resolved by component_loader.sh, then this file's own
  # directory (the two are normally the same vendored/cloned location).
  local dir
  for dir in "${ISC_COMPONENT_LIB_DIR:-}" "$here"; do
    [[ -n "$dir" && -f "$dir/component_menu.sh" ]] || continue
    isc_log_debug "sourcing menu engine from local dir: $dir"
    # shellcheck source=/dev/null
    source "$dir/component_menu.sh" && return 0
  done
  local raw="${ISC_MENU_RAW_URL:-https://raw.githubusercontent.com/mikaeltorni/linux_installation_scripts_functions/master/component_menu.sh}"
  isc_log_debug "menu engine not found locally — downloading from $raw"
  local tmp
  tmp="$(mktemp 2>/dev/null)" || { isc_log_error "mktemp failed while fetching menu engine"; return 1; }
  if command -v curl >/dev/null 2>&1 && curl -fsSL "$raw" -o "$tmp" 2>/dev/null; then
    # shellcheck source=/dev/null
    source "$tmp" && { rm -f "$tmp"; return 0; }
  elif command -v wget >/dev/null 2>&1 && wget -qO "$tmp" "$raw" 2>/dev/null; then
    # shellcheck source=/dev/null
    source "$tmp" && { rm -f "$tmp"; return 0; }
  fi
  rm -f "$tmp"
  isc_log_error "could not load menu engine (no local copy and download failed)"
  return 1
}

# Build the CM_* arrays for this single repo and run the submenu.
#
# Echoes the selected ids (newline-separated) on stdout and returns 0 when the
# user accepted, or returns 1 when cancelled / the menu was unavailable.
_isc_interactive_select() {
  if ! _isc_load_menu; then
    isc_log_warn "interactive menu unavailable — caller will fall back to defaults"
    return 2
  fi
  local repo="${ISC_REPO_NAME:-repo}" id def
  CM_REPOS=("$repo")
  CM_REPO_LABEL[$repo]="${ISC_REPO_LABEL:-$repo}"
  CM_REPO_ENABLED[$repo]=1
  local ids=""
  while IFS= read -r id; do
    [[ -z "$id" ]] && continue
    ids+="$id "
    CM_COMP_LABEL[$repo|$id]="$(_isc_field "$id" 1)"
    def="$(_isc_field "$id" 2)"
    [[ "$def" == "on" ]] && CM_COMP_ON[$repo|$id]=1 || CM_COMP_ON[$repo|$id]=0
  done < <(_isc_all_ids)
  CM_COMP_IDS[$repo]="${ids% }"

  if cm_single_submenu "$repo"; then
    isc_log_info "interactive selection accepted for repo '$repo'"
    for id in ${CM_COMP_IDS[$repo]}; do
      [[ "${CM_COMP_ON[$repo|$id]:-0}" == "1" ]] && printf '%s\n' "$id"
    done
    return 0
  fi
  isc_log_info "interactive selection cancelled for repo '$repo'"
  return 1
}

###############################################################################
# Entry point
###############################################################################

# Main entry point for a component-based installer.
#
# Arguments:
#   $@ - command-line arguments (see usage).
#
# Returns:
#   The exit status of the selected operation.
component_main() {
  if [[ -z "${ISC_COMPONENTS:-}" ]]; then
    isc_log_error "ISC_COMPONENTS manifest is not defined"
    msg "ERROR: ISC_COMPONENTS manifest is not defined."
    return 2
  fi

  isc_log_info "component_main invoked for '${ISC_REPO_NAME:-installer}' with args: $*"
  local mode="" select_ids=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --list-components) _isc_list_components; return 0 ;;
      --default)         mode="default" ;;
      --all)             mode="all" ;;
      --select)          mode="select"; select_ids="${2:-}"; shift ;;
      --select=*)        mode="select"; select_ids="${1#*=}" ;;
      --help|-h)         _isc_usage; return 0 ;;
      *)                 isc_log_warn "ignoring unknown argument: $1"
                         msg "WARN: ignoring unknown argument: $1" ;;
    esac
    shift
  done
  isc_log_debug "resolved mode='${mode:-interactive}' select_ids='${select_ids}'"

  case "$mode" in
    default) _isc_run_selected "$(_isc_default_ids)"; return $? ;;
    all)     _isc_run_selected "$(_isc_all_ids)";     return $? ;;
    select)  _isc_run_selected "$select_ids";         return $? ;;
    "")
      # No mode requested. Use the interactive submenu on a real terminal,
      # otherwise fall back to the default-on set so piped/automated runs work.
      if [[ -t 0 && -t 1 ]]; then
        local chosen rc
        chosen="$(_isc_interactive_select)"; rc=$?
        if (( rc == 2 )); then
          isc_log_info "interactive menu unavailable — installing default components"
          msg "Interactive menu unavailable — installing default components."
          _isc_run_selected "$(_isc_default_ids)"; return $?
        fi
        if (( rc != 0 )); then
          isc_log_info "selection cancelled — nothing installed"
          msg "Selection cancelled — nothing installed."
          return 0
        fi
        _isc_run_selected "$chosen"; return $?
      else
        isc_log_info "no TTY — installing default components non-interactively"
        _isc_run_selected "$(_isc_default_ids)"; return $?
      fi
      ;;
  esac
}
