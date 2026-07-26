from __future__ import annotations

import os
import subprocess
import sys

from ._find_git_omit import find_git_omit_bin


def main() -> int:
    executable = find_git_omit_bin()
    argv = [executable, *sys.argv[1:]]

    if os.name == "nt":
        return subprocess.run(argv, check=False).returncode

    os.execv(executable, argv)
    raise AssertionError("os.execv unexpectedly returned")


if __name__ == "__main__":
    raise SystemExit(main())
