"""Text normalization helpers for retrieval nodes."""

from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_prompt(text: str) -> str:
    """Trim and squash whitespace inside user prompts."""

    collapsed = _WHITESPACE_RE.sub(" ", text or "")
    return collapsed.strip()
