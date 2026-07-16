import json
import os
from typing import Annotated, Any

import httpx
from pydantic import BaseModel, ConfigDict, StringConstraints

from app import tools

QWEN_CHAT_COMPLETIONS_URL = os.getenv(
    "DASHSCOPE_BASE_URL",
    "https://llm-0nsl26x7l7v72b8i.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
).rstrip("/") + "/chat/completions"
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen3.7-plus")
QWEN_TIMEOUT_SECONDS = 30.0
MAX_TOOL_ROUNDS = 4

TOOL_NAMES = {
    "get_current_forecast",
    "get_match_prediction",
    "compare_snapshots",
    "get_model_card",
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_current_forecast",
            "description": "返回最新快照的冠军概率、剩余赛程和完整来源信息。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_match_prediction",
            "description": "返回指定剩余比赛在最新快照中的预测。",
            "parameters": {
                "type": "object",
                "properties": {
                    "match_id": {
                        "type": "integer",
                        "description": "显式配置的比赛 ID。",
                    }
                },
                "required": ["match_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_snapshots",
            "description": "比较两个不可覆盖快照的球队概率变化和新增真实赛果。",
            "parameters": {
                "type": "object",
                "properties": {
                    "base_snapshot_id": {"type": "string"},
                    "target_snapshot_id": {"type": "string"},
                },
                "required": ["base_snapshot_id", "target_snapshot_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_model_card",
            "description": "返回模型算法、回测指标、来源、限制和免责声明。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
]

SYSTEM_PROMPT = """你是 CupLens 的单一解释 Agent。
只能引用工具结果中的数值；禁止重新计算、四舍五入后改写或补全缺失概率。
工具失败时明确说明无法获取，不得凭常识回答数值。
回答必须注明快照 ID、数据截止时间和模型版本。
必须区分真实赛果、模型预测和用户假设。
不提供博彩建议，也不得透露或索取 API Key。
你只负责选择给定工具并解释其确定性输出。"""

Question = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Question


def validate_tool_name(name: str) -> str:
    if name not in TOOL_NAMES:
        raise ValueError(f"unsupported tool: {name}")
    return name


def _validate_arguments(name: str, arguments: Any) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must be an object")
    if name in {"get_current_forecast", "get_model_card"}:
        if arguments:
            raise ValueError(f"{name} does not accept arguments")
    elif name == "get_match_prediction":
        if set(arguments) != {"match_id"} or type(arguments["match_id"]) is not int:
            raise ValueError("get_match_prediction requires an integer match_id")
    elif name == "compare_snapshots":
        if set(arguments) != {"base_snapshot_id", "target_snapshot_id"}:
            raise ValueError("compare_snapshots requires both snapshot IDs")
        if not all(
            isinstance(arguments[field], str)
            for field in ("base_snapshot_id", "target_snapshot_id")
        ):
            raise ValueError("snapshot IDs must be strings")
    return arguments


def _execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    validate_tool_name(name)
    validated = _validate_arguments(name, arguments)
    if name == "get_current_forecast":
        return tools.get_current_forecast()
    if name == "get_match_prediction":
        return tools.get_match_prediction(validated["match_id"])
    if name == "compare_snapshots":
        return tools.compare_snapshots(
            validated["base_snapshot_id"], validated["target_snapshot_id"]
        )
    return tools.get_model_card()


def _request_qwen(
    api_key: str,
    messages: list[dict[str, Any]],
    *,
    require_tool: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": QWEN_MODEL,
        "messages": messages,
        "tools": TOOL_SCHEMAS,
        "parallel_tool_calls": False,
        "enable_thinking": False,
    }
    if require_tool:
        payload["tool_choice"] = "required"
    response = httpx.post(
        QWEN_CHAT_COMPLETIONS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=QWEN_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("Qwen response must be an object")
    return body


def _message_from_response(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("Qwen response must contain exactly one choice")
    message = choices[0].get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise ValueError("Qwen response is missing an assistant message")
    return message


def _parse_tool_call(message: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list) or len(tool_calls) != 1:
        raise ValueError("Qwen must request exactly one tool per round")
    tool_call = tool_calls[0]
    if not isinstance(tool_call, dict) or tool_call.get("type") != "function":
        raise ValueError("invalid tool call")
    call_id = tool_call.get("id")
    function = tool_call.get("function")
    if not isinstance(call_id, str) or not call_id or not isinstance(function, dict):
        raise ValueError("invalid tool call metadata")
    name = validate_tool_name(function.get("name"))
    raw_arguments = function.get("arguments")
    if not isinstance(raw_arguments, str):
        raise ValueError("tool arguments must be JSON text")
    arguments = _validate_arguments(name, json.loads(raw_arguments))
    return call_id, name, arguments


def _snapshot_context(structured_data: dict[str, Any]) -> tuple[str, str, str]:
    if "snapshot_id" in structured_data:
        provenance = structured_data
    else:
        provenance = structured_data["target"]
    return (
        provenance["snapshot_id"],
        provenance["cutoff_at"],
        provenance["model_version"],
    )


def _template_response(
    structured_data: dict[str, Any],
    completed_tool_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    snapshot_id, cutoff_at, model_version = _snapshot_context(structured_data)
    answer = (
        "智能解释暂不可用，以下为模型结构化结果。"
        f"快照 ID：{snapshot_id}；数据截止时间：{cutoff_at}；"
        f"模型版本：{model_version}。"
        "请区分真实赛果、模型预测和用户假设；本结果不构成博彩建议。"
    )
    return {
        "mode": "template",
        "answer": answer,
        "tool_calls": (
            [{"name": "get_current_forecast", "arguments": {}}]
            if completed_tool_calls is None
            else completed_tool_calls
        ),
        "structured_data": structured_data,
        "snapshot_id": snapshot_id,
    }


def _qwen_response(
    content: str,
    structured_data: dict[str, Any],
    completed_tool_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    snapshot_id, cutoff_at, model_version = _snapshot_context(structured_data)
    answer = (
        "数值以结构化卡片为准。"
        f"快照 ID：{snapshot_id}；数据截止时间：{cutoff_at}；"
        f"模型版本：{model_version}。"
        "以下内容须区分真实赛果、模型预测和用户假设，且不构成博彩建议。\n"
        f"{content}"
    )
    return {
        "mode": "qwen",
        "answer": answer,
        "tool_calls": completed_tool_calls,
        "structured_data": structured_data,
        "snapshot_id": snapshot_id,
    }


def answer_question(question: str) -> dict[str, Any]:
    fallback_data = tools.get_current_forecast()
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        return _template_response(fallback_data)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    completed_tool_calls: list[dict[str, Any]] = []
    structured_data: dict[str, Any] | None = None
    tool_rounds = 0
    try:
        while True:
            response = _request_qwen(
                api_key, messages, require_tool=structured_data is None
            )
            message = _message_from_response(response)
            remote_tool_calls = message.get("tool_calls")
            if not remote_tool_calls:
                content = message.get("content")
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("Qwen response is missing final text")
                if structured_data is None:
                    raise ValueError("Qwen returned text before using a tool")
                return _qwen_response(
                    content.strip(), structured_data, completed_tool_calls
                )

            if tool_rounds >= MAX_TOOL_ROUNDS:
                raise ValueError("maximum tool rounds exceeded")
            call_id, name, arguments = _parse_tool_call(message)
            result = _execute_tool(name, arguments)
            completed_tool_calls.append({"name": name, "arguments": arguments})
            structured_data = result
            tool_rounds += 1
            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": remote_tool_calls,
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(
                        result,
                        ensure_ascii=False,
                        sort_keys=True,
                        allow_nan=False,
                    ),
                }
            )
    except Exception:
        return _template_response(
            structured_data or fallback_data,
            completed_tool_calls,
        )
