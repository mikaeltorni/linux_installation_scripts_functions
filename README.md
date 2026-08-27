# linux_installation_scripts_functions

> Part of [installation_scripts](https://github.com/mikaeltorni/installation_scripts) — the shared, pure-Bash installer component-selection framework for the Ubuntu 24.04 desktop setup chain. Tested on Ubuntu 24.04.4 LTS; the Bash framework is portable to any system with Bash 4+ (macOS/WSL untested).

Shared, reusable installer functions for the
[`installation_scripts`](https://github.com/mikaeltorni/installation_scripts)
Ubuntu desktop setup chain. This repository is the **single source of truth** for
the interactive installer component-selection framework. The master installer
and every standalone repository installer load these files instead of vendoring
their own copies, so a change here updates all of them at once.

## Repository dependencies

This repository **is** the shared installer component framework, so it depends
on no other setup repository. Every component-aware installer in the chain
depends on *it* — loaded from a sibling checkout when present, otherwise
downloaded on demand — so a missing checkout never blocks an installation.

See the full cross-repository map in
[installation_scripts/DEPENDENCIES.md](https://github.com/mikaeltorni/installation_scripts/blob/master/DEPENDENCIES.md).

## What's here

| File | Purpose |
|---|---|
| `component_menu.sh` | Pure-Bash TUI engine: a two-level selection menu (repository rows with enable/disable, per-repository component submenus, and live `on/total` counts). No external dependencies. |
| `component_runtime.sh` | The per-repository installer contract: `--list-components`, `--select id,…`, `--default`, `--all`, an interactive submenu, and optional `ISC_CORE` / `ISC_PREFLIGHT` / `ISC_POSTFLIGHT` hooks. |
| `monitor_layout.sh` / `monitor_layout.py` | Shared display-monitor discovery. `isc_list_monitors` prints `number<TAB>connector<TAB>name<TAB>primary<TAB>x<TAB>y<TAB>width<TAB>height` per monitor, numbered exactly like the GNOME Settings → Displays panel (the Mutter `DisplayConfig` order), so installers, menus, and Shell extensions all agree on what "monitor 2" means. `ISC_MONITOR_LIST` overrides detection for headless runs and tests. |
| `repeatable_fields.py` | Shared one-based row mutations for repository-owned configurators that add repeated values and edit boolean/group metadata. `isc_load_helpers` exports its installed path as `ISC_REPEATABLE_FIELDS_PY`. |

Component manifests may use a tenth `monitor` field (`1`-`9`, or `-` for none)
declaring the display monitor an application should open on. The shared submenu
shows `[m] monitor` for those rows and cycles the assignment `none → 1 → … → N`
over the detected monitors; the master installer serializes the result into the
per-application placement rules. The action is hidden when only one monitor is
detected, or when the layout cannot be read at all (no GNOME session bus).

Component manifests may use a ninth `configure_fn` field. The shared submenu
shows `[→] details` for those rows and invokes the repository-owned screen via
`--configure-component ID`; `--list-configurable-components` lets the aggregate
master menu discover the same nested screens without sourcing child internals.
| `component_loader.sh` | Resolves and activates the framework from a sibling checkout or by downloading it; exposes `isc_activate_components`. |
| `component_logging.sh` | Centralized, dependency-free leveled logging (`verbose`/`debug`/`info`/`warn`/`error`) written to a per-repository `.log/` file with timestamps and a context tag. Sourced automatically by the loader, runtime, and menu; degrades to silent no-ops when absent. |
| `installer_helpers.sh` | Shared install-time helpers (`run_as_target`, `msg`, `need_cmd`, `apt_install`, linked-repository auth gating, session-bus/root guards, and sudo-deferral reporting) loaded through `isc_load_helpers`; uses the same best-effort file logger. |
| `safe_system_action.sh` | Guarded reboot/poweroff entry point with an audible 10-to-1 countdown, Ctrl+C/SIGTERM cancellation, and an extended alert at 0. |
| `logging_utils.py` | Centralized Python logging helper for repository maintenance scripts and tests; provides idempotent `.log/` file logging and the standard `log_call` tracing decorator. |
| `install.sh` | Component-based installer that deploys this framework as selectable modules (core always installed; menu/runtime/helpers optional, default-on). |
| `installer/components.sh` | This repository's optional-module manifest consumed by the shared runtime. |
| `lib/framework_install.sh` | The deploy functions (`isc_install_core` and one per optional module) invoked by `install.sh`. |

## Installing this repository as modules

Like every other repository in the chain, this one ships a component-based
`install.sh` that deploys its features as selectable, installable modules. It
copies the framework into a stable, network-independent location (by default the
loader's offline download cache,
`${XDG_CACHE_HOME:-$HOME/.cache}/installation_scripts/components`; override with
`ISC_INSTALL_DIR`) so a consuming installer can resolve the framework even with
no source checkout present.

```bash
bash install.sh                  # interactive submenu on a TTY, else defaults
bash install.sh --default        # core + all default-on modules, no prompts
bash install.sh --all            # core + every module, no prompts
bash install.sh --select menu    # core + exactly these module ids
bash install.sh --list-components  # print: id<TAB>label<TAB>default[<TAB>section[<TAB>requires]]
```

**Core (always installed, never deselectable).** Installed unconditionally so
the framework core works no matter which optional modules are chosen:

| File | Why it is core |
|---|---|
| `component_loader.sh` | The bootstrap/resolver — without it nothing can locate the framework. |
| `component_logging.sh` | Shared Bash leveled file logger (logging is required). |
| `logging_utils.py` | Shared Python logging helper (logging is required). |
| `safe_system_action.sh` | Shared safety boundary for every reboot and poweroff request. |

**Optional modules (default-on, fully customizable).** Each is one selectable
component in `installer/components.sh`:

| Component id | File | Purpose |
|---|---|---|
| `menu` | `component_menu.sh` | Interactive two-level selection menu engine. |
| `runtime` | `component_runtime.sh` | Per-repository `--list-components`/`--select`/`--default`/`--all` contract. |
| `installer_helpers` | `installer_helpers.sh` | Shared install-time helpers (`run_as_target`, `apt_install`, …). |

Deselecting an optional module only means that file is not deployed locally; a
consuming installer still fetches it on demand through `component_loader.sh`, so
nothing breaks — the core always resolves and the rest downloads when needed.

## Linked repository authentication

The component runtime accepts `--auth`, which exports `INSTALLER_AUTH=1` for
the selected components. Shared helpers use that flag for linked private setup
repositories:

- `ensure_linked_repository <label> <dir> <url>` uses an existing sibling
  checkout as-is by default.
- With `--auth` / `INSTALLER_AUTH=1`, the helper may run non-prompting
  `git pull` for an existing checkout or non-prompting `git clone` for a
  missing checkout.
- Without auth, a missing linked repository returns non-zero with a clear
  message instead of prompting for GitHub credentials.

## How a repository uses it

A consuming repository declares a small component manifest
(`installer/components.sh`) and, from its `install.sh`, loads this framework and
hands control to it:

```bash
# Load the shared installer component framework (single source of truth).
ISC_FN_DIR="${ISC_FUNCTIONS_DIR:-$SCRIPT_DIR/../linux_installation_scripts_functions}"
if [ -f "$ISC_FN_DIR/component_loader.sh" ]; then
  source "$ISC_FN_DIR/component_loader.sh"
else
  source <(curl -fsSL "https://raw.githubusercontent.com/mikaeltorni/linux_installation_scripts_functions/${ISC_FUNCTIONS_REF:-master}/component_loader.sh")
fi
isc_activate_components
source "$SCRIPT_DIR/installer/components.sh"   # repo-specific manifest
component_main "$@"
```

The manifest maps component ids to the installer's own step functions. Each
entry is
`id|label|default|install_fn[|detect_fn[|uninstall_fn[|section[|requires[|configure_fn[|config_status_fn]]]]]]`;
the trailing fields are optional:

```bash
ISC_REPO_NAME="example_repo"
ISC_REPO_LABEL="Example repository"
ISC_CORE="install_example_core"        # optional, ALWAYS runs first (see below)
ISC_PREFLIGHT="ensure_session_bus"     # optional, runs once before components
ISC_POSTFLIGHT="report_sudo_required"  # optional, runs once after components
ISC_COMPONENTS=(
  "feature_a|Human label for A|on|install_feature_a|detect_feature_a|uninstall_feature_a"
  "feature_b|Human label for B|off|install_feature_b|||Models"
  "feature_b_status|B status bar|on|install_b_status|||Models|feature_b"
)
```

### Core vs. optional components

Only genuinely optional features belong in `ISC_COMPONENTS`. A `default` of `on`
means *pre-selected*, not *mandatory* — the user can always deselect it, and
`--select ''` selects nothing at all. Whatever a repository must install to be
useful at all (its CLI, its extension, its service) therefore has to live
outside the manifest:

```bash
ISC_CORE="install_example_core"   # always runs, even for --select ''
```

`ISC_CORE` runs once, first, before the preflight and before any component, and
its failure is fatal (`component_main` returns 2 and installs no components, so
nothing is layered on top of a broken core). It must be idempotent: every
install, re-run, and reconfigure invokes it. Calling the core function directly
from the repository's own `main()` before `component_main "$@"` is equally
valid.

Do **not** express the core as `ISC_PREFLIGHT`. The preflight deliberately fires
only in front of the first component that actually runs, so that a no-op run
stays a no-op — which means a blank selection skips it and the core would never
be installed. Keep `ISC_PREFLIGHT` for per-run environment setup (session bus,
device selection) and `ISC_POSTFLIGHT` for end-of-run summaries.

* `detect_fn` returns 0 when the component is already installed on this machine.
  When omitted, detection falls back to an **install receipt** — a marker file
  the runtime writes automatically after the install function succeeds (under
  `${XDG_STATE_HOME:-~/.local/state}/isc/receipts/<repo>/<id>`), so detection
  works for every component with no extra code.
* `uninstall_fn` reverses the installation. When omitted, the component cannot be
  reversed from the menu; its `[u]` action only clears the receipt (a safe,
  non-destructive fallback for components whose reversal would be ambiguous).
* `section` is a visual heading only. Components remain selectable rows and
  execute in manifest order; repositories can put a `Models` section first
  without introducing pseudo-components.
* `requires` is a comma-separated list of component ids. A dependent row can be
  selected only when every requirement is selected in the same run or detected
  as already installed. Requirements must precede dependents in manifest order.
* `configure_fn` opens a repository-owned typed/details screen when the user
  presses RIGHT. `config_status_fn` is side-effect free and prints the current
  friendly value shown in brackets, such as `[Super+W]`; the menu labels the
  action `(→ rebind)`.

For hotkeys, `isc_prompt_hotkey_field` accepts multiple modifiers plus exactly
one key, while `isc_prompt_modifier_field` accepts exactly one modifier. Both
persist validated values for standalone and aggregate master installers.

The runtime writes a receipt after each successful install and clears it after a
successful uninstall, so install state stays accurate across runs.

### Resulting command-line contract

```bash
bash install.sh                  # interactive submenu on a TTY, else defaults
bash install.sh --default        # install all default-on components, no prompts
bash install.sh --all            # install every component, no prompts
bash install.sh --select a,b     # install exactly these component ids
bash install.sh --reconfigure a  # re-apply (idempotent re-run) of these ids
bash install.sh --uninstall a,b  # uninstall exactly these component ids
bash install.sh --list-components  # print: id<TAB>label<TAB>default[<TAB>section[<TAB>requires]]
bash install.sh --list-configurable-components
bash install.sh --list-component-config-values  # id<TAB>friendly current value
bash install.sh --configure-component a         # open a nested field/details screen
bash install.sh --detect         # print: id<TAB>installed|absent
```

In the interactive submenu, already-installed components show a `✓`; `space`
selects an installed component for **reconfigure** (`~`), `[u]` marks it for
**uninstall** (`✗`), `[r]` marks every installed component for reconfigure,
`[f]` toggles GNOME dock favourite selection, and `[s]` toggles launch at
desktop login for app components that expose the corresponding metadata. Rows
show `F`, `S`, or `FS` when either or both app actions are selected. Editable
rows show their current value in brackets; RIGHT opens the rebind/details field.
The footer is derived from loaded component metadata: navigation and toggle
remain universal, while RIGHT, favourite, startup, workspace, all-workspaces,
and uninstall hints appear only when at least one row supports that action.
This keeps application actions out of non-application repositories without
hardcoding repository names in the menu engine.

In the aggregate master menu, setting `ISC_MENU_DEBUG=1` exposes `[l] log state`.
That action writes a quiet snapshot of every repository and component state
(selected, installed, pending reconfigure, pending uninstall, or absent) to the
framework log file without printing the dump into the TUI.

## Resolution order

`isc_activate_components` looks for the framework in this order:

1. `$ISC_COMPONENT_LIB_DIR` (explicit override)
2. `$ISC_FUNCTIONS_DIR` (explicit path to this repo)
3. `$SCRIPT_DIR/../linux_installation_scripts_functions` (sibling checkout)
4. `$HOME/projects/linux_installation_scripts_functions` (default checkout)
5. download into `$XDG_CACHE_HOME/installation_scripts/components`

In the `installation_scripts` clean-install chain this repository is cloned as a
sibling, so installers resolve it locally with no network call. Standalone, a
single repository downloads the framework on demand. Set `ISC_FUNCTIONS_REF` to
pin a branch/tag or `ISC_FUNCTIONS_RAW` for a private mirror.

## Logging

Every framework entry point records leveled, timestamped diagnostics through
`component_logging.sh`. Logs are written to a file (never the terminal, so the
TUI is never corrupted) and the directory is created on demand:

| Variable | Default | Purpose |
|---|---|---|
| `ISC_LOG_DIR` | `${SCRIPT_DIR:-$PWD}/.log` | Directory for log files (the consuming repo's `.log/`). |
| `ISC_LOG_NAME` | `installer_components.log` | Log file name within `ISC_LOG_DIR`. |
| `ISC_LOG_LEVEL` | `debug` | Minimum level recorded (`verbose` < `debug` < `info` < `warn` < `error`). |
| `ISC_LOG_TAG` | `$ISC_REPO_NAME`, else `framework` | Context tag added to each line. |
| `ISC_MENU_DEBUG` | unset | Set to `1` to unlock debug-only aggregate-menu actions such as `[l] log state`. |

Log files are runtime artifacts and are git-ignored via `.log/`. Logging is
best-effort: a read-only filesystem or missing `date` never aborts an installer.

## Tests

```bash
bash tests/run_tests.sh
```

The tests are simulation-only: they exercise the contract, the menu count
helpers, and loader resolution with a synthetic manifest in isolated Bash
subprocesses. No packages are installed and no desktop settings change.

## License

See [`LICENSE.md`](LICENSE.md).

## Disclaimer

This software is provided under the MIT License on an **“as is”** basis, without warranties of any kind. To the maximum extent permitted by applicable law, the authors and copyright holders shall not be liable for any claims, damages, losses, or other liability arising from the use of this software.

You are solely responsible for determining whether this software is suitable, safe, lawful, and appropriate for your intended use. Unless explicitly stated otherwise, this project is general-purpose software and is not designed, tested, certified, or approved for safety-critical, medical, automotive, aviation, industrial-control, life-support, cybersecurity-critical, financial-critical, or other high-risk use cases.

The authors and copyright holders make no guarantees regarding security, reliability, availability, correctness, compliance, non-infringement, or fitness for any particular purpose.

This notice is intended to clarify the nature of the project and does not impose additional restrictions beyond the MIT License.
