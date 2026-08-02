# Portions derived from Ruff: https://github.com/astral-sh/ruff/tree/main/python/ruff
# Copyright (c) 2022 Charles Marsh
# SPDX-License-Identifier: MIT

import os
import sys
import sysconfig


class GitOmitNotFound(FileNotFoundError): ...


def find_git_omit_bin() -> str:
    """Return the git-omit binary path."""

    git_omit_exe = "git-omit" + sysconfig.get_config_var("EXE")

    targets = [
        # The scripts directory for the current Python
        sysconfig.get_path("scripts"),
        # The scripts directory for the base prefix
        sysconfig.get_path("scripts", vars={"base": sys.base_prefix}),
        # Above the package root, e.g., from `pip install --prefix` or `uv run --with`
        (
            # On Windows, with module path `<prefix>/Lib/site-packages/git_omit`
            _join(
                _matching_parents(
                    _module_path(),
                    "Lib/site-packages/git_omit",
                ),
                "Scripts",
            )
            if sys.platform == "win32"
            # On Unix, with module path `<prefix>/lib/python3.13/site-packages/git_omit`
            else _join(
                _matching_parents(
                    _module_path(),
                    "lib/python*/site-packages/git_omit",
                ),
                "bin",
            )
        ),
        # Adjacent to the package root, e.g., from `pip install --target`
        # with module path `<target>/git_omit`
        _join(_matching_parents(_module_path(), "git_omit"), "bin"),
        # The user scheme scripts directory, e.g., `~/.local/bin`
        sysconfig.get_path(
            "scripts",
            scheme=sysconfig.get_preferred_scheme("user"),
        ),
    ]

    seen = []
    for target in targets:
        if not target:
            continue
        if target in seen:
            continue
        seen.append(target)
        path = os.path.join(target, git_omit_exe)
        if os.path.isfile(path):
            return path

    locations = "\n".join(f" - {target}" for target in seen)
    raise GitOmitNotFound(
        "Could not find the git-omit binary in any of the following "
        f"locations:\n{locations}\n"
    )


def _module_path() -> str | None:
    path = os.path.dirname(__file__)
    return path


def _matching_parents(path: str | None, match: str) -> str | None:
    """
    Return the parent directory of `path` after trimming a `match` from the end.
    The match is expected to contain `/` as a path separator, while the `path`
    is expected to use the platform's path separator (e.g., `os.sep`). The path
    components are compared case-insensitively and a `*` wildcard can be used
    in the `match`.
    """
    from fnmatch import fnmatch

    if not path:
        return None
    parts = path.split(os.sep)
    match_parts = match.split("/")
    if len(parts) < len(match_parts):
        return None

    if not all(
        fnmatch(part, match_part)
        for part, match_part in zip(reversed(parts), reversed(match_parts))
    ):
        return None

    return os.sep.join(parts[: -len(match_parts)])


def _join(path: str | None, *parts: str) -> str | None:
    if not path:
        return None
    return os.path.join(path, *parts)
