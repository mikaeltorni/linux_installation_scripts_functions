#!/usr/bin/env bash
# minimal_standalone_bootstrap.sh - Declare CM_* and seed a demo standalone repo.
#
# Sources installation_config.sh and sets manifest-default selection state for
# isc_bootstrap_selection tests. Every CM_* key touched by the bootstrap path is
# declared so callers can run under set -u.

set -uo pipefail

FRAMEWORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
source "${FRAMEWORK_DIR}/component_menu.sh"
# shellcheck source=/dev/null
source "${FRAMEWORK_DIR}/installation_config.sh"

declare -gA CM_REPO_LABEL CM_REPO_ENABLED CM_REPO_AWARE
declare -gA CM_COMP_IDS CM_COMP_LABEL CM_COMP_SECTION CM_COMP_REQUIRES CM_COMP_ON
declare -gA CM_COMP_INSTALLED CM_COMP_UNINSTALL
declare -gA CM_COMP_FAVORITE_ELIGIBLE CM_COMP_FAVORITE_ON CM_COMP_FAVORITE_DESKTOPS
declare -gA CM_COMP_STARTUP_ELIGIBLE CM_COMP_STARTUP_ON CM_COMP_STARTUP_SPECS
declare -gA CM_COMP_WORKSPACE_ELIGIBLE CM_COMP_WORKSPACE CM_COMP_WORKSPACE_SPECS
declare -gA CM_COMP_STICKY_ELIGIBLE CM_COMP_STICKY_ON CM_COMP_STICKY_SPECS
declare -gA CM_COMP_CONFIGURE_ELIGIBLE CM_COMP_CONFIG_VALUE
declare -ga CM_REPOS

repo="${ISC_REPO_NAME:-demo}"
CM_REPOS=("$repo")
CM_REPO_LABEL[$repo]="${ISC_REPO_LABEL:-Demo}"
CM_REPO_ENABLED[$repo]=1
CM_REPO_AWARE[$repo]=1
CM_COMP_IDS[$repo]="alpha beta"

for id in alpha beta; do
  CM_COMP_LABEL[$repo|$id]="$id"
  CM_COMP_SECTION[$repo|$id]=""
  CM_COMP_REQUIRES[$repo|$id]=""
  CM_COMP_CONFIGURE_ELIGIBLE[$repo|$id]=0
  CM_COMP_CONFIG_VALUE[$repo|$id]=""
  CM_COMP_UNINSTALL[$repo|$id]=0
  CM_COMP_FAVORITE_ELIGIBLE[$repo|$id]=0
  CM_COMP_FAVORITE_ON[$repo|$id]=0
  CM_COMP_FAVORITE_DESKTOPS[$repo|$id]=""
  CM_COMP_STARTUP_ELIGIBLE[$repo|$id]=0
  CM_COMP_STARTUP_ON[$repo|$id]=0
  CM_COMP_STARTUP_SPECS[$repo|$id]=""
  CM_COMP_WORKSPACE_ELIGIBLE[$repo|$id]=0
  CM_COMP_WORKSPACE[$repo|$id]=0
  CM_COMP_WORKSPACE_SPECS[$repo|$id]=""
  CM_COMP_STICKY_ELIGIBLE[$repo|$id]=0
  CM_COMP_STICKY_ON[$repo|$id]=0
  CM_COMP_STICKY_SPECS[$repo|$id]=""
  CM_COMP_INSTALLED[$repo|$id]=0
done

# Manifest defaults: alpha on, beta off (matches typical ISC_COMPONENTS demo).
CM_COMP_ON[$repo|alpha]=1
CM_COMP_ON[$repo|beta]=0