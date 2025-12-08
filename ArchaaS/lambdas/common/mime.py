"""MIME type detection and validation utilities."""

import os

# Try to import python-magic, fall back to simple extension-based detection
try:
    import magic

    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False


# Allowed MIME types and their extensions
ALLOWED_MIME_TYPES = {
    "application/pdf": ["pdf"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ["docx"],
    "application/msword": ["doc"],
    "text/html": ["html", "htm"],
    "text/csv": ["csv"],
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ["xlsx"],
    "application/vnd.ms-excel": ["xls"],
    "text/plain": ["txt"],
    "text/markdown": ["md"],
}

# Extension to MIME type mapping
EXTENSION_TO_MIME = {}
for mime, exts in ALLOWED_MIME_TYPES.items():
    for ext in exts:
        EXTENSION_TO_MIME[ext] = mime


def detect_mime_type(
    file_path: str | None = None,
    file_content: bytes | None = None,
    filename: str | None = None,
) -> tuple[str, str]:
    """
    Detect the MIME type of a file.

    Args:
        file_path: Path to the file (for magic-based detection)
        file_content: File content bytes (for magic-based detection)
        filename: Filename with extension (for extension-based fallback)

    Returns:
        Tuple of (mime_type, detection_method)
        detection_method is either "magic" or "extension"
    """
    detected_mime = None
    method = "unknown"

    # Try python-magic first (most accurate)
    if HAS_MAGIC:
        try:
            if file_path and os.path.exists(file_path):
                detected_mime = magic.from_file(file_path, mime=True)
                method = "magic"
            elif file_content:
                detected_mime = magic.from_buffer(file_content, mime=True)
                method = "magic"
        except Exception:
            pass

    # Fall back to extension-based detection
    if not detected_mime and filename:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else None
        if ext and ext in EXTENSION_TO_MIME:
            detected_mime = EXTENSION_TO_MIME[ext]
            method = "extension"

    return detected_mime or "application/octet-stream", method


def validate_mime_type(
    mime_type: str,
    expected_type: str | None = None,
) -> tuple[bool, str | None]:
    """
    Validate that a MIME type is allowed for ingestion.

    Args:
        mime_type: The detected MIME type
        expected_type: Optional expected type to match against

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check if MIME type is in allowed list
    if mime_type not in ALLOWED_MIME_TYPES:
        allowed = ", ".join(ALLOWED_MIME_TYPES.keys())
        return (
            False,
            f"MIME type '{mime_type}' is not allowed. Allowed types: {allowed}",
        )

    # Check against expected type if provided
    if expected_type and mime_type != expected_type:
        return (
            False,
            f"MIME type mismatch: expected '{expected_type}', got '{mime_type}'",
        )

    return True, None


def get_source_type_from_mime(mime_type: str) -> str | None:
    """
    Get the source_type (file extension) from a MIME type.

    Args:
        mime_type: The MIME type

    Returns:
        The primary file extension for this MIME type, or None
    """
    extensions = ALLOWED_MIME_TYPES.get(mime_type)
    return extensions[0] if extensions else None
