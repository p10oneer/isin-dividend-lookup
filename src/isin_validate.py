"""ISO 6166 ISIN format and check-digit validation."""

from __future__ import annotations

import re

_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def normalize_isin(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().upper()
    if text in {"NAN", "NONE", "NAT"}:
        return ""
    return text


def is_header_cell(value: object) -> bool:
    text = normalize_isin(value)
    return text in {"ISIN", "ISINS", "CODE", "IDENTIFIER", "ID"}


def isin_format_ok(isin: str) -> bool:
    return bool(_ISIN_RE.fullmatch(isin))


def _check_digit(body: str) -> int:
    digits: list[int] = []
    for ch in body:
        if ch.isdigit():
            digits.extend(int(d) for d in ch)
        else:
            n = ord(ch) - 55  # A -> 10
            digits.extend(int(d) for d in str(n))
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d = d // 10 + d % 10
        total += d
    return (10 - (total % 10)) % 10


def isin_checksum_ok(isin: str) -> bool:
    if not isin_format_ok(isin):
        return False
    return int(isin[-1]) == _check_digit(isin[:-1])


def corrected_isin(isin: str) -> str | None:
    """Same 11-character body with a valid check digit, or None if format is bad."""
    if len(isin) != 12 or not isin[:2].isalpha() or not isin[2:11].isalnum():
        return None
    return isin[:11] + str(_check_digit(isin[:11]))


def us_cusip(isin: str) -> str | None:
    if len(isin) >= 11 and isin[:2] in {"US", "CA"}:
        return isin[2:11]
    return None


def classify_isin(isin: str) -> str:
    """Return 'ok', 'checksum', or 'invalid'."""
    if not isin_format_ok(isin):
        return "invalid"
    if not isin_checksum_ok(isin):
        return "checksum"
    return "ok"
