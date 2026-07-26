"""Python launcher support for the native git-omit executable."""

from ._find_git_omit import GitOmitNotFound, find_git_omit_bin

__all__ = ["GitOmitNotFound", "find_git_omit_bin"]
