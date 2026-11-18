"""Descriptor-relative workspace access on supported POSIX platforms."""
from contextlib import contextmanager
import os
import re
import stat

SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", re.ASCII)


class WorkspaceError(ValueError):
    """A workspace safety check failed."""


def safe_parts(path):
    parts = path.split("/")
    if len(path) > 240 or len(parts) > 8 or any(
        not SEGMENT.fullmatch(part) or part.endswith(".") for part in parts
    ):
        raise WorkspaceError("Use a relative path with ordinary, non-hidden names.")
    return parts


def directory_flags():
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise WorkspaceError("Secure directory operations require macOS, Linux, or WSL.")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def open_directory(name, **kwargs):
    fd = os.open(name, directory_flags(), **kwargs)
    metadata = os.fstat(fd)
    if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022:
        os.close(fd)
        raise WorkspaceError("Workspace directories must be owned by you and protected from other writers.")
    return fd


@contextmanager
def workspace_root(path):
    directory_flags()
    try:
        os.mkdir(path, mode=0o700)
    except FileExistsError:
        pass
    fd = open_directory(path)
    try:
        yield fd
    finally:
        os.close(fd)


@contextmanager
def parent_directory(root_fd, parts, create=False):
    fd = os.dup(root_fd)
    try:
        for name in parts[:-1]:
            if create:
                try:
                    os.mkdir(name, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = open_directory(name, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def require_regular(fd):
    state = os.fstat(fd)
    if not stat.S_ISREG(state.st_mode) or state.st_nlink != 1:
        raise WorkspaceError("Only regular, single-link files are supported.")
    return state


@contextmanager
def workspace_file(parent_fd, name, flags):
    fd = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=parent_fd)
    try:
        require_regular(fd)
        yield fd
    finally:
        os.close(fd)


def terminal_text(text):
    """Escape terminal controls while preserving readable text and line breaks."""
    return "".join(
        char if char.isprintable() or char == "\n" else ascii(char)[1:-1]
        for char in text
    )
