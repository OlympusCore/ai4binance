"""Compatibility facade for the canonical runtime artifact layout manifest."""

from ai4binance.infrastructure.filesystem.runtime_artifacts.layout import (
    RuntimeArtifactLayoutManifest,
    default_runtime_artifact_layout_manifest_path,
    load_runtime_artifact_layout_manifest,
)

__all__ = [
    "RuntimeArtifactLayoutManifest",
    "default_runtime_artifact_layout_manifest_path",
    "load_runtime_artifact_layout_manifest",
]
