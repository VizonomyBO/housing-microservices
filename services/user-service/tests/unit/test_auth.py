"""
Unit tests for authentication utilities

NOTE: These tests are for Flask-specific auth utilities that are no longer used
in the FastAPI implementation. All tests are skipped.
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="Flask auth utilities no longer used in FastAPI implementation"
)


# All original tests have been removed as they test Flask-specific code
# that is no longer used in the FastAPI implementation.
