# linux_installation_scripts_functions

Shared, reusable installer functions for the
[`installation_scripts`](https://github.com/mikaeltorni/installation_scripts)
Ubuntu desktop setup chain. This repository is the **single source of truth** for
the interactive installer component-selection framework. The master installer
and every standalone repository installer load these files instead of vendoring
their own copies, so a change here updates all of them at once.

## What's here

| File | Purpose |
|---|---|
| `component_menu.sh` | Pure-Bash TUI engine: a two-level selection menu (repository rows with enable/disable, per-repository component submenus, and live `on/total` counts). No external dependencies. |
| `component_runtime.sh` | The per-repository installer contract: `--list-components`, `--select id,…`, `--default`, `--all`, an interactive submenu, and optional `ISC_PREFLIGHT` / `ISC_POSTFLIGHT` hooks. |
| `component_loader.sh` | Resolves and activates the framework from a sibling checkout or by downloading it; exposes `isc_activate_components`. |

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

The manifest maps component ids to the installer's own step functions:

```bash
ISC_REPO_NAME="example_repo"
ISC_REPO_LABEL="Example repository"
ISC_PREFLIGHT="ensure_session_bus"     # optional, runs once before components
ISC_POSTFLIGHT="report_sudo_required"  # optional, runs once after components
ISC_COMPONENTS=(
  "feature_a|Human label for A|on|install_feature_a"
  "feature_b|Human label for B|off|install_feature_b"
)
```

### Resulting command-line contract

```bash
bash install.sh                  # interactive submenu on a TTY, else defaults
bash install.sh --default        # install all default-on components, no prompts
bash install.sh --all            # install every component, no prompts
bash install.sh --select a,b     # install exactly these component ids
bash install.sh --list-components  # print: id<TAB>label<TAB>default
```

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
