"""Small boundary normalizer for customer-facing UTF-8 text."""

from __future__ import annotations


def normalize_customer_text(value: str) -> str:
    """Repair common UTF-8-as-Latin-1 corruption at customer-facing boundaries."""
    if not isinstance(value, str):
        raise TypeError("customer text must be a string")
    text = value.strip()
    markers = (chr(0xC3), chr(0xC2), chr(0xE2), chr(0xFFFD))
    for _ in range(3):
        if not any(marker in text for marker in markers):
            break
        try:
            repaired = text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if repaired == text:
            break
        text = repaired
    return text
