import json
import logging
import re
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


def _clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    return max(
        minimum,
        min(value, maximum),
    )


def _extract_json(
    raw_response: str,
) -> str:
    if not isinstance(raw_response, str):
        return ""

    text = raw_response.strip()

    if not text:
        return ""

    # Remove Markdown code fences.
    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s*```$",
        "",
        text,
    )

    text = text.strip()

    # If extra text surrounds the JSON object,
    # try to extract the outermost JSON object.
    if not text.startswith("{"):
        start = text.find("{")

        if start >= 0:
            text = text[start:]

    if not text.endswith("}"):
        end = text.rfind("}")

        if end >= 0:
            text = text[: end + 1]

    return text.strip()


def _safe_result(
    reason: str = "Invalid AI moderation response.",
) -> ModerationResult:
    return ModerationResult(
        violation=False,
        category="none",
        severity=0,
        confidence=0.0,
        reason=reason,
    )


def parse_moderation_result(
    raw_response: str,
) -> ModerationResult:
    """
    Parse and validate AI moderation JSON.

    Invalid AI output is always treated as a
    non-violation. The bot must never punish a
    user because of malformed AI output.
    """

    json_text = _extract_json(
        raw_response
    )

    if not json_text:
        logger.warning(
            "AI returned an empty moderation response."
        )

        return _safe_result()

    try:
        data = json.loads(
            json_text
        )

    except (
        json.JSONDecodeError,
        TypeError,
    ):
        logger.warning(
            "AI returned invalid JSON."
        )

        return _safe_result()

    if not isinstance(data, dict):
        logger.warning(
            "AI moderation response is not an object."
        )

        return _safe_result()

    # -----------------------------------------------------
    # Violation
    # -----------------------------------------------------

    raw_violation = data.get(
        "violation",
        False,
    )

    if isinstance(
        raw_violation,
        bool,
    ):
        violation = raw_violation

    elif isinstance(
        raw_violation,
        str,
    ):
        violation = (
            raw_violation.lower().strip()
            == "true"
        )

    else:
        violation = bool(
            raw_violation
        )

    # -----------------------------------------------------
    # Category
    # -----------------------------------------------------

    category = str(
        data.get(
            "category",
            "none",
        )
    ).lower().strip()

    if category not in ALLOWED_CATEGORIES:
        logger.warning(
            "AI returned unknown category: %s",
            category,
        )

        return _safe_result(
            "AI returned an unknown moderation category."
        )

    # -----------------------------------------------------
    # Severity
    # -----------------------------------------------------

    try:
        severity = int(
            data.get(
                "severity",
                0,
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        severity = 0

    severity = max(
        0,
        min(severity, 3),
    )

    # -----------------------------------------------------
    # Confidence
    # -----------------------------------------------------

    try:
        confidence = float(
            data.get(
                "confidence",
                0.0,
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        confidence = 0.0

    confidence = _clamp(
        confidence,
        0.0,
        1.0,
    )

    # -----------------------------------------------------
    # Reason
    # -----------------------------------------------------

    reason = str(
        data.get(
            "reason",
            "No reason provided.",
        )
    ).strip()

    if not reason:
        reason = "No reason provided."

    # -----------------------------------------------------
    # Normalize non-violation
    # -----------------------------------------------------

    if not violation:
        return ModerationResult(
            violation=False,
            category="none",
            severity=0,
            confidence=confidence,
            reason=reason,
        )

    # A violation without a valid category
    # must never reach the moderation policy.
    if category == "none":
        return _safe_result(
            "AI marked a violation without a valid category."
        )

    # A violation with zero severity is invalid.
    if severity <= 0:
        return _safe_result(
            "AI marked a violation with zero severity."
        )

    return ModerationResult(
        violation=True,
        category=category,
        severity=severity,
        confidence=confidence,
        reason=reason,
    )
