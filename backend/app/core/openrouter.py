import json
import time
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MODEL_PRICES, OPENROUTER_API_KEY, OPENROUTER_URL
from app.models.llm_call import LLMCall


@dataclass
class ToolCallResult:
    args: dict
    in_tokens: int
    out_tokens: int
    cached_tokens: int
    cost_usd: float
    latency_ms: int
    model: str
    raw: dict


def _calc_cost(model: str, in_tokens: int, out_tokens: int, cached_tokens: int) -> float:
    p = MODEL_PRICES.get(model, {"in": 1.0, "in_cached": 0.1, "out": 1.0})
    return (p["in"] * (in_tokens - cached_tokens) + p["in_cached"] * cached_tokens + p["out"] * out_tokens) / 1_000_000


def _extract_args(raw: dict) -> dict:
    choices = raw.get("choices") or []
    if not choices:
        raise ValueError("OpenRouter returned no choices")
    message = choices[0].get("message") or {}

    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        fn = tool_calls[0].get("function") or {}
        arguments = fn.get("arguments")
        if isinstance(arguments, str):
            return json.loads(arguments)
        if isinstance(arguments, dict):
            return arguments

    content = message.get("content")
    if isinstance(content, str):
        parsed = _try_parse_json(content)
        if isinstance(parsed, dict):
            return parsed
    if isinstance(content, list):
        text_parts = [block.get("text", "") for block in content if isinstance(block, dict)]
        merged = "".join(text_parts).strip()
        if merged:
            parsed = _try_parse_json(merged)
            if isinstance(parsed, dict):
                return parsed

    raise ValueError("No parsable tool arguments in OpenRouter response")


def _try_parse_json(text: str):
    candidate = (text or "").strip()
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except Exception:
        pass
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(candidate[start : end + 1])
        except Exception:
            return None
    return None


def _error_detail(resp: httpx.Response) -> str:
    detail = ""
    try:
        err = resp.json()
        if isinstance(err, dict):
            if isinstance(err.get("error"), dict):
                detail = str(err["error"].get("message", ""))[:600]
            elif "message" in err:
                detail = str(err.get("message", ""))[:600]
    except Exception:
        detail = (resp.text or "")[:600]
    return detail or "request failed"


async def call_tool(call_type: str, model: str, messages: list[dict], tool: dict, *, cache_control_on_system: bool, seed: int, stream: bool = False, session: AsyncSession | None = None, player_id: str | None = None) -> ToolCallResult:
    started = time.perf_counter()

    if not OPENROUTER_API_KEY:
        latency_ms = int((time.perf_counter() - started) * 1000)
        if session:
            session.add(
                LLMCall(
                    player_id=player_id,
                    call_type=call_type,
                    model=model,
                    in_tokens=0,
                    out_tokens=0,
                    cached_tokens=0,
                    cache_hit_ratio=0,
                    cost_usd=0,
                    latency_ms=latency_ms,
                    success=False,
                    error="OPENROUTER_API_KEY not configured",
                )
            )
            await session.commit()
        raise RuntimeError("OPENROUTER_API_KEY not configured")

    # We request non-streaming JSON from OpenRouter because this function
    # parses a single JSON payload and the API routes handle SSE fan-out.
    payload = {"model": model, "messages": messages, "tools": [tool], "tool_choice": {"type": "function", "function": {"name": tool["function"]["name"]}}, "seed": seed, "stream": False}
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
            if not resp.is_success:
                detail = _error_detail(resp)
                # Some Qwen routes on OpenRouter reject forced tool_choice.
                # Retry on the same model with strict JSON-output instruction.
                if resp.status_code == 404 and "tool_choice" in detail.lower():
                    schema = tool.get("function", {}).get("parameters", {"type": "object"})
                    json_only_instruction = (
                        "Return ONLY a valid JSON object. No prose, no markdown, no code fences. "
                        f"The JSON must satisfy this schema: {json.dumps(schema, ensure_ascii=True)}"
                    )
                    retry_messages = list(messages) + [{"role": "user", "content": json_only_instruction}]
                    retry_payload = {"model": model, "messages": retry_messages, "seed": seed, "stream": False}
                    retry_resp = await client.post(OPENROUTER_URL, headers=headers, json=retry_payload)
                    if not retry_resp.is_success:
                        raise RuntimeError(f"OpenRouter {retry_resp.status_code}: {_error_detail(retry_resp)}")
                    raw = retry_resp.json()
                else:
                    raise RuntimeError(f"OpenRouter {resp.status_code}: {detail}")
            else:
                raw = resp.json()

        args = _extract_args(raw)
        usage = raw.get("usage", {})
        in_tokens = int(usage.get("prompt_tokens", 0))
        out_tokens = int(usage.get("completion_tokens", 0))
        cached_tokens = int(usage.get("prompt_tokens_details", {}).get("cached_tokens", 0))
        latency_ms = int((time.perf_counter() - started) * 1000)
        cost = _calc_cost(model, in_tokens, out_tokens, cached_tokens)

        if session:
            session.add(LLMCall(player_id=player_id, call_type=call_type, model=model, in_tokens=in_tokens, out_tokens=out_tokens, cached_tokens=cached_tokens, cache_hit_ratio=(cached_tokens / in_tokens if in_tokens else 0), cost_usd=cost, latency_ms=latency_ms, success=True, error=None))
            await session.commit()

        return ToolCallResult(args, in_tokens, out_tokens, cached_tokens, cost, latency_ms, model, raw)
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        if session:
            session.add(
                LLMCall(
                    player_id=player_id,
                    call_type=call_type,
                    model=model,
                    in_tokens=0,
                    out_tokens=0,
                    cached_tokens=0,
                    cache_hit_ratio=0,
                    cost_usd=0,
                    latency_ms=latency_ms,
                    success=False,
                    error=str(exc)[:2000],
                )
            )
            await session.commit()
        raise
