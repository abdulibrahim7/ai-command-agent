"""Execute validated text workspace operations and fixed read-only built-ins."""
from datetime import datetime, timezone
from itertools import islice
import json
import os
import secrets

from action_schema import PlanError, validate_action_plan
from safety import (WorkspaceError, parent_directory, require_regular, safe_parts,
                    terminal_text, workspace_file)

MAX_FILE = 65_536
MAX_LIST = 100


def log_action(log_root, kind, status):
    entry = json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
                        "action": kind, "status": status}) + "\n"
    with workspace_file(log_root, "actions.log", os.O_WRONLY | os.O_APPEND | os.O_CREAT) as fd:
        os.write(fd, entry.encode("utf-8"))


def built_in(root_fd, name):
    if name == "pwd":
        return "workspace/"
    with os.scandir(root_fd) as entries:
        names = [entry.name for entry in islice(entries, MAX_LIST + 1)]
    # JSON string quoting prevents filenames from manufacturing extra output lines.
    listing = "\n".join(json.dumps(name) for name in sorted(names[:MAX_LIST]))
    return (listing or "(empty workspace)") + ("\n(list truncated)" if len(names) > MAX_LIST else "")


def write_file(parent, name, content, append, approve_change):
    create = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        with workspace_file(parent, name, create) as fd:
            with os.fdopen(os.dup(fd), "wb") as stream:
                stream.write(content)
        return True, "Created file."
    except FileExistsError:
        pass
    flags = os.O_WRONLY | (os.O_APPEND if append else 0)
    with workspace_file(parent, name, flags) as fd:
        previous = require_regular(fd)
        if append and previous.st_size + len(content) > MAX_FILE:
            raise WorkspaceError("Append would exceed the file size limit.")
        verb = "Append to" if append else "Overwrite"
        if not approve_change(f"{verb} an existing file?"):
            return False, "Existing file change canceled."
        current = require_regular(fd)
        named = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (named.st_dev, named.st_ino):
            raise WorkspaceError("Target changed during confirmation.")
        if append and current.st_size + len(content) > MAX_FILE:
            raise WorkspaceError("Append would exceed the file size limit.")
        if append:
            with os.fdopen(os.dup(fd), "wb") as stream:
                stream.write(content)
        else:
            temporary = ".agent-" + secrets.token_hex(16)
            with workspace_file(parent, temporary, create) as replacement:
                try:
                    with os.fdopen(os.dup(replacement), "wb") as stream:
                        stream.write(content)
                    os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
                finally:
                    try:
                        os.unlink(temporary, dir_fd=parent)
                    except FileNotFoundError:
                        pass
    return True, "Updated file."


def execute_action(action, root_fd, log_root, *, approved=False, approve_change=lambda _: False):
    """Perform one action after an out-of-band human approval."""
    try:
        validate_action_plan({"actions": [action]})
    except PlanError:
        log_action(log_root, "invalid", "blocked")
        return False, "Invalid action blocked."
    kind, params = action["type"], action["params"]
    if kind == "no_op":
        log_action(log_root, kind, "skipped")
        return True, "No action."
    if not approved:
        log_action(log_root, kind, "blocked")
        return False, "Human approval required."

    try:
        if kind == "shell_command":
            ok, output = True, built_in(root_fd, params["command"])
        else:
            parts = safe_parts(params["path"])
            with parent_directory(root_fd, parts, create=kind != "file_read") as parent:
                if kind == "file_read":
                    with workspace_file(parent, parts[-1], os.O_RDONLY) as fd:
                        with os.fdopen(os.dup(fd), "rb") as stream:
                            data = stream.read(MAX_FILE + 1)
                    if len(data) > MAX_FILE:
                        raise WorkspaceError("File exceeds the read limit.")
                    ok, output = True, terminal_text(data.decode("utf-8"))
                else:
                    def confirm_existing(question):
                        if not approve_change(f"{question} Target: {params['path']}"):
                            return False
                        with parent_directory(root_fd, parts) as current_parent:
                            if not os.path.samestat(os.fstat(parent), os.fstat(current_parent)):
                                raise WorkspaceError("Parent changed during confirmation.")
                        return True

                    ok, output = write_file(parent, parts[-1], params["content"].encode("utf-8"),
                                            kind == "file_append", confirm_existing)
    except (OSError, UnicodeError, WorkspaceError):
        log_action(log_root, kind, "blocked")
        return False, "File or workspace operation failed a safety or I/O check."
    log_action(log_root, kind, "success" if ok else "cancelled")
    return ok, output
