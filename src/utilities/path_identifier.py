"""Path identifier utilities.

Provides deterministic, reversible, filesystem-safe identifiers for arbitrary
Windows paths using URL-safe base64 of UTF-8 bytes. The mapping is purely
algorithmic (no sidecar files). Normalizes Unicode to NFC before encoding.

Design notes:
- Uses urlsafe base64 and strips '=' padding to keep tokens filename-safe.
- Prefixes tokens with 'b64_' so we can recognize the format when decoding.
- Guards against Windows reserved device names by prefixing '_' if needed.
"""

from __future__ import annotations

import base64
import binascii
import unicodedata
from typing import Final

# Windows reserved device names (case-insensitive)
_RESERVED: Final[set[str]] = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def _normalize(s: str) -> str:
    """Normalize Unicode to NFC for deterministic behavior."""
    return unicodedata.normalize("NFC", s)


def encode_path(path: str) -> str:
    r"""Encode an arbitrary path into a filesystem-safe token.

    The token is deterministic and reversible. It is safe for use as a
    filename or database key on Windows (uses only A-Za-z0-9_- and an ASCII
    prefix). Caller must be aware of overall length limits (Windows MAX_PATH).

    Example: encode_path(r"C:\\Users\\ä\\file.txt") -> 'b64_<...>'
    """
    if not isinstance(path, str):
        raise TypeError("path must be a str")

    normalized = _normalize(path)
    data = normalized.encode("utf-8")
    b64 = base64.urlsafe_b64encode(data).decode("ascii")
    # strip padding to make tokens shorter and still reversible (we re-pad on decode)
    b64 = b64.rstrip("=")
    token = "b64_" + b64
    # Guard against accidental reserved device names (case-insensitive)
    if token.upper() in _RESERVED:
        token = "_" + token
    return token


def decode_path(token: str) -> str:
    """Decode a token previously produced by encode_path back to the original path.

    Raises ValueError if the token format is not recognized or decoding fails.
    """
    if not isinstance(token, str):
        raise TypeError("token must be a str")

    # handle the optional leading '_' used when token matched a reserved name
    if token.startswith("_"):
        token = token[1:]

    if not token.startswith("b64_"):
        raise ValueError("unsupported token format")

    b64 = token[4:]
    # restore padding
    pad_len = (-len(b64)) % 4
    b64_padded = b64 + ("=" * pad_len)
    try:
        data = base64.urlsafe_b64decode(b64_padded.encode("ascii"))
    except (ValueError, binascii.Error) as exc:  # pragma: no cover - defensive
        raise ValueError("invalid base64 token") from exc

    return data.decode("utf-8")


__all__ = ["decode_path", "encode_path"]
