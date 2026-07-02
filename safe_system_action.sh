#!/usr/bin/env bash
# Guard reboot and poweroff behind an audible, abortable ten-second countdown.
#
# Usage: safe_system_action.sh reboot|poweroff
# Ctrl+C or SIGTERM during the countdown exits without invoking the action.

set -euo pipefail

action="${1:-}"
case "$action" in
  reboot) action_command=(systemctl reboot); action_label="Rebooting" ;;
  poweroff) action_command=(systemctl poweroff); action_label="Powering off" ;;
  *) printf 'Usage: %s reboot|poweroff\n' "$0" >&2; exit 2 ;;
esac

find_beep_file() {
  local script_dir candidate
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  for candidate in \
    "${SAFE_SYSTEM_ACTION_BEEP_FILE:-}" \
    "$script_dir/../phrase_automation/sounds/command.mp3" \
    "${HOME:-}/projects/phrase_automation/sounds/command.mp3"; do
    [[ -n "$candidate" && -f "$candidate" ]] && { printf '%s' "$candidate"; return 0; }
  done
  return 1
}

beep_file="$(find_beep_file || true)"
beep_pid=""

play_beep() {
  if [[ -n "$beep_file" ]] && command -v ffplay >/dev/null 2>&1; then
    ffplay -nodisp -autoexit -loglevel quiet "$beep_file" </dev/null >/dev/null 2>&1 &
    beep_pid=$!
  else
    printf '\a' >&2
  fi
}

cancel_action() {
  [[ -n "$beep_pid" ]] && kill "$beep_pid" 2>/dev/null || true
  printf '\n%s cancelled; no system action was requested.\n' "$action_label" >&2
  exit 130
}
trap 'cancel_action' INT TERM

printf '%s in 10 seconds. Press Ctrl+C to cancel.\n' "$action_label"
for second in {10..1}; do
  printf '%s\n' "$second"
  play_beep
  sleep 1
done

printf "0 %s\n" "$action_label"
for _ in 1 2 3 4; do
  play_beep
  sleep 0.16
done

trap - INT TERM
exec "${action_command[@]}"
