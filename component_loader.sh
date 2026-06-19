#!/usr/bin/env bash
# component_loader.sh - Resolve and activate the shared installer component
# framework from a single source of truth.
#
# This repository (linux_installation_scripts_functions) owns the reusable
# installer selection framework: component_menu.sh (the pure-Bash TUI) and
# component_runtime.sh (the per-repository --list-components/--select/--default
# contract). Consuming repositories do NOT vendor copies of those files; instead
# each repository's install.sh sources this loader and calls
# isc_activate_components, which locates the framework next to a sibling
# checkout of this repository or downloads it on demand. Editing the framework
# here updates every standalone installer automatically.
#
# Resolution order for the library directory:
#   1. $ISC_COMPONENT_LIB_DIR        (explicit override)
#   2. $ISC_FUNCTIONS_DIR            (explicit path to this repo)
#   3. $SCRIPT_DIR/../linux_installation_scripts_functions   (sibling checkout)
#   4. $HOME/projects/linux_installation_scripts_functions   (default checkout)
#   5. download into $XDG_CACHE_HOME/installation_scripts/components
#
# Usage (from a consuming install.sh):
#   source "<sibling-or-curled>/component_loader.sh"
#   isc_activate_components            # sources the runtime (and menu on demand)
#   source "$SCRIPT_DIR/installer/components.sh"
#   component_main "$@"

if [[ -n "${ISC_LOADER_SOURCED:-}" ]]; then
  return 0 2>/dev/null || true
fi
ISC_LOADER_SOURCED=1

# Repository identity and download location. Override ISC_FUNCTIONS_REF to pin a
# branch/tag, or ISC_FUNCTIONS_RAW for a private mirror.
ISC_FUNCTIONS_REPO="${ISC_FUNCTIONS_REPO:-linux_installation_scripts_functions}"
ISC_FUNCTIONS_REF="${ISC_FUNCTIONS_REF:-master}"
ISC_FUNCTIONS_RAW="${ISC_FUNCTIONS_RAW:-https://raw.githubusercontent.com/mikaeltorni/${ISC_FUNCTIONS_REPO}/${ISC_FUNCTIONS_REF}}"

# isc_component_lib_dir - echo a directory that contains both component_menu.sh
# and component_runtime.sh, downloading them into a cache directory when no
# local checkout is available.
#
# Returns:
#   0 and prints the directory on success; non-zero when the library could not
#   be located or downloaded.
isc_component_lib_dir() {
  local d cache f
  for d in \
      "${ISC_COMPONENT_LIB_DIR:-}" \
      "${ISC_FUNCTIONS_DIR:-}" \
      "${SCRIPT_DIR:-}/../${ISC_FUNCTIONS_REPO}" \
      "${HOME}/projects/${ISC_FUNCTIONS_REPO}"; do
    [[ -n "$d" && -f "$d/component_runtime.sh" && -f "$d/component_menu.sh" ]] || continue
    ( cd "$d" && pwd )
    return 0
  done

  cache="${XDG_CACHE_HOME:-$HOME/.cache}/installation_scripts/components"
  mkdir -p "$cache" 2>/dev/null || return 1
  for f in component_menu.sh component_runtime.sh; do
    if [[ ! -f "$cache/$f" || "${ISC_FUNCTIONS_REFRESH:-0}" == "1" ]]; then
      if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$ISC_FUNCTIONS_RAW/$f" -o "$cache/$f" || return 1
      elif command -v wget >/dev/null 2>&1; then
        wget -qO "$cache/$f" "$ISC_FUNCTIONS_RAW/$f" || return 1
      else
        return 1
      fi
    fi
  done
  printf '%s' "$cache"
}

# isc_activate_components - resolve the framework and source component_runtime.sh
# so component_main and the menu become available. Exports ISC_COMPONENT_LIB_DIR
# so the runtime can locate component_menu.sh from the same place.
#
# Returns:
#   0 on success; non-zero (with an error message) when the framework could not
#   be loaded.
isc_activate_components() {
  local dir
  dir="$(isc_component_lib_dir)" || {
    echo "ERROR: could not resolve installer component framework (${ISC_FUNCTIONS_REPO})." >&2
    echo "       Clone ${ISC_FUNCTIONS_REPO} next to this repo, set ISC_FUNCTIONS_DIR, or enable network access." >&2
    return 1
  }
  export ISC_COMPONENT_LIB_DIR="$dir"
  # shellcheck source=/dev/null
  source "$dir/component_runtime.sh"
}

# isc_load_menu - source only the TUI engine (component_menu.sh). The master
# installer uses this directly to drive the aggregate two-level menu without
# needing the per-repository runtime.
#
# Returns:
#   0 on success; non-zero when the framework could not be loaded.
isc_load_menu() {
  declare -F cm_aggregate_menu >/dev/null 2>&1 && return 0
  local dir
  dir="$(isc_component_lib_dir)" || {
    echo "ERROR: could not resolve installer component framework (${ISC_FUNCTIONS_REPO})." >&2
    return 1
  }
  export ISC_COMPONENT_LIB_DIR="$dir"
  # shellcheck source=/dev/null
  source "$dir/component_menu.sh"
}
