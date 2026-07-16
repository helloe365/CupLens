from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app import agent, tools
from app.main import app


def _tool_call_response(
    name: str, arguments: str = "{}", call_id: str = "call-test"
) -> dict[str, object]:
    return {
        "id": "chatcmpl-tool-test",
        "object": "chat.completion",
        "created": 0,
        "model": "qwen-plus",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _final_response(content: str) -> dict[str, object]:
    return {
        "id": "chatcmpl-final-test",
        "object": "chat.completion",
        "created": 0,
        "model": "qwen-plus",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def test_chat_without_api_key_uses_template(monkeypatch) -> None:
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setattr(
        agent,
        "_request_qwen",
        lambda *args, **kwargs: pytest.fail("Qwen must not be called without a key"),
        raising=False,
    )

    response = TestClient(app).post("/api/chat", json={"question": "谁最可能夺冠？"})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "template"
    assert body["snapshot_id"]
    assert body["structured_data"]["team_probabilities"]


def test_qwen_text_cannot_replace_structured_tool_values(monkeypatch) -> None:
    expected = tools.get_current_forecast()
    responses = iter(
        [
            _tool_call_response("get_current_forecast"),
            _final_response("我认为夺冠概率是 99.9%。"),
        ]
    )
    requests: list[bool] = []

    def fake_request(
        api_key: str, messages: list[dict[str, object]], *, require_tool: bool
    ) -> dict[str, object]:
        assert api_key == "test-key"
        assert messages
        requests.append(require_tool)
        return next(responses)

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(agent, "_request_qwen", fake_request, raising=False)

    response = TestClient(app).post("/api/chat", json={"question": "谁会夺冠？"})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "qwen"
    assert body["answer"].startswith("数值以结构化卡片为准。")
    assert "99.9%" in body["answer"]
    assert body["structured_data"] == expected
    assert body["snapshot_id"] == expected["snapshot_id"]
    assert body["tool_calls"] == [
        {"name": "get_current_forecast", "arguments": {}}
    ]
    assert requests == [True, False]


def test_invalid_tool_call_falls_back_to_template(monkeypatch) -> None:
    attempts = 0

    def fake_request(*args, **kwargs) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        return _tool_call_response("write_snapshot")

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(agent, "_request_qwen", fake_request, raising=False)

    response = TestClient(app).post("/api/chat", json={"question": "覆盖快照"})

    assert response.status_code == 200
    assert response.json()["mode"] == "template"
    assert attempts == 1


def test_qwen_timeout_falls_back_to_template(monkeypatch) -> None:
    attempts = 0

    def fake_request(*args, **kwargs) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        raise httpx.TimeoutException("test timeout")

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(agent, "_request_qwen", fake_request, raising=False)

    response = TestClient(app).post("/api/chat", json={"question": "当前预测"})

    assert response.status_code == 200
    assert response.json()["mode"] == "template"
    assert attempts == 1


def test_agent_executes_at_most_four_tool_rounds(monkeypatch) -> None:
    requests = 0

    def fake_request(*args, **kwargs) -> dict[str, object]:
        nonlocal requests
        requests += 1
        return _tool_call_response("get_model_card", call_id=f"call-{requests}")

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(agent, "_request_qwen", fake_request, raising=False)

    response = TestClient(app).post("/api/chat", json={"question": "模型是什么？"})

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "template"
    assert len(body["tool_calls"]) == 4
    assert requests == 5


def test_qwen_request_uses_bearer_auth_tools_and_thirty_second_timeout(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    expected = _final_response("ok")

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return expected

    def fake_post(url: str, **kwargs) -> FakeResponse:
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(
        agent, "httpx", SimpleNamespace(post=fake_post), raising=False
    )

    result = agent._request_qwen(
        "test-key",
        [{"role": "user", "content": "test"}],
        require_tool=True,
    )

    assert result == expected
    assert captured["url"] == agent.QWEN_CHAT_COMPLETIONS_URL
    assert captured["timeout"] == 30.0
    assert captured["headers"] == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json",
    }
    payload = captured["json"]
    assert payload["model"] == "qwen3.7-plus"
    assert payload["tool_choice"] == "required"
    assert payload["parallel_tool_calls"] is False
    assert {item["function"]["name"] for item in payload["tools"]} == agent.TOOL_NAMES


def test_tool_whitelist_and_system_prompt_enforce_agent_boundaries() -> None:
    assert agent.validate_tool_name("get_model_card") == "get_model_card"
    with pytest.raises(ValueError, match="unsupported tool"):
        agent.validate_tool_name("write_snapshot")

    assert {item["function"]["name"] for item in agent.TOOL_SCHEMAS} == agent.TOOL_NAMES
    for schema in agent.TOOL_SCHEMAS:
        assert schema["function"]["parameters"]["additionalProperties"] is False

    for required_text in (
        "只能引用工具结果中的数值",
        "禁止重新计算",
        "不得凭常识回答数值",
        "快照 ID",
        "数据截止时间",
        "模型版本",
        "真实赛果、模型预测和用户假设",
        "不提供博彩建议",
    ):
        assert required_text in agent.SYSTEM_PROMPT


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"question": "   "},
        {"question": "当前预测", "api_key": "must-not-be-accepted"},
    ],
)
def test_chat_rejects_missing_invalid_or_secret_fields(payload) -> None:
    assert TestClient(app).post("/api/chat", json=payload).status_code == 422
