from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModerationDecision:
    action: str
    reason: str


VALID_ACTIONS = {
    "ignore",
    "warn",
    "delete",
    "restrict",
}


VALID_STRICTNESS = {
    "low",
    "medium",
    "high",
}


def normalize_strictness(strictness: str) -> str:
    value = strictness.lower().strip()

    if value not in VALID_STRICTNESS:
        return "medium"

    return value


def normalize_action(action: str) -> str:
    value = action.lower().strip()

    if value not in VALID_ACTIONS:
        return "warn"

    return value


def decide_action(
    *,
    violation: bool,
    category: str,
    severity: int,
    confidence: float,
    strictness: str,
    configured_action: str,
) -> ModerationDecision:
    """
    Convert an AI moderation result into a safe moderation action.

    The AI does not directly control Telegram.
    This function applies our own deterministic policy.
    """

    if not violation:
        return ModerationDecision(
            action="ignore",
            reason="No violation detected.",
        )

    strictness = normalize_strictness(strictness)
    configured_action = normalize_action(configured_action)

    if confidence < 0.70:
        return ModerationDecision(
            action="ignore",
            reason="AI confidence is too low.",
        )

    if severity <= 0:
        return ModerationDecision(
            action="ignore",
            reason="Violation severity is zero.",
        )

    if strictness == "low":
        if severity < 3:
            return ModerationDecision(
                action="warn",
                reason=(
                    f"Low strictness: {category} "
                    "requires a warning."
                ),
            )

    if strictness == "medium":
        if severity == 1:
            return ModerationDecision(
                action="warn",
                reason=(
                    f"Medium strictness: minor {category} "
                    "violation."
                ),
            )

    if strictness == "high":
        if severity == 1:
            return ModerationDecision(
                action="delete",
                reason=(
                    f"High strictness: minor {category} "
                    "violation."
                ),
            )

    return ModerationDecision(
        action=configured_action,
        reason=(
            f"Moderation policy selected '{configured_action}' "
            f"for {category} with severity {severity}."
        ),
    )
