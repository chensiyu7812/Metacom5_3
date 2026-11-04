"""Append immutable progress records without overwriting a prior snapshot."""
from pathlib import Path
from .durable import save_json_once


def record_progress(root,kind,value):
    if kind not in ('step','epoch') or type(value.get(kind)) is not int or value[kind]<1:
        raise ValueError('positive step/epoch identity required')
    path=Path(root)/f'{kind}_{value[kind]:04d}.json'
    save_json_once(path,value)
    return path
