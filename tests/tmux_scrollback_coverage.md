# Background output preservation

Run `python3 -m unittest discover -s tests -p test_tmux_background_output.py`.
Each case has a fresh temporary directory; tmux cases use a private socket.

| Interface / rule | Executable case and independent expectation |
| --- | --- |
| record binary output, live-readable complete gzip members | test_record: decompressed bytes equal the supplied binary payload; empty stream passes gzip validation |
| start missing/extra/unknown arguments | test_rejections: CLI returns nonzero before touching tmux |
| fresh background window and unlimited agent history | test_background: 8000 numbered lines archived, live history at most 2000, agent limit and pane unchanged |
| existing large grid, snapshot before replacement | test_background: old marker retained in snapshot, replacement has a 2000-line grid |
| restart already bounded pane | test_background: pane id preserved and second-run marker archived |
| invalid multi-pane target | test_multiple_panes: rejection preserves pane ids and commands; missing cwd also leaves panes unchanged |
| installed helper available without optional modules | test_install.py core file inventory and temporary installation |

Archive chunks are independent gzip members, so a recorder crash cannot invalidate
earlier chunks. Archives are private, append-only, and never automatically pruned.
