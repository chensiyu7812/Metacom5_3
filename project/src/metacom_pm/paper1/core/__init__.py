"""Mechanical execution primitives for the active Paper-1 pipeline."""

from .treatment import (
    ResourceBlock,
    RunBinding,
    inspect_treatment_delivery,
    parse_resource_blocks,
    render_resource_block,
)

__all__ = [
    "ResourceBlock",
    "RunBinding",
    "inspect_treatment_delivery",
    "parse_resource_blocks",
    "render_resource_block",
]
