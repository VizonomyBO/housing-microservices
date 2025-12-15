"""Helpers for normalizing attachment metadata for the Vision subgraph."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from models.retrieval import AttachmentScope


@dataclass(slots=True)
class VisionAttachmentArtifact:
    """Normalized attachment metadata used by vision nodes."""

    document_id: str
    canonical_name: str | None
    mime_type: str | None
    caption: str | None
    chunk_id: str | None
    figure_id: str | None
    content_flags: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def fallback_caption(self, index: int) -> str:
        """Build a deterministic fallback caption when metadata is missing."""

        if self.canonical_name:
            return f"{self.canonical_name} (image {index})"
        return f"Image attachment {index} ({self.document_id})"


def extract_vision_attachments(scope: AttachmentScope | None) -> list[VisionAttachmentArtifact]:
    """Return attachment artifacts that look like images."""

    attachments: list[VisionAttachmentArtifact] = []
    if scope is None:
        return attachments
    for document in scope.documents:
        metadata = document.metadata or {}
        mime_type = _normalize_mime(metadata)
        attachment_category = str(metadata.get("attachment_category") or "").lower()
        if not _looks_like_image(mime_type, attachment_category):
            continue
        content_flags = tuple(
            str(flag).lower() for flag in metadata.get("content_flags", []) if isinstance(flag, str)
        )
        attachments.append(
            VisionAttachmentArtifact(
                document_id=document.document_id,
                canonical_name=document.canonical_name,
                mime_type=mime_type,
                caption=metadata.get("image_caption") or metadata.get("caption"),
                chunk_id=metadata.get("image_caption_chunk_id") or metadata.get("chunk_id"),
                figure_id=metadata.get("figure_id") or metadata.get("image_id"),
                content_flags=content_flags,
                metadata=metadata,
            )
        )
    return attachments


def _normalize_mime(metadata: dict[str, Any]) -> str | None:
    raw = metadata.get("mime_type") or metadata.get("content_type")
    if not raw:
        return None
    return str(raw).lower()


def _looks_like_image(mime_type: str | None, category: str) -> bool:
    return bool(mime_type and mime_type.startswith("image/")) or category in {
        "image",
        "figure",
        "photo",
        "diagram",
    }


__all__ = ["VisionAttachmentArtifact", "extract_vision_attachments"]
