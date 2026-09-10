"""One application configuration surface for bounded Foundry chat requests."""
import os
from dataclasses import dataclass


def _number(name, default, low, high):
    value = int(os.environ.get(name, default))
    if not low <= value <= high:
        raise ValueError(f'{name} must be between {low} and {high}')
    return value


@dataclass(frozen=True)
class Limits:
    runtime_seconds: int = 180
    tool_calls: int = 16
    retries: int = 0
    conversation_turns: int = 20
    output_tokens: int = 4000
    input_characters: int = 16000
    learn_searches_per_turn: int = 3
    learn_fetches_per_turn: int = 2


def load_limits():
    return Limits(
        _number('MAX_AGENT_RUNTIME_SECONDS', 180, 10, 600),
        _number('MAX_TOOL_CALLS_PER_TURN', 16, 1, 32),
        _number('MAX_TOOL_RETRIES', 0, 0, 0),
        _number('MAX_CONVERSATION_TURNS', 20, 1, 100),
        _number('MAX_OUTPUT_TOKENS', 4000, 128, 16000),
        _number('MAX_INPUT_CHARACTERS', 16000, 100, 64000),
        _number('MAX_LEARN_SEARCHES_PER_TURN', 3, 1, 10),
        _number('MAX_LEARN_FETCHES_PER_TURN', 2, 1, 10),
    )
