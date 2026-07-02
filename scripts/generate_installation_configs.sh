#!/usr/bin/env bash
# generate_installation_configs.sh - Seed installation_configs/default.json and empty.json.
#
# Usage:
#   bash scripts/generate_installation_configs.sh [REPO_ROOT]
#   bash scripts/generate_installation_configs.sh --master /path/to/installation_scripts

set -euo pipefail

FRAMEWORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MASTER_MODE=0
TARGET=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --master) MASTER_MODE=1; shift ;;
    *) TARGET="$1"; shift ;;
  esac
done

write_empty_standalone() {
  local repo_name="$1" out_dir="$2"
  mkdir -p "$out_dir"
  cat >"$out_dir/empty.json" <<EOF
{
  "components": {},
  "repo": "$repo_name",
  "schema_version": 1,
  "scope": "standalone"
}
EOF
}

write_default_standalone() {
  local repo_root="$1" repo_name="$2" out_dir="$3"
  mkdir -p "$out_dir"
  local tmp
  tmp="$(mktemp)"
  (
    cd "$repo_root"
    export SCRIPT_DIR="$repo_root"
    export ISC_CONFIG_REPO_ROOT="$repo_root"
    export ISC_RECEIPT_DIR="${ISC_RECEIPT_DIR:-/tmp/isc-gen-$$}"
    export ISC_CONFIG_SKIP_APPLY=1
    mkdir -p "$ISC_RECEIPT_DIR"
    # shellcheck source=/dev/null
    source "$FRAMEWORK_DIR/component_loader.sh"
    isc_activate_components
    # shellcheck source=/dev/null
    source "$repo_root/installer/components.sh"
    component_main --export-selection >"$tmp" 2>/dev/null || true
  ) || true
  if [[ -s "$tmp" ]]; then
    cp "$tmp" "$out_dir/default.json"
  else
    cat >"$out_dir/default.json" <<EOF
{
  "components": {},
  "repo": "$repo_name",
  "schema_version": 1,
  "scope": "standalone"
}
EOF
  fi
  rm -f "$tmp"
  write_empty_standalone "$repo_name" "$out_dir"
}

write_master_configs() {
  local master_root="$1" out_dir="$2" projects="${PROJECTS_DIR:-$HOME/projects}"
  mkdir -p "$out_dir"
  cat >"$out_dir/empty.json" <<'EOF'
{
  "repos": {},
  "schema_version": 1,
  "scope": "master"
}
EOF
  local tmp
  tmp="$(mktemp)"
  (
    cd "$master_root"
    export SCRIPT_DIR="$master_root"
    export ISC_CONFIG_REPO_ROOT="$master_root"
    export PROJECTS_DIR="$projects"
    export TARGET_HOME="${TARGET_HOME:-$HOME}"
    export INSTALLER_AUTH=0
    # shellcheck source=/dev/null
    source "$master_root/scripts/repository_manifest.sh"
    # shellcheck source=/dev/null
    source "$master_root/scripts/installer_helpers.sh"
    # shellcheck source=/dev/null
    source "$master_root/scripts/component_selection.sh"
    for repo in "${INSTALL_REPOS[@]}"; do
      _cs_load_repo "$repo"
    done
    cs_export_selection_json >"$tmp" 2>/dev/null || true
  ) || true
  if [[ -s "$tmp" ]]; then
    cp "$tmp" "$out_dir/default.json"
  else
    cat >"$out_dir/default.json" <<'EOF'
{
  "repos": {},
  "schema_version": 1,
  "scope": "master"
}
EOF
  fi
  rm -f "$tmp"
}

generate_repo() {
  local repo_root="$1"
  [[ -f "$repo_root/installer/components.sh" ]] || return 0
  local repo_name
  repo_name="$(basename "$repo_root")"
  # shellcheck source=/dev/null
  local isc_name
  isc_name="$(grep -m1 '^ISC_REPO_NAME=' "$repo_root/installer/components.sh" | cut -d'"' -f2)"
  [[ -n "$isc_name" ]] || isc_name="$repo_name"
  write_default_standalone "$repo_root" "$isc_name" "$repo_root/installation_configs"
  echo "  $repo_name"
}

main() {
  if [[ "$MASTER_MODE" -eq 1 ]]; then
    local master="${TARGET:-$HOME/projects/installation_scripts}"
    write_master_configs "$master" "$master/installation_configs" "${PROJECTS_DIR:-$HOME/projects}"
    echo "master: $master/installation_configs"
    return 0
  fi

  if [[ -n "$TARGET" ]]; then
    generate_repo "$TARGET"
    return 0
  fi

  generate_repo "$FRAMEWORK_DIR"
  local projects="${PROJECTS_DIR:-$HOME/projects}" d
  for d in "$projects"/*/; do
    [[ -f "${d}installer/components.sh" ]] && generate_repo "${d%/}"
  done
  write_master_configs "$projects/installation_scripts" "$projects/installation_scripts/installation_configs" "$projects"
  echo "done"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi