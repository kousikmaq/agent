"""Parallel-batch processing helpers.

A *batch processing machine* (e.g. a paint booth / curing oven or a QC test
chamber) can process several **compatible** operations **simultaneously** in a
single batch cycle. Operations are compatible when they are at the same batch
work center and belong to the same product family.

There is no product-family master data in the snapshot, so the family is derived
deterministically from the product id (a documented stand-in until real family
data exists). This module is pure and deterministic — no ML, no randomness.
"""

from __future__ import annotations

import re

_FAMILY_BUCKET_SIZE = 3


def product_family(product_id: str) -> str:
    """Derive a deterministic product-family key from a product id.

    Groups products into families of :data:`_FAMILY_BUCKET_SIZE` consecutive
    ids (e.g. FG-0001..FG-0003 -> family "FAM-0"). Falls back to the raw id when
    no numeric suffix is present.
    """
    match = re.search(r"(\d+)\s*$", product_id)
    if match is None:
        return f"FAM-{product_id}"
    index = (int(match.group(1)) - 1) // _FAMILY_BUCKET_SIZE
    return f"FAM-{index}"
