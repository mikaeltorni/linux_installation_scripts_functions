#!/usr/bin/env bash
# installer_helpers.sh - Shared install-time helpers (single source of truth).
#
# This repository (linux_installation_scripts_functions) owns the reusable
# installer helpers that every setup repository previously redefined on its own
# (run_as_target, msg, need_cmd, apt_install, the sudo-skip reporting, and the
# session-bus / root guards). Consuming installers resolve and source this file
# via isc_load_helpers (component_loader.sh) instead of vendoring a copy, so a
# fix here reaches every standalone installer.
#
# Contract: the caller must define TARGET_USER, TARGET_HOME, RUNTIME_DIR,
# USER_BUS, and DISPLAY_VAL before invoking run_as_target/ensure_session_bus.
# A repository may still define repo-specific helpers (e.g. desktop-file lookup)
# in its own lib; this file holds only what was duplicated everywhere.
#
# Safe to source standalone: it loads the centralized logger when available and
# provides a no-op fallback when it is absent, so logging never aborts an
# installer.

if [[ -n "${ISC_HELPERS_SOURCED:-}" ]]; then
  return 0 2>/dev/null || true
fi
ISC_HELPERS_SOURCED=1

# Prefer the shared file logger from this framework checkout. Some older
# consuming repositories still provide their own log LEVEL MESSAGE helper; keep
# that as a compatibility input/output while routing this file's own diagnostics
# through the centralized isc_log_* API.
if ! declare -F isc_log >/dev/null 2>&1; then
  _isc_helpers_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd 2>/dev/null)" || _isc_helpers_dir=""
  if [[ -n "$_isc_helpers_dir" && -f "$_isc_helpers_dir/component_logging.sh" ]]; then
    # shellcheck source=/dev/null
    source "$_isc_helpers_dir/component_logging.sh"
  fi
  unset _isc_helpers_dir
fi
if ! declare -F isc_log >/dev/null 2>&1; then
  if declare -F log >/dev/null 2>&1; then
    isc_log() { log "$@"; }
  else
    isc_log() { :; }
  fi
fi
if ! declare -F isc_log_verbose >/dev/null 2>&1; then
  isc_log_verbose() { isc_log verbose "$@"; }
  isc_log_debug()   { isc_log debug   "$@"; }
  isc_log_info()    { isc_log info    "$@"; }
  isc_log_warn()    { isc_log warn    "$@"; }
  isc_log_error()   { isc_log error   "$@"; }
fi
if ! declare -F log >/dev/null 2>&1; then
  log() { isc_log "$@"; }
fi

# msg - Print a user-facing status line ("==> text") to stdout.
#   Args: $* - message text. Returns: 0.
msg() { printf "\n==> %s\n" "$*"; }

# need_cmd - Test whether a command is available on PATH.
#   Args: $1 - command name. Returns: 0 if present, non-zero otherwise.
need_cmd() { isc_log_debug "need_cmd: checking for '$1'"; command -v "$1" >/dev/null 2>&1; }

# is_root - Test whether the script runs with root privileges.
#   Args: none. Returns: 0 when root, non-zero otherwise.
is_root() { isc_log_debug "is_root: euid=$(id -u)"; [ "$(id -u)" -eq 0 ]; }

# Root-only steps skipped during a non-root run; reported at the end.
SUDO_REQUIRED_STEPS=()

# note_sudo_required - Record a skipped root-only step for the final report.
#   Args: $1 - human-readable description. Returns: 0.
note_sudo_required() {
  SUDO_REQUIRED_STEPS+=("$1")
  isc_log_warn "root-only step deferred: $1"
  msg "SKIP (requires sudo): $1"
}

# report_sudo_required - Print all root-only steps skipped this run, if any.
#   Args: none. Returns: 0.
report_sudo_required() {
  [ "${#SUDO_REQUIRED_STEPS[@]}" -eq 0 ] && return 0
  isc_log_warn "root-only steps still pending: ${SUDO_REQUIRED_STEPS[*]}"
  msg "The following steps still require root and were skipped:"
  printf '    - %s\n' "${SUDO_REQUIRED_STEPS[@]}"
  msg "Apply them with: sudo bash install.sh"
}

# apt_install - Ensure one or more apt packages are installed (idempotent).
#   Skips already-present packages and only refreshes the cache when something is
#   missing. When not root, records the step via note_sudo_required and returns 0
#   so a sudo-free run still completes.
#   Args: $@ - apt package names. Returns: 0 on success/deferral; non-zero when
#     apt-get is unavailable or the install fails.
apt_install() {
  local pkg missing=()
  for pkg in "$@"; do
    if ! dpkg -s "$pkg" >/dev/null 2>&1; then
      missing+=("$pkg")
    fi
  done

  if [ "${#missing[@]}" -eq 0 ]; then
    isc_log_debug "apt_install: all packages already installed: $*"
    return 0
  fi

  if ! need_cmd apt-get; then
    isc_log_error "apt_install: apt-get not available; cannot install ${missing[*]}"
    return 1
  fi

  if ! is_root; then
    note_sudo_required "apt install ${missing[*]}"
    return 0
  fi

  isc_log_info "Installing apt packages: ${missing[*]}"
  DEBIAN_FRONTEND=noninteractive apt-get update -y >/dev/null 2>&1 || \
    isc_log_warn "apt_install: 'apt-get update' failed; attempting install anyway"
  DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}"
}

# run_as_target - Run a command as TARGET_USER with that user's desktop session
#   environment (HOME, XDG_RUNTIME_DIR, D-Bus, DISPLAY) populated so that
#   gsettings/systemctl --user calls reach the live session. Uses sudo only when
#   the current user differs from the target, keeping the installer sudo-free in
#   the common standalone case.
#   Args: $@ - command and arguments. Returns: the command's exit status.
run_as_target() {
  isc_log_debug "run_as_target: $*"
  if [ "$(id -un)" = "$TARGET_USER" ]; then
    isc_log_debug "run_as_target: executing directly as $TARGET_USER"
    env \
      HOME="$TARGET_HOME" \
      USER="$TARGET_USER" \
      LOGNAME="$TARGET_USER" \
      XDG_RUNTIME_DIR="$RUNTIME_DIR" \
      DBUS_SESSION_BUS_ADDRESS="$USER_BUS" \
      DISPLAY="$DISPLAY_VAL" \
      "$@"
  else
    isc_log_debug "run_as_target: executing via sudo as $TARGET_USER"
    sudo -H -u "$TARGET_USER" env \
      HOME="$TARGET_HOME" \
      USER="$TARGET_USER" \
      LOGNAME="$TARGET_USER" \
      XDG_RUNTIME_DIR="$RUNTIME_DIR" \
      DBUS_SESSION_BUS_ADDRESS="$USER_BUS" \
      DISPLAY="$DISPLAY_VAL" \
      "$@"
  fi
}

# ensure_root - Abort unless running as root. For installers whose work is
#   inherently root-only (e.g. apt package installation).
#   Args: none. Exits 1 when not root.
ensure_root() {
  if [ "$(id -u)" -ne 0 ]; then
    isc_log_error "Please run with sudo: sudo bash $0"
    echo "Please run with sudo: sudo bash $0"
    exit 1
  fi
}

# ensure_session_bus - Abort if the target user has no live D-Bus session bus
#   (required for gsettings/systemctl --user to affect the running desktop).
#   Args: none. Exits 1 when the session bus socket is missing.
ensure_session_bus() {
  if [ ! -S "${RUNTIME_DIR}/bus" ]; then
    isc_log_error "No user session bus at ${RUNTIME_DIR}/bus"
    cat <<EOF
No user session bus at ${RUNTIME_DIR}/bus.
Open a terminal in ${TARGET_USER}'s *logged-in desktop* session and run:
  sudo bash $0
EOF
    exit 1
  fi
}
