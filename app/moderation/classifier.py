import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


ALLOWED_CATEGORIES = {
    "spam",
    "advertising",
    "scam",
    "harassment",
    "insult",
    "toxicity",
    "threat",
    "flooding",
    "repetition",
    "harmful",
    "suspicious_link",
    "none",
}


@dataclass(slots=True)
class ModerationResult:
    violation: bool
    category: str
    severity: int
    confidence: float
    reason: str


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def parse_moderation_result(raw_response: str) -> ModerationResult:
    """
    Parse and validate the JSON returned by the AI moderator.

    Invalid AI output is treated as a non-violation rather than
    causing an automatic punishment.
    """

    try:
        data = json.loads(raw_response)
    except (json.JSONDecodeError, TypeError):
        logger.warning("AI returned invalid JSON.")
        return ModerationResult(
            violation=False,
            category="none",
            severity=0,
            confidence=0.0,
            reason="Invalid AI moderation response.",
        )

    if not isinstance(data, dict):
        logger.warning("AI moderation response is not an object.")
        return ModerationResult(
            violation=False,
            category="none",
            severity=0,
            confidence=0.0,
            reason="Invalid AI moderation response.",
        )

    violation = bool(data.get("violation", False))

    category = str(data.get("category", "none")).lower().strip()

    if category not in ALLOWED_CATEGORIES:
        category = "none"
        violation = False

    try:
        severity = int(data.get("severity", 0))
    except (TypeError, ValueError):
        severity = 0

    severity = max(0, min(severity, 3))

    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    confidence = _clamp(confidence, 0.0, 1.0)

    reason = str(
        data.get(
            "reason",
            "No reason provided.",
        )
    ).strip()

    if not reason:
        reason = "No reason provided."

    if not violation:
        category = "none"
        severity = 0

    return ModerationResult(
        violation=violation,
        category=category,
        severity=severity,
        confidence=confidence,
        reason=reason,
    )
