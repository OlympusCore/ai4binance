"""Normalization utilities for EIEF."""

from ai4binance.external_intel.normalization.deduplication import (
    DuplicateCluster,
    canonicalize_text,
    cluster_duplicates,
)

__all__ = ["DuplicateCluster", "canonicalize_text", "cluster_duplicates"]
