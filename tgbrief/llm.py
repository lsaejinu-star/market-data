"""Claude API 호출 래퍼 (구조화 출력 + 스트리밍 + 사용량 집계)."""

import base64
import json
import os

import anthropic

ANALYSIS_MODEL = os.environ.get("TG_ANALYSIS_MODEL", "claude-opus-5-5")
SCREEN_MODEL = os.environ.get("TG_SCREEN_MODEL", "claude-haiku-5-5")

_client = None
USAGE = {"input": 0, "output": 0, "calls": 0}


def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(max_retries=4)
    return _client


def image_block(jpeg: bytes):
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.standard_b64encode(jpeg).decode()}}


def ask_json(model, system, content, schema, effort="high", max_tokens=32000):
    """content(블록 리스트)를 보내고 schema에 맞는 JSON(dict)을 돌려준다."""
    kwargs = dict(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": content}],
        output_config={"effort": effort,
                       "format": {"type": "json_schema", "schema": schema}},
    )
    if model in ("claude-opus-5-5", "claude-fable-5-1", "claude-opus-5"):
        # 안전 분류기 오탐으로 거절되면 서버 측에서 다른 모델로 재시도
        kwargs["betas"] = ["server-side-fallback-2026-07-01"]
        kwargs["fallbacks"] = "default"
        stream_ctx = client().beta.messages.stream(**kwargs)
    else:
        stream_ctx = client().messages.stream(**kwargs)
    with stream_ctx as stream:
        msg = stream.get_final_message()
    USAGE["calls"] += 1
    USAGE["input"] += msg.usage.input_tokens
    USAGE["output"] += msg.usage.output_tokens
    if msg.stop_reason == "refusal":
        raise RuntimeError("model refused")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("output truncated (max_tokens)")
    text = next(b.text for b in msg.content if b.type == "text")
    return json.loads(text)
