"""
Security utilities for password hashing and token generation
"""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Initialize Argon2 password hasher with secure parameters
ph = PasswordHasher(
    time_cost=2,  # Number of iterations
    memory_cost=65536,  # Memory usage in KiB (64 MB)
    parallelism=4,  # Number of parallel threads
    hash_len=32,  # Length of the hash in bytes
    salt_len=16,  # Length of the salt in bytes
)


def hash_password(password: str) -> str:
    """
    Hash a password using Argon2id algorithm.

    Args:
        password: Plain text password to hash

    Returns:
        Hashed password string
    """
    return ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """
    Verify a password against its hash.

    Args:
        password_hash: The stored password hash
        password: The plain text password to verify

    Returns:
        True if password matches, False otherwise
    """
    try:
        ph.verify(password_hash, password)

        # Check if rehashing is needed (parameters changed)
        if ph.check_needs_rehash(password_hash):
            # In production, you might want to update the hash in the database
            pass

        return True
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def generate_reset_token(length: int = 32) -> str:
    """
    Generate a secure random token for password reset.

    Args:
        length: Length of the token in bytes (will be hex encoded, so actual length is 2x)

    Returns:
        Secure random token as hex string
    """
    return secrets.token_urlsafe(length)
