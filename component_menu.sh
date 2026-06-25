#!/usr/bin/env bash
# component_menu.sh - Shared pure-Bash TUI for installer component selection.
#
# This is the single source of truth for the interactive selection menu used by
# the master installer (a two-level repo -> component menu) and by each child
# repository's standalone installer (a single-repo component submenu). It has no
# external dependencies beyond a POSIX terminal and Bash, so it works on a fresh
# Ubuntu install before any packages are added.
#
# The menu operates on a small set of well-known global arrays that the caller
# populates before invoking an entry point:
#
#   CM_REPOS              - ordered array of repo ids (top-level rows)
#   CM_REPO_LABEL[repo]   - human label for a repo row
#   CM_REPO_ENABLED[repo] - 1 when the whole repo is enabled, 0 when disabled
#   CM_COMP_IDS[repo]     - space-separated component ids belonging to a repo
#   CM_COMP_LABEL[repo|id]- human label for a component
#   CM_COMP_ON[repo|id]   - 1 when that component is selected, 0 otherwise
#   CM_COMP_INSTALLED[repo|id] - 1 when already installed on this machine
#                           (optional; defaults to 0 — drives the install-state
#                           markers and the reconfigure/uninstall actions)
#   CM_COMP_UNINSTALL[repo|id] - 1 when the user marked an installed component
#                           for removal with the [u] key (optional)
#   CM_COMP_FAVORITE_ELIGIBLE[repo|id] - 1 when a component can be pinned as a
#                           GNOME favourite app from the program menu
#   CM_COMP_FAVORITE_ON[repo|id] - 1 when the component should be included in
#                           the generated favourite-apps list
#
# Per-component states shown in the checklist:
#   [ ] absent, will be skipped          [x] absent, will be installed
#   [✓] installed, left as-is            [~] installed, will be reconfigured
#   [✗] installed, will be uninstalled
#   [F] app component selected for dock favourites
# SPACE toggles install/reconfigure, [f] toggles dock favourite selection for
# eligible app components, [u] toggles uninstall of an installed component, and
# [r] marks every installed component for reconfigure.
#
# Entry points (all mutate the arrays in place):
#   cm_aggregate_menu     - two-level menu: rows are repos; SPACE enables or
#                           disables a whole repo; RIGHT enters the repo's
#                           component submenu; ENTER accepts; q/Esc cancels.
#   cm_single_submenu REPO- flat component checklist for one repo; ENTER accepts
#                           (returns 0); q/Esc cancels (returns 1).
#
# Usage:
#   source "<dir>/component_menu.sh"
#   ... populate CM_* arrays ...
#   cm_aggregate_menu   # or: cm_single_submenu "<repo>"

# Guard against double-sourcing.
if [[ -n "${CM_MENU_SOURCED:-}" ]]; then
  return 0 2>/dev/null || true
fi
CM_MENU_SOURCED=1

# Ensure the centralized logging helpers exist. Source component_logging.sh from
# next to this engine when present, otherwise define silent no-op stubs so every
# isc_log* call below is always safe and never corrupts the TUI on the terminal.
if ! declare -F isc_log >/dev/null 2>&1; then
  _cm_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd 2>/dev/null)" || _cm_dir=""
  if [[ -n "$_cm_dir" && -f "$_cm_dir/component_logging.sh" ]]; then
    # shellcheck source=/dev/null
    source "$_cm_dir/component_logging.sh"
  fi
  unset _cm_dir
fi
if ! declare -F isc_log >/dev/null 2>&1; then
  isc_log()         { :; }
  isc_log_verbose() { :; }
  isc_log_debug()   { :; }
  isc_log_info()    { :; }
  isc_log_warn()    { :; }
  isc_log_error()   { :; }
fi

# Associative state shared with callers. Declared here so sourcing alone makes
# them available; callers may also declare them, which is harmless.
declare -gA CM_REPO_LABEL CM_REPO_ENABLED CM_COMP_IDS CM_COMP_LABEL CM_COMP_ON 2>/dev/null || true
declare -gA CM_COMP_INSTALLED CM_COMP_UNINSTALL 2>/dev/null || true
declare -gA CM_COMP_FAVORITE_ELIGIBLE CM_COMP_FAVORITE_ON 2>/dev/null || true
declare -ga CM_REPOS 2>/dev/null || true

###############################################################################
# Terminal helpers
###############################################################################

# Hide the terminal cursor for clean rendering.
cm_hide_cursor() { printf '\033[?25l'; }

# Restore the terminal cursor.
cm_show_cursor() { printf '\033[?25h'; }

# Clear the screen and move the cursor to the home position.
cm_clear() { printf '\033[2J\033[H'; }

# Read a single keypress and echo a normalized token.
#
# Returns one of: UP DOWN LEFT RIGHT SPACE ENTER ESC QUIT ALL NONE FAVORITE OTHER.
cm_read_key() {
  local key rest
  IFS= read -rsn1 key 2>/dev/null || { echo QUIT; return; }
  case "$key" in
    '')   echo ENTER ;;
    ' ')  echo SPACE ;;
    $'\x1b')
      # Possible escape sequence (arrow keys). Read the rest with a short
      # timeout so a bare Esc is still recognized.
      read -rsn2 -t 0.005 rest 2>/dev/null || rest=''
      case "$rest" in
        '[A'|'OA') echo UP ;;
        '[B'|'OB') echo DOWN ;;
        '[C'|'OC') echo RIGHT ;;
        '[D'|'OD') echo LEFT ;;
        '')        echo ESC ;;
        *)         echo OTHER ;;
      esac
      ;;
    q|Q) echo QUIT ;;
    a|A) echo ALL ;;
    n|N) echo NONE ;;
    f|F) echo FAVORITE ;;
    u|U) echo UNINSTALL ;;
    r|R) echo RECONFIG ;;
    *)   echo OTHER ;;
  esac
}

###############################################################################
# Install-state helpers
###############################################################################

# Echo the number of installed components for a repo (CM_COMP_INSTALLED==1).
#
# Arguments:
#   $1 - repo id whose installed components are counted.
cm_repo_installed_count() {
  local repo="$1" id count=0
  for id in ${CM_COMP_IDS[$repo]:-}; do
    [[ -n "$id" ]] || continue
    [[ "${CM_COMP_INSTALLED[$repo|$id]:-0}" == "1" ]] && count=$((count + 1))
  done
  printf '%s' "$count"
}

###############################################################################
# Count helpers
###############################################################################

# Echo the number of enabled components for a repo.
#
# Arguments:
#   $1 - repo id whose enabled components are counted.
#
# Returns:
#   0; prints the count of components with CM_COMP_ON set to 1.
cm_repo_on_count() {
  local repo="$1" id count=0
  for id in ${CM_COMP_IDS[$repo]:-}; do
    [[ -n "$id" ]] || continue
    [[ "${CM_COMP_ON[$repo|$id]:-0}" == "1" ]] && count=$((count + 1))
  done
  printf '%s' "$count"
}

# Echo the total number of components for a repo.
#
# Arguments:
#   $1 - repo id whose components are counted.
#
# Returns:
#   0; prints the total number of component ids registered for the repo.
cm_repo_total_count() {
  local repo="$1" id count=0
  for id in ${CM_COMP_IDS[$repo]:-}; do
    [[ -n "$id" ]] && count=$((count + 1))
  done
  printf '%s' "$count"
}

# Copy non-empty component ids for a repo into a caller-provided array.
#
# Arguments:
#   $1 - repo id
#   $2 - name of the destination array variable (nameref)
cm_comp_ids_for_repo() {
  local repo="$1" raw
  local -n _dest="$2"
  _dest=()
  for raw in ${CM_COMP_IDS[$repo]:-}; do
    [[ -n "$raw" ]] && _dest+=("$raw")
  done
}

###############################################################################
# Submenu (component checklist for a single repo)
###############################################################################

# Render the component checklist for one repo.
#
# Arguments:
#   $1 - repo id
#   $2 - currently selected row index
#   $3 - title line
#   $4 - footer/help line
cm_render_submenu() {
  local repo="$1" sel="$2" title="$3" footer="$4"
  local -a ids=()
  local i id mark box label on total inst tag term_rows chrome_rows footer_rows
  local visible_rows offset end indicators
  cm_comp_ids_for_repo "$repo" ids
  if (( ${#ids[@]} > 0 )); then
    if (( sel < 0 )); then sel=0; fi
    if (( sel >= ${#ids[@]} )); then sel=$(( ${#ids[@]} - 1 )); fi
  else
    sel=0
  fi
  on="$(cm_repo_on_count "$repo")"
  total="$(cm_repo_total_count "$repo")"
  inst="$(cm_repo_installed_count "$repo")"
  term_rows="${LINES:-}"
  [[ "$term_rows" =~ ^[0-9]+$ ]] || term_rows="$(tput lines 2>/dev/null || printf '24')"
  # Title, status, blank, and footer consume fixed rows; scroll hints add one
  # line each so the selected row never renders past the terminal bottom.
  chrome_rows=4
  footer_rows=2
  visible_rows=$((term_rows - chrome_rows - footer_rows))
  (( visible_rows < 1 )) && visible_rows=1
  offset=0
  if (( sel >= visible_rows )); then
    offset=$((sel - visible_rows + 1))
  fi
  end=$((offset + visible_rows))
  (( end > ${#ids[@]} )) && end=${#ids[@]}
  indicators=0
  (( offset > 0 )) && indicators=$((indicators + 1))
  (( end < ${#ids[@]} )) && indicators=$((indicators + 1))
  if (( indicators > 0 )); then
    visible_rows=$((term_rows - chrome_rows - footer_rows - indicators))
    (( visible_rows < 1 )) && visible_rows=1
    offset=0
    if (( sel >= visible_rows )); then
      offset=$((sel - visible_rows + 1))
    fi
    end=$((offset + visible_rows))
    (( end > ${#ids[@]} )) && end=${#ids[@]}
  fi
  cm_clear
  printf '  \033[1m%s\033[0m\n' "$title"
  if (( inst > 0 )); then
    printf '  \033[2m%s — %s/%s selected, %s/%s already installed\033[0m\n\n' \
      "${CM_REPO_LABEL[$repo]:-$repo}" "$on" "$total" "$inst" "$total"
  else
    printf '  \033[2m%s — %s/%s selected\033[0m\n\n' "${CM_REPO_LABEL[$repo]:-$repo}" "$on" "$total"
  fi
  if (( offset > 0 )); then
    printf '     \033[2m... %s more above ...\033[0m\n' "$offset"
  fi
  for ((i = offset; i < end; i++)); do
    id="${ids[$i]}"
    if [[ "$i" == "$sel" ]]; then mark='\033[36m›\033[0m'; else mark=' '; fi
    label="${CM_COMP_LABEL[$repo|$id]:-$id}"
    tag=''
    if [[ "${CM_COMP_UNINSTALL[$repo|$id]:-0}" == "1" ]]; then
      box='[\033[31m✗\033[0m]'; tag=' \033[31m(uninstall)\033[0m'
    elif [[ "${CM_COMP_FAVORITE_ON[$repo|$id]:-0}" == "1" ]]; then
      box='[\033[36mF\033[0m]'
      if [[ "${CM_COMP_INSTALLED[$repo|$id]:-0}" == "1" ]]; then
        tag=' \033[2m(installed, favourite)\033[0m'
      else
        tag=' \033[36m(favourite)\033[0m'
      fi
    elif [[ "${CM_COMP_INSTALLED[$repo|$id]:-0}" == "1" ]]; then
      if [[ "${CM_COMP_ON[$repo|$id]:-0}" == "1" ]]; then
        box='[\033[33m~\033[0m]'; tag=' \033[33m(reconfigure)\033[0m'
      else
        box='[\033[32m✓\033[0m]'; tag=' \033[2m(installed)\033[0m'
      fi
    else
      if [[ "${CM_COMP_ON[$repo|$id]:-0}" == "1" ]]; then box='[\033[32mx\033[0m]'; else box='[ ]'; fi
    fi
    printf '   %b %b %s%b\n' "$mark" "$box" "$label" "$tag"
  done
  if (( end < ${#ids[@]} )); then
    printf '     \033[2m... %s more below ...\033[0m\n' "$((${#ids[@]} - end))"
  fi
  printf '\n  \033[2m%s\033[0m\n' "$footer"
}

# Drive the component checklist for one repo until the user leaves it.
#
# Arguments:
#   $1 - repo id
#   $2 - "standalone" to make ENTER accept and return 0 / q-Esc return 1, or
#        "embedded" to make ENTER and LEFT return 0 (back to the parent menu).
#
# Returns:
#   0 when accepted / returned to parent; 1 when cancelled in standalone mode.
cm_submenu_loop() {
  local repo="$1" mode="${2:-embedded}"
  local -a ids=()
  local sel=0 key id title footer
  cm_comp_ids_for_repo "$repo" ids
  title="Configure components"
  if [[ "$mode" == "standalone" ]]; then
    footer="[↑/↓] move  [space] toggle  [f] favourite  [u] uninstall  [r] reconfigure all  [a] all  [n] none  [enter] apply  [q] cancel"
  else
    footer="[↑/↓] move  [space] toggle  [f] favourite  [u] uninstall  [r] reconfigure all  [a] all  [n] none  [←/enter] back"
    cm_show_cursor
  fi
  if (( ${#ids[@]} == 0 )); then
    cm_clear
    printf '  \033[1m%s\033[0m\n\n' "$title"
    printf '  \033[2mNo selectable components for %s.\033[0m\n\n' "${CM_REPO_LABEL[$repo]:-$repo}"
    printf '  \033[2m%s\033[0m\n' "$footer"
    cm_read_key >/dev/null
    return 0
  fi
  while true; do
    (( sel < 0 )) && sel=0
    (( ${#ids[@]} > 0 && sel >= ${#ids[@]} )) && sel=$(( ${#ids[@]} - 1 ))
    cm_render_submenu "$repo" "$sel" "$title" "$footer"
    key="$(cm_read_key)"
    case "$key" in
      UP)    sel=$((sel - 1)) ;;
      DOWN)  sel=$((sel + 1)) ;;
      SPACE)
        id="${ids[$sel]:-}"
        [[ -z "$id" ]] && continue
        # SPACE selects a component to apply (install if absent, reconfigure if
        # installed) and always clears any pending uninstall mark.
        CM_COMP_UNINSTALL[$repo|$id]=0
        if [[ "${CM_COMP_ON[$repo|$id]:-0}" == "1" ]]; then
          CM_COMP_ON[$repo|$id]=0
        else
          CM_COMP_ON[$repo|$id]=1
        fi
        ;;
      UNINSTALL)
        id="${ids[$sel]:-}"
        [[ -z "$id" ]] && continue
        # Uninstall only applies to installed components; toggling it clears the
        # apply/reconfigure selection so the two actions never conflict.
        [[ "${CM_COMP_INSTALLED[$repo|$id]:-0}" == "1" ]] || continue
        if [[ "${CM_COMP_UNINSTALL[$repo|$id]:-0}" == "1" ]]; then
          CM_COMP_UNINSTALL[$repo|$id]=0
        else
          CM_COMP_UNINSTALL[$repo|$id]=1
          CM_COMP_ON[$repo|$id]=0
          CM_COMP_FAVORITE_ON[$repo|$id]=0
        fi
        ;;
      FAVORITE)
        id="${ids[$sel]:-}"
        [[ -z "$id" ]] && continue
        [[ "${CM_COMP_FAVORITE_ELIGIBLE[$repo|$id]:-0}" == "1" ]] || continue
        CM_COMP_UNINSTALL[$repo|$id]=0
        if [[ "${CM_COMP_FAVORITE_ON[$repo|$id]:-0}" == "1" ]]; then
          CM_COMP_FAVORITE_ON[$repo|$id]=0
        else
          CM_COMP_FAVORITE_ON[$repo|$id]=1
        fi
        ;;
      RECONFIG)
        # Mark every installed component for reconfigure (idempotent re-apply).
        for id in "${ids[@]}"; do
          if [[ "${CM_COMP_INSTALLED[$repo|$id]:-0}" == "1" ]]; then
            CM_COMP_ON[$repo|$id]=1
            CM_COMP_UNINSTALL[$repo|$id]=0
          fi
        done
        ;;
      ALL)  for id in "${ids[@]}"; do CM_COMP_ON[$repo|$id]=1; CM_COMP_UNINSTALL[$repo|$id]=0; done ;;
      NONE) for id in "${ids[@]}"; do CM_COMP_ON[$repo|$id]=0; done ;;
      LEFT)
        [[ "$mode" == "embedded" ]] && return 0
        ;;
      ENTER) return 0 ;;
      ESC|QUIT)
        [[ "$mode" == "standalone" ]] && return 1
        return 0
        ;;
    esac
  done
}

# Public: run a standalone single-repo component submenu.
#
# Arguments:
#   $1 - repo id
#
# Returns:
#   0 when the user accepted (install), 1 when cancelled.
cm_single_submenu() {
  local repo="$1"
  isc_log_debug "opening standalone submenu for repo '$repo'"
  cm_hide_cursor
  trap 'cm_show_cursor' RETURN
  cm_submenu_loop "$repo" standalone
  local rc=$?
  cm_show_cursor
  cm_clear
  trap - RETURN
  isc_log_debug "standalone submenu for repo '$repo' closed with rc=$rc"
  return $rc
}

###############################################################################
# Aggregate menu (repos as rows with submenu drill-down)
###############################################################################

# Render the top-level repo menu.
#
# Arguments:
#   $1 - currently selected row index
cm_render_aggregate() {
  local sel="$1"
  local i repo mark box label on total status term_rows chrome_rows footer_rows
  local visible_rows offset end indicators
  if (( sel < 0 )); then sel=0; fi
  if (( sel >= ${#CM_REPOS[@]} )); then sel=$(( ${#CM_REPOS[@]} - 1 )); fi
  term_rows="${LINES:-}"
  [[ "$term_rows" =~ ^[0-9]+$ ]] || term_rows="$(tput lines 2>/dev/null || printf '24')"
  chrome_rows=3
  footer_rows=2
  visible_rows=$((term_rows - chrome_rows - footer_rows))
  (( visible_rows < 1 )) && visible_rows=1
  offset=0
  if (( sel >= visible_rows )); then
    offset=$((sel - visible_rows + 1))
  fi
  end=$((offset + visible_rows))
  (( end > ${#CM_REPOS[@]} )) && end=${#CM_REPOS[@]}
  indicators=0
  (( offset > 0 )) && indicators=$((indicators + 1))
  (( end < ${#CM_REPOS[@]} )) && indicators=$((indicators + 1))
  if (( indicators > 0 )); then
    visible_rows=$((term_rows - chrome_rows - footer_rows - indicators))
    (( visible_rows < 1 )) && visible_rows=1
    offset=0
    if (( sel >= visible_rows )); then
      offset=$((sel - visible_rows + 1))
    fi
    end=$((offset + visible_rows))
    (( end > ${#CM_REPOS[@]} )) && end=${#CM_REPOS[@]}
  fi
  cm_clear
  printf '  \033[1mInstallation Components\033[0m\n'
  printf '  \033[2mSelect what to install. Disabled repositories are skipped entirely.\033[0m\n\n'
  if (( offset > 0 )); then
    printf '     \033[2m... %s more above ...\033[0m\n' "$offset"
  fi
  for ((i = offset; i < end; i++)); do
    repo="${CM_REPOS[$i]}"
    if [[ "$i" == "$sel" ]]; then mark='\033[36m›\033[0m'; else mark=' '; fi
    if [[ "${CM_REPO_ENABLED[$repo]:-0}" == "1" ]]; then box='[\033[32mx\033[0m]'; else box='[ ]'; fi
    label="${CM_REPO_LABEL[$repo]:-$repo}"
    total="$(cm_repo_total_count "$repo")"
    if [[ "${CM_REPO_ENABLED[$repo]:-0}" == "1" ]]; then
      on="$(cm_repo_on_count "$repo")"
      if (( total > 0 )); then
        local inst
        inst="$(cm_repo_installed_count "$repo")"
        if (( inst > 0 )); then
          status="$(printf '(%s/%s, \033[32m%s installed\033[0m) \033[36m›\033[0m' "$on" "$total" "$inst")"
        else
          status="$(printf '(%s/%s) \033[36m›\033[0m' "$on" "$total")"
        fi
      else
        status='(no options)'
      fi
    else
      status='\033[2mdisabled\033[0m'
    fi
    printf '   %b %b %-44s %b\n' "$mark" "$box" "$label" "$status"
  done
  if (( end < ${#CM_REPOS[@]} )); then
    printf '     \033[2m... %s more below ...\033[0m\n' "$((${#CM_REPOS[@]} - end))"
  fi
  printf '\n  \033[2m[↑/↓] move   [space] enable/disable   [→] configure (incl. reconfigure/uninstall)   [enter] apply   [q] cancel\033[0m\n'
}

# Public: run the two-level aggregate menu.
#
# Returns:
#   0 when the user accepted the selection (ENTER); 1 when cancelled (q/Esc).
cm_aggregate_menu() {
  local sel=0 key repo
  isc_log_debug "opening aggregate menu with ${#CM_REPOS[@]} repo row(s)"
  cm_hide_cursor
  while true; do
    (( sel < 0 )) && sel=0
    (( sel >= ${#CM_REPOS[@]} )) && sel=$(( ${#CM_REPOS[@]} - 1 ))
    cm_render_aggregate "$sel"
    key="$(cm_read_key)"
    repo="${CM_REPOS[$sel]:-}"
    case "$key" in
      UP)    sel=$((sel - 1)) ;;
      DOWN)  sel=$((sel + 1)) ;;
      SPACE)
        [[ -z "$repo" ]] && continue
        if [[ "${CM_REPO_ENABLED[$repo]:-0}" == "1" ]]; then
          CM_REPO_ENABLED[$repo]=0
        else
          CM_REPO_ENABLED[$repo]=1
        fi
        ;;
      RIGHT)
        [[ -z "$repo" ]] && continue
        [[ "${CM_REPO_ENABLED[$repo]:-0}" != "1" ]] && continue
        [[ "$(cm_repo_total_count "$repo")" == "0" ]] && continue
        cm_submenu_loop "$repo" embedded
        cm_hide_cursor
        ;;
      ENTER)
        isc_log_info "aggregate menu accepted"
        cm_show_cursor; cm_clear
        return 0
        ;;
      ESC|QUIT)
        isc_log_info "aggregate menu cancelled"
        cm_show_cursor; cm_clear
        return 1
        ;;
    esac
  done
}
