# git-omit

[简体中文](README_zh.md)

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

The wheel installs the native executable into the environment's scripts directory:

```console
git-omit --help
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

## Development

To build the project, install Zig 0.17.0 and
[uv](https://docs.astral.sh/uv/).

```console
uv sync
uv run git-omit --help
```

Build and run tests locally:

```console
zig build test
zig build -Doptimize=ReleaseSmall
```

Build all five platform wheels into `dist/` with Zig cross-compilation:

```console
uv run python make_wheels.py
```

Pass `--target` to build a specific target. Only wheels are built; no source
distribution (sdist) is produced.

> **Windows cross-build note:** When building Linux or macOS wheels on Windows,
> `make_wheels.py` records mode `0755` in the wheel metadata because Windows
> `chmod` cannot set Unix executable bits.

## Publish

Before publishing, set `UV_PUBLISH_TOKEN`, make sure the version matches in
`pyproject.toml` and `build.zig.zon`, and commit all changes. Then run:

```console
uv run python pypi_publish.py 0.0.4
```

The script checks the versions, working tree, and local and remote tags, then
builds and validates all five wheels. It publishes to PyPI first, then creates
and pushes the version tag.
