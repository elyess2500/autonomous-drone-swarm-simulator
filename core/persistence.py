"""Unique output names and atomic publication; no object deserialization."""
import json
import os
from pathlib import Path
import tempfile
import uuid


def unique_path(directory, prefix, suffix):
    return str(Path(directory) / f'{prefix}_{uuid.uuid4().hex}{suffix}')


def atomic_write(path, write, *, overwrite=False):
    """Publish a complete sibling temp file; default publication cannot clobber.

    Hard-link publication is atomic and fails if the destination exists. Explicit
    overwrite uses os.replace. Filesystems without hard-link support fail safely.
    fsync covers file contents, not a portable power-loss durability guarantee.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path, payload, *, overwrite=False):
    atomic_write(path, lambda f: json.dump(payload, f, sort_keys=True,
                                          separators=(',', ':'), allow_nan=False),
                 overwrite=overwrite)
