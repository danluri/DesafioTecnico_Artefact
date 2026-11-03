"""Reusable privacy and observability assertions for conversation scenarios."""

from __future__ import annotations

from collections.abc import Iterable

from emporio.conversation import ConversationOutcome
from emporio.observability import SafetyEvent

SYNTHETIC_SENSITIVE_VALUES = (
    "Cliente Sintético A",
    "Cliente Sintético B",
    "00000000000",
    "11111111111",
    "cliente-a@example.invalid",
    "cliente-b@example.invalid",
    "SYNTHETIC-TRACKING",
    "raw prompt: meu telefone é 00000000000",
    "super-secret-provider-payload",
    "SELECT phone FROM customers",
    "DROP TABLE sessions",
    "provider payload must not escape",
)


def assert_private_values_absent(
    values: Iterable[object], *, extra_forbidden: Iterable[str] = ()
) -> None:
    """Fail if any serialized output/event contains synthetic private input."""
    serialized = "\n".join(repr(value) for value in values)
    forbidden = (*SYNTHETIC_SENSITIVE_VALUES, *extra_forbidden)
    leaked = [marker for marker in forbidden if marker in serialized]
    assert not leaked, f"sensitive values leaked: {leaked}"


def assert_conversation_is_private(
    result: ConversationOutcome,
    events: Iterable[SafetyEvent],
    *,
    extra_forbidden: Iterable[str] = (),
) -> None:
    """Scan the user-visible outcome and all emitted events together."""
    event_list = tuple(events)
    assert result.correlation_id
    assert event_list
    assert_private_values_absent(
        (result, *event_list), extra_forbidden=extra_forbidden
    )


def assert_event_contract(
    event: SafetyEvent,
    result: ConversationOutcome,
    *,
    expected_outcome: str,
    expected_tool: str | None,
    error_expected: bool,
) -> None:
    """Check the stable sanitized fields required for operational diagnosis."""
    assert event.correlation_id == result.correlation_id
    assert event.correlation_id
    assert event.provider == "fake"
    assert event.tool == expected_tool
    assert event.duration_ms >= 0
    assert event.outcome == expected_outcome
    if error_expected:
        assert event.error_class
    else:
        assert event.error_class is None

