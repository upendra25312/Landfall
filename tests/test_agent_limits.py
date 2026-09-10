import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/web'))
from agent_limits import Limits, load_limits
from agent_run import run_response


def test_limits_reject_unbounded_configuration(monkeypatch):
    monkeypatch.setenv('MAX_TOOL_CALLS_PER_TURN', '99999')
    with pytest.raises(ValueError):
        load_limits()


def test_timeout_cancels_background_response():
    client = Mock()
    client.responses.create.return_value = SimpleNamespace(status='in_progress', id='response-1')
    with pytest.raises(TimeoutError):
        asyncio.run(run_response(client, {}, Limits(runtime_seconds=0.01)))
    client.responses.cancel.assert_called_once_with('response-1')


def test_completed_response_forwards_server_limits():
    client = Mock()
    response = SimpleNamespace(status='completed', id='response-1')
    client.responses.create.return_value = response
    assert asyncio.run(run_response(client, {'input': 'test'}, Limits())) == response
    assert client.responses.create.call_args.kwargs['max_tool_calls'] == 16
    assert client.responses.create.call_args.kwargs['max_output_tokens'] == 4000
    client.responses.cancel.assert_not_called()
