# git-omit

Small Git helpers for files that should only be ignored locally.

## Installation

Install the native command from PyPI:

```console
uv tool install git-omit
```

Or install it into a Python environment:

```console
pip install git-omit
```

The environment installation supports both entry styles:

```console
git-omit --help
python -m git_omit --help
```

Prebuilt wheels are published for Windows x86_64, macOS x86_64 and ARM64,
and glibc-based Linux x86_64 and ARM64.

## Commands

| Command | Effect |
| --- | --- |
| `git-omit hide <pattern>...` | Add patterns to `.git/info/exclude` |
| `git-omit unhide <pattern>...` | Remove patterns from `.git/info/exclude` |
| `git-omit freeze <path>...` | Mark tracked files as `skip-worktree` |
| `git-omit unfreeze <path>...` | Clear `skip-worktree` |
| `git-omit list` | List hidden patterns and frozen paths |

Quote glob patterns so the shell passes them to `git-omit` unchanged:

```console
git-omit hide '*.log'
```

## Building

The native program requires Zig 0.16.0:

```console
zig build test
zig build -Doptimize=ReleaseSmall
```

Build every platform wheel from one Linux host with Zig cross-compilation:

```console
python make_wheels.py --sdist
```
