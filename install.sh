#!/usr/bin/env bash
# install.sh — deploy the shared installer component framework as modules.
#
# This repository (linux_installation_scripts_functions) is the single source of
# truth for the installer component-selection framework. Every other setup
# repository loads these files; this installer makes them available as installable
# modules in the same component-based way the rest of the installation_scripts
# chain does.
#
# CORE (always installed, never deselectable): the bootstrap loader and the
# logging helpers — installed unconditionally so the framework core works no
# matter which optional modules are chosen.
# OPTIONAL (default-on): the menu engine, the per-repository runtime, and the
# shared install-time helpers — each a selectable component (installer/components.sh).
#
# Usage:
#   bash install.sh                  # interactive submenu on a TTY, else defaults
#   bash install.sh --default        # core + all default-on modules, no prompts
#   bash install.sh --all            # core + every module, no prompts
#   bash install.sh --select menu    # core + exactly these module ids
#   bash install.sh --list-components # print: id<TAB>label<TAB>default
#
# Destination (override with ISC_INSTALL_DIR): the framework download cache,
# which is component_loader.sh's offline resolution fallback, so a consuming
# installer resolves the framework even with no source checkout present.

set -euo pipefail

TARGET_USER="${SUDO_USER:-$USER}"
TARGET_UID="$(id -u "$TARGET_USER")"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="/run/user/${TARGET_UID}"
DISPLAY_VAL="${DISPLAY:-:0}"
USER_BUS="unix:path=${RUNTIME_DIR}/bus"

# Where to deploy the framework. Default to the loader's offline download cache
# so installing this repo populates the resolution-step-#5 fallback.
ISC_INSTALL_DIR="${ISC_INSTALL_DIR:-${XDG_CACHE_HOME:-$TARGET_HOME/.cache}/installation_scripts/components}"

# Load the shared install-time helpers (msg/run_as_target/need_cmd) and logging.
# These files live right here, so source them directly — no resolution needed.
# shellcheck source=/dev/null
source "$SCRIPT_DIR/installer_helpers.sh"

# Framework-deployment functions and the optional-module manifest.
# shellcheck source=/dev/null
source "$SCRIPT_DIR/lib/framework_install.sh"

# Activate the component runtime from this very checkout, then load the manifest.
# shellcheck source=/dev/null
source "$SCRIPT_DIR/component_loader.sh"
ISC_FUNCTIONS_DIR="$SCRIPT_DIR" isc_activate_components
# shellcheck source=/dev/null
source "$SCRIPT_DIR/installer/components.sh"

# Execute the parsed deployment plan and install the core with every install selection.
# Parameters: none; consumes the parsed installer plan. Returns: operation exit status.
main() {
  printf 'parameters=none\n' >&2
  isc_plan_install
  if [[ "$ISC_PLAN_ACTION" == cancel ]]; then
    printf '0\n' >&2
    return 0
  fi
  if [[ "$ISC_PLAN_ACTION" == install ]]; then
    isc_install_core
  fi
  _isc_apply_plan "$ISC_ARGUMENT_ORIGIN"
  if [[ "$ISC_PLAN_ACTION" == install ]]; then
    isc_install_summary
    msg "Shared installer component framework deployment complete."
  fi
  printf '0\n' >&2
  return 0
}

# Parse once and execute queries and removals before planning any deployment.
if isc_route_readonly_args "$@"; then exit $?; fi
main
