# Config Analyzer

Interactive TUI to browse network device configuration repositories, preview current configs, and diff historical snapshots — all from your terminal.

- Fast, keyboard-first workflow powered by Textual + Rich
- Device browser with instant preview and quick filtering
- Snapshot history view with unified or side‑by‑side diffs
- Flexible layout (right / left / bottom / top) you can toggle on the fly


## Installation

Requirements: Python 3.10+ and Textual 8.2+ (`textual>=8.2,<9`, installed with the package)

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

- Jump straight to a device’s snapshot history (device name without .cfg). The repository browser stays underneath, so Esc returns to it on the device’s folder; an unknown device opens the browser with an error notification:

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
--device NAME           Optional device name (without .cfg) to open snapshot view directly
                        (the browser stays beneath; an unknown name shows an error notification).
--layout [right|left|bottom|top]
                        Starting layout of the preview/diff pane. Default: right
--scroll-to-end         Auto-scrolls preview/diff pane to the end when shown.
--history-dir NAME      Name of the folder that stores snapshots. Default: history
--debug                 Verbose logs to tui_debug.log (set by CONFIG_ANALYZER_DEBUG=1 as well).
```

The entry point is installed as `config-analyzer` and also available as `python -m config_analyzer`.


## Keyboard Shortcuts

Press `?` in either view to open the help panel with the keys that apply there.

Device Browser (left: list, right: preview):
- Ctrl+Q: Quit at once
- Enter or Right: Enter / Open
- Left or Alt+Up: Go up a directory
- Tab / Shift+Tab: Switch between list and preview
- Ctrl+F or Alt+F: Find in the preview, only while a document is shown (a text line: Enter/Down next match, Up previous, Esc closes)
- z: Maximize the preview (only while a document is shown)
- j / k / Space: Scroll the preview
- Ctrl+L: Toggle layout (right → bottom → left → top)
- Home / End: Jump to first / last row
- Quick filter: `/` focuses the filter line; letters typed on the list go into it, except `z`, `/` and `?`. Backspace edits the filter only while the filter line has the focus.
- Esc: Close find, restore a maximized preview, clear the filter. In the browser it never leaves or quits.

Snapshot History (list of snapshots + diff):
- Ctrl+Q: Quit at once
- Enter: Toggle select on the current row (select two to diff)
- Tab / Shift+Tab: Switch focus between list and diff pane
- Esc: Close find, restore a maximized pane, clear the filter, hide the diff, then go back to the device browser (its folder, filter, cursor and scroll position are kept)
- Ctrl+L: Toggle layout
- Ctrl+F or Alt+F: Find in the document; z: Maximize it; j / k / Space: Scroll it
- d: Toggle diff mode (unified ↔ side‑by‑side) when the diff pane is focused
- h: Hide unchanged (side‑by‑side mode) when the diff pane is focused
- Home / End: Jump to first / last row
- Quick filter: same as in the browser (`/`, or just start typing on the list).

Footer tips update dynamically to reflect the current context.


## Features and Behavior

- Device preview: Highlight a device to preview its current configuration with syntax highlighting.
- History discovery: Finds the nearest `history/<device>` directory relative to a selected config; falls back to repo root or scans the repo.
- Current + snapshots: Shows current config (labeled “Current”) first, followed by snapshots ordered by timestamp (newest first).
- De‑duplication: If “Current” has the same content as the latest snapshot, it’s omitted automatically.
- Layout switching: Ctrl+L changes the layout in place (nothing is rebuilt), so focus, cursor and scroll position are kept.
- Side‑by‑side and unified diffs: Choose your preferred diff mode; optionally hide unchanged sections in side‑by‑side.
- Quick filter: Press `/` or just type on a list to filter rows by name, author, or date (where applicable). The filter is an editable text line. Works in both views.


## How It Works (Architecture)

- `config_analyzer/cli.py`: Click CLI. Builds `ConfigAnalyzerApp` from the options and runs it.
- `config_analyzer/app.py`: `ConfigAnalyzerApp`, the one Textual app. Hosts the two screens, owns the layout preference and the navigation between them (open a device, Esc back, quit).
- `config_analyzer/repo_browser.py`: `BrowserScreen`, the device/folder browser. Instant preview, quick filter, find, layout toggling.
- `config_analyzer/tui.py`: `SnapshotScreen`, the snapshot selector and diff view. Two‑item selection to diff; single selection shows highlighted content.
- `config_analyzer/widgets.py`: `FilterInput` and `FindInput` (the filter and find text lines) and the searchable document pane.
- `config_analyzer/parser.py`: Heuristics to parse configs into `Snapshot` objects. Extracts author and timestamp from content or filename; falls back to file mtime. Also provides `parse_snapshot_meta` for fast directory listing (head‑only read).
- `config_analyzer/differ.py`: Unified and side‑by‑side diffs using `difflib`, rendered via Rich.
- `config_analyzer/utils.py`: Repository scanning, nearest `history/<device>` lookup, and snapshot collection (ordering + duplication handling).
- `config_analyzer/filter_mixin.py`: Reusable quick‑filter state for the list screens.
- `config_analyzer/keymap.py`: Centralized per‑view key bindings, and the keys a list never types into the filter.
- `config_analyzer/tips.py`: Dynamic footer tip formatting.
- `config_analyzer/formatting.py`: Timestamp normalization/formatting.
- `config_analyzer/debug.py`: File logger (`tui_debug.log`) controlled by `--debug` or `CONFIG_ANALYZER_DEBUG=1`.


## Logging and Troubleshooting

- Enable verbose logs: `--debug` or `CONFIG_ANALYZER_DEBUG=1`. Output goes to `tui_debug.log` in the current working directory (override with `CONFIG_ANALYZER_LOG`).
- Large files: Syntax highlighting and side‑by‑side rendering rely on Rich; very large configs may render slowly.
- Terminal size: Small terminals may clip panels; use Ctrl+L to switch layouts.
- Textual version: The package needs `textual>=8.2,<9`. Run `pip install -r requirements.txt` after updating from an older version.


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
  app.py            # ConfigAnalyzerApp: hosts both screens
  repo_browser.py   # Device/folder browser screen
  tui.py            # Snapshot history + diff screen
  widgets.py        # Filter / find lines, searchable pane
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

- 0.2.0: one `ConfigAnalyzerApp` with browser and snapshot screens; `?` help panel; filter and find as text lines; Esc closes find, restores a maximized pane, clears the filter, then goes back; layout changes keep focus, cursor and scroll; requires Textual 8.2+.
- Filtering + per‑view keymaps; dynamic footer hints; stable Enter selection and Tab focus.
- Repo browser: robust layout switching (rebuild + restore selection/preview); borders reflect orientation.
- Snapshot view: remount‑based layout switching; diff panel focus control; hide unchanged lines (SxS).
- CLI: `--history-dir`, persistent layout across views, nearest history discovery; clears terminal between views.
- Parser: fast head‑only metadata for directory listing; timestamp/author heuristics; timezone normalization.
- Differ: unified and side‑by‑side modes with simple visuals and word wrap.
- Packaging: installable module with `config-analyzer` entry point.


## License

Proprietary. All rights reserved.

