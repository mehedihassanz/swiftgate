"""PII redaction service — strips sensitive data before sending to providers.

Two modes:
  1. Redact: Replace PII with [REDACTED_TYPE] tokens before the upstream call
  2. Rehydrate: Restore original PII values in the response (via token mapping)

This enables:
  - Enterprise data residency (PII never leaves SwiftGate)
  - Compliance: GDPR, HIPAA, SOC2
  - Audit logging: see what was redacted per request

Public API:
    redact_messages(messages) -> (redacted_messages, token_map)
    rehydrate_response(response, token_map) -> response_with_real_pii
    detect_pii(text) -> list[PiiMatch]
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PiiMatch:
    """A detected PII entity within text."""
    pii_type: str           # "email", "phone", "ssn", "credit_card", "api_key"
    original: str           # the actual matched text
    placeholder: str        # the replacement token
    start: int              # character offset in original text
    end: int


@dataclass
class TokenMap:
    """Mapping of placeholders → original PII values for rehydration."""
    _placeholders: dict[str, str] = field(default_factory=dict)

    def add(self, original: str, placeholder: str) -> None:
        self._placeholders[placeholder] = original

    def rehydrate(self, text: str) -> str:
        """Replace all placeholders with their original values."""
        for placeholder, original in self._placeholders.items():
            text = text.replace(placeholder, original)
        return text

    def __len__(self) -> int:
        return len(self._placeholders)

    def to_log(self) -> list[dict]:
        """Return a safe log of what was redacted (types + count, not values)."""
        types: dict[str, int] = {}
        for placeholder in self._placeholders:
            # Format: "[REDACTED_EMAIL_abc123]" → "email"
            match = re.match(r"\[REDACTED_(\w+?)_[^\]]+\]", placeholder)
            if match:
                t = match.group(1).lower()
                types[t] = types.get(t, 0) + 1
        return [{"type": k, "count": v} for k, v in sorted(types.items())]


# ─── PII Detection Patterns ────────────────────────────────────────────

# Each pattern: (name, compiled_regex, redaction_template)
# Regexes are deliberately conservative — false negatives are acceptable
# (we just don't redact), false positives are not (we'd redact real content).
_PII_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # Email addresses
    (
        "EMAIL",
        re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        ),
        "[REDACTED_EMAIL_{}]",
    ),

    # Phone numbers (US + international, 10-15 digits)
    (
        "PHONE",
        re.compile(
            r"(?<!\d)"
            r"(?:\+?1[-.\s]?)?"  # optional country code
            r"\(?\d{3}\)?[-.\s]?"
            r"\d{3}[-.\s]?"
            r"\d{4}"
            r"(?!\d)"
        ),
        "[REDACTED_PHONE_{}]",
    ),

    # SSN (US Social Security Numbers)
    (
        "SSN",
        re.compile(r"\b(?!000|666|9\d{2})([0-8]\d{2})-(?!00)\d{2}-(?!0000)\d{4}\b"),
        "[REDACTED_SSN_{}]",
    ),

    # Credit card numbers (13-19 digits with typical grouping — must have spaces/dashes)
    (
        "CREDIT_CARD",
        re.compile(
            r"\b(?:\d{4}[- ]?){3}\d{1,4}\b"  # 4-4-4-(1-4) pattern: 13-19 digits
        ),
        "[REDACTED_CREDIT_CARD_{}]",
    ),

    # API keys / bearer tokens (common formats — including SwiftGate sg- keys)
    (
        "API_KEY",
        re.compile(
            r"\b(?:sk-|pk-|rk-|sg-|Bearer )"
            r"[A-Za-z0-9]{20,}"
        ),
        "[REDACTED_API_KEY_{}]",
    ),

    # IBAN (international bank account)
    (
        "IBAN",
        re.compile(
            r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}(?:[ ]?\d{3,4}){1,7}\b"
        ),
        "[REDACTED_IBAN_{}]",
    ),

    # IP addresses (IPv4)
    (
        "IP_ADDRESS",
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"
            r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
        ),
        "[REDACTED_IP_{}]",
    ),
]

# Public-facing pattern info (safe to expose — no regex internals needed)


def _describe(name: str) -> str:
    descriptions = {
        "EMAIL": "Email addresses",
        "PHONE": "Phone numbers (US + international)",
        "SSN": "US Social Security Numbers",
        "CREDIT_CARD": "Credit card numbers (13-19 digits)",
        "API_KEY": "API keys and Bearer tokens",
        "IBAN": "International Bank Account Numbers",
        "IP_ADDRESS": "IPv4 addresses",
    }
    return descriptions.get(name, name)


PII_PATTERNS_INFO = [
    {"type": name, "description": _describe(name)}
    for name, _, _ in _PII_PATTERNS
]


def detect_pii(text: str) -> list[PiiMatch]:
    """Detect all PII entities in a text string.

    Returns list of PiiMatch objects with positions and placeholders.
    """
    if not text:
        return []

    matches: list[PiiMatch] = []

    for pii_type, pattern, template in _PII_PATTERNS:
        for m in pattern.finditer(text):
            # Skip if this span overlaps with an already-detected match
            overlap = False
            for existing in matches:
                if (m.start() < existing.end and m.end() > existing.start):
                    overlap = True
                    break
            if overlap:
                continue

            # Generate a short unique ID for the placeholder
            short_id = uuid.uuid4().hex[:8]
            placeholder = template.format(short_id)

            matches.append(PiiMatch(
                pii_type=pii_type,
                original=m.group(),
                placeholder=placeholder,
                start=m.start(),
                end=m.end(),
            ))

    # Sort by position
    matches.sort(key=lambda x: x.start)
    return matches


def redact_text(text: str, token_map: TokenMap) -> str:
    """Redact PII in a single text string, populating the token_map.

    Returns the redacted text. The token_map is updated in-place with
    placeholder → original mappings for later rehydration.
    """
    if not text:
        return text

    matches = detect_pii(text)
    if not matches:
        return text

    # Build redacted text by replacing from end to start (preserves offsets)
    result = text
    for m in reversed(matches):
        result = result[:m.start] + m.placeholder + result[m.end:]
        token_map.add(m.original, m.placeholder)

    return result


def redact_messages(messages: list[dict]) -> tuple[list[dict], TokenMap]:
    """Redact PII across all messages.

    Returns:
      - new messages list with PII replaced by placeholders
      - TokenMap for rehydrating the response
    """
    token_map = TokenMap()
    redacted: list[dict] = []

    for msg in messages:
        new_msg = dict(msg)
        content = msg.get("content")

        if isinstance(content, str):
            new_msg["content"] = redact_text(content, token_map)

        elif isinstance(content, list):
            # Vision/multipart format
            new_content = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    block = dict(block)
                    block["text"] = redact_text(block.get("text", ""), token_map)
                new_content.append(block)
            new_msg["content"] = new_content

        redacted.append(new_msg)

    if len(token_map) > 0:
        logger.info(f"Redacted {len(token_map)} PII entities: {token_map.to_log()}")

    return redacted, token_map


def rehydrate_response(response: dict, token_map: TokenMap) -> dict:
    """Restore original PII values in the model's response.

    Scans the response text for placeholder tokens and replaces them
    with the original PII values from the token_map.
    """
    if not token_map or len(token_map) == 0:
        return response

    # Deep-copy to avoid mutating the original
    import copy
    result = copy.deepcopy(response)

    # Rehydrate choices[].message.content
    for choice in result.get("choices", []):
        message = choice.get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            message["content"] = token_map.rehydrate(content)

    return result


def rehydrate_streaming_chunk(chunk: dict, token_map: TokenMap) -> dict:
    """Rehydrate a single streaming chunk (SSE delta)."""
    if not token_map or len(token_map) == 0:
        return chunk

    import copy
    result = copy.deepcopy(chunk)

    for choice in result.get("choices", []):
        delta = choice.get("delta", {})
        content = delta.get("content")
        if isinstance(content, str):
            delta["content"] = token_map.rehydrate(content)

    return result
