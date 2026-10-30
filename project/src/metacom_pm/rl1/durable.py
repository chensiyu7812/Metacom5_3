"""Publish a complete immutable file, including directory durability."""
import os
import json
from pathlib import Path
import tempfile


def save_json_once(path, value):
    """Canonical immutable envelope; strings keep exact original wire order."""
    path = Path(path)
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n'
    if path.exists():
        if path.read_text() != data:
            raise ValueError('immutable development journal changed')
    else:
        publish(path, lambda f: f.write(data.encode()))


def publish(path, writer):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            writer(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)  # atomic create; never overwrite an old result
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.unlink(temporary)
