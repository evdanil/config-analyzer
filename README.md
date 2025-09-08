# Config Analyzer

Interactive TUI to browse network device configuration repositories, preview current configs, and diff historical snapshots — all from your terminal.

- Fast, keyboard-first workflow powered by Textual + Rich
- Device browser with instant preview and quick filtering
- Snapshot history view with unified or side‑by‑side diffs
- Flexible layout (right / left / bottom / top) you can toggle on the fly


## Installation

Requirements: Python 3.8+

- From source (editable):

```bash
pip install -e .
```

- As a module (without install):

```bash
python -m config_analyzer --help
```


## Quick Start

- Browse a repository of device configs:

```bash
config-analyzer --repo-path /path/to/repo
```

- Jump straight to a device’s snapshot history (device name without .cfg):

```bash
config-analyzer --repo-path /path/to/repo --device router-01
```

- Choose initial layout (diff/right pane on a side or top/bottom):

```bash
config-analyzer --repo-path /path/to/repo --layout left
```

- Enable verbose logs to `tui_debug.log`:

```bash
config-analyzer --repo-path /path/to/repo --debug
```


## Repository Layout Expectations

The browser lists folders (excluding any named like the history directory, default `history`) and `.cfg` files as devices. For a selected device, it discovers snapshots under the closest history folder.

Typical shapes it understands:

```
repo/
  siteA/
    switches/
      sw01.cfg         # current config
      history/
        sw01/
          2024-08-11_09-00_sw01.cfg
          2024-08-18_09-00_sw01.cfg
    routers/
      r01.cfg
      history/
        r01/
          r01_2024-08-02_1200.cfg
  history/
    r02/
      2024-07-01_0000_r02.cfg
```

Discovery rules:
- Current config: `DEVICE.cfg` found anywhere under the repo except inside the configured history folder.
- Snapshots: `history/DEVICE/*.cfg`, preferring the nearest folder relative to a selected device, then repo root, then any found in the repo.


## CLI Options

```text
--repo-path PATH        Required. Folder with device configs.
--device NAME           Optional device name (without .cfg) to open snapshot view directly.
--layout [right|left|bottom|top]
                        Starting layout of the preview/diff pane. Default: right
--scroll-to-end         Auto-scrolls preview/diff pane to the end when shown.
--history-dir NAME      Name of the folder that stores snapshots. Default: history
--debug                 Verbose logs to tui_debug.log (set by CONFIG_ANALYZER_DEBUG=1 as well).
```

The entry point is installed as `config-analyzer` and also available as `python -m config_analyzer`.


## Keyboard Shortcuts

Device Browser (left: list, right: preview):
- Ctrl+Q: Quit
- Enter or Right: Enter / Open
- Left or Alt+Up: Go up a directory
- Ctrl+L: Toggle layout (right → bottom → left → top)
- Home / End: Jump to first / last row
- Quick filter: Just start typing to filter. Backspace deletes a character. Esc clears.

Snapshot History (list of snapshots + diff):
- Ctrl+Q: Quit
- Enter: Toggle select on the current row (select two to diff)
- Tab: Switch focus between table and diff pane
- Esc: Back to device browser or hide diff (when visible)
- Ctrl+L: Toggle layout
- D: Toggle diff mode (unified ↔ side‑by‑side) when the diff pane is focused
- H: Hide unchanged (side‑by‑side mode) when the diff pane is focused
- Home / End: Jump to first / last row
- Quick filter: Just start typing. Backspace deletes. Esc clears.

Footer tips update dynamically to reflect the current context and filter state.


## Features and Behavior

- Device preview: Highlight a device to preview its current configuration with syntax highlighting.
- History discovery: Finds the nearest `history/<device>` directory relative to a selected config; falls back to repo root or scans the repo.
- Current + snapshots: Shows current config (labeled “Current”) first, followed by snapshots ordered by timestamp (newest first).
- De‑duplication: If “Current” has the same content as the latest snapshot, it’s omitted automatically.
- Layout switching: Rebuilds widgets on layout toggle and restores selection/preview to avoid any visual glitches.
- Side‑by‑side and unified diffs: Choose your preferred diff mode; optionally hide unchanged sections in side‑by‑side.
- Quick filter: Type to filter rows by name, author, or date (where applicable). Works in both views.


## How It Works (Architecture)

- `config_analyzer/cli.py`: Click CLI. Orchestrates the device browser and snapshot history views, preserves layout preference, and uses utils for discovery/collection.
- `config_analyzer/repo_browser.py`: Device/folder browser TUI. Instant preview, quick filter, layout toggling, selection persistence.
- `config_analyzer/tui.py`: Snapshot selector and diff TUI. Two‑item selection to diff; single selection shows highlighted content.
- `config_analyzer/parser.py`: Heuristics to parse configs into `Snapshot` objects. Extracts author and timestamp from content or filename; falls back to file mtime. Also provides `parse_snapshot_meta` for fast directory listing (head‑only read).
- `config_analyzer/differ.py`: Unified and side‑by‑side diffs using `difflib`, rendered via Rich.
- `config_analyzer/utils.py`: Repository scanning, nearest `history/<device>` lookup, and snapshot collection (ordering + duplication handling).
- `config_analyzer/filter_mixin.py`: Reusable quick‑filter behavior for Textual apps.
- `config_analyzer/keymap.py`: Centralized per‑view key bindings.
- `config_analyzer/tips.py`: Dynamic footer tip formatting.
- `config_analyzer/formatting.py`: Timestamp normalization/formatting.
- `config_analyzer/debug.py`: File logger (`tui_debug.log`) controlled by `--debug` or `CONFIG_ANALYZER_DEBUG=1`.


## Logging and Troubleshooting

- Enable verbose logs: `--debug` or `CONFIG_ANALYZER_DEBUG=1`. Output goes to `tui_debug.log` in the current working directory (override with `CONFIG_ANALYZER_LOG`).
- Large files: Syntax highlighting and side‑by‑side rendering rely on Rich; very large configs may render slowly.
- Terminal size: Small terminals may clip panels; use Ctrl+L to switch layouts.
- Textual version quirks: The UIs rebuild widgets on layout changes to avoid reparenting issues that can cause blank panes right after startup.


## Development

- Install dev environment:

```bash
pip install -e .
```

- Run from source:

```bash
python -m config_analyzer --repo-path /path/to/repo
```

- Project layout:

```
config_analyzer/
  cli.py            # CLI entry point
  repo_browser.py   # Device/folder browser TUI
  tui.py            # Snapshot history + diff TUI
  parser.py         # Snapshot parsing heuristics (+ fast meta)
  differ.py         # Unified / side‑by‑side diffs
  utils.py          # Discovery and snapshot collection
  filter_mixin.py   # Quick filter behavior
  keymap.py         # Keymaps per view
  tips.py           # Footer hints
  formatting.py     # Timestamp formatting
  debug.py          # Logging setup
  version.py        # __version__
pyproject.toml
```

- Code style: The code follows a pragmatic, small‑module style. Avoid adding global side effects; prefer explicit wiring in the CLI.


## Changelog Highlights (from git log)

- Filtering + per‑view keymaps; dynamic footer hints; stable Enter selection and Tab focus.
- Repo browser: robust layout switching (rebuild + restore selection/preview); borders reflect orientation.
- Snapshot view: remount‑based layout switching; diff panel focus control; hide unchanged lines (SxS).
- CLI: `--history-dir`, persistent layout across views, nearest history discovery; clears terminal between views.
- Parser: fast head‑only metadata for directory listing; timestamp/author heuristics; timezone normalization.
- Differ: unified and side‑by‑side modes with simple visuals and word wrap.
- Packaging: installable module with `config-analyzer` entry point.


## License

Proprietary. All rights reserved.

