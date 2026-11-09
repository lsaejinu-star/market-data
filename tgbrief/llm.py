"""Claude 호출 래퍼 — Claude Code CLI(`claude -p`)를 구독 토큰으로 실행한다.

- 인증: 환경변수 CLAUDE_CODE_OAUTH_TOKEN (`claude setup-token`으로 발급, 1년 유효).
  ANTHROPIC_API_KEY가 있으면 그쪽이 우선되므로 하위 프로세스에서는 제거한다.
- 이미지는 임시 폴더에 파일로 저장하고 Claude가 Read 도구로 직접 열어 본다.
- 결과는 --json-schema 로 받은 structured_output(dict)을 돌려준다.
- 구독 사용량 한도를 함께 쓰므로 호출 수·분량을 최소화하도록 상위 모듈에서 상한을 둔다.
"""

import json
import os
import subprocess
import tempfile
import time

ANALYSIS_MODEL = os.environ.get("TG_ANALYSIS_MODEL") or "claude-opus-5-5"
SCREEN_MODEL = os.environ.get("TG_SCREEN_MODEL") or "claude-haiku-5-5"
CALL_TIMEOUT = int(os.environ.get("TG_CALL_TIMEOUT", "1800"))
RETRIES = int(os.environ.get("TG_RETRIES", "2"))  # 실패 시 재시도 횟수(일시 과부하·네트워크·시간 초과 대비)

USAGE = {"input": 0, "output": 0, "calls": 0, "cost_usd": 0.0}


def image_block(jpeg: bytes):
    """content 리스트에 넣을 이미지 블록(실행 시 파일로 저장된다)."""
    return {"type": "image", "jpeg": jpeg}


def _build_prompt(content, workdir):
    parts, n_img = [], 0
    for blk in content:
        if blk["type"] == "text":
            parts.append(blk["text"])
        else:
            path = os.path.join(workdir, f"img_{n_img:03d}.jpg")
            with open(path, "wb") as fp:
                fp.write(blk["jpeg"])
            parts.append(f"[이미지 파일: {path}]")
            n_img += 1
    if n_img:
        parts.insert(0, f"이 요청에는 이미지 파일 {n_img}개가 있다. 본문에 표시된 '[이미지 파일: 경로]'를 "
                        "Read 도구로 하나도 빠짐없이 열어 보고 답하라.\n")
    return "\n".join(parts), n_img


def ask_json(model, system, content, schema, effort="high", max_tokens=None, tools=("Read",), max_turns=None):
    """실패하면 RETRIES회까지 30초·90초 간격으로 다시 시도한다."""
    last = None
    for attempt in range(RETRIES + 1):
        try:
            return _ask_once(model, system, content, schema, tools, max_turns)
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < RETRIES:
                print(f"[llm] 호출 실패({e.__class__.__name__}) → {30 * (attempt * 2 + 1)}초 후 재시도 {attempt + 1}/{RETRIES}", flush=True)
                time.sleep(30 * (attempt * 2 + 1))
    raise last


def _ask_once(model, system, content, schema, tools, max_turns):
    """content(텍스트·이미지 블록 리스트)를 보내고 schema에 맞는 dict를 돌려준다.
    tools: 허용 도구(기본 Read만. 매크로 조사는 WebSearch·WebFetch 추가)."""
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    if not env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        raise RuntimeError("CLAUDE_CODE_OAUTH_TOKEN 이 설정되지 않음")
    with tempfile.TemporaryDirectory(prefix="tgbrief_") as workdir:
        prompt, n_img = _build_prompt(content, workdir)
        cmd = [
            "claude", "-p",
            "--model", model,
            "--output-format", "json",
            "--json-schema", json.dumps(schema, ensure_ascii=False),
            # 기본 시스템 프롬프트·도구·스킬·MCP를 빼서 호출당 토큰(=구독 사용량)을 최소화
            "--system-prompt", system,
            "--tools", ",".join(tools),
            "--allowedTools", ",".join(tools),
            "--disable-slash-commands",
            "--strict-mcp-config",
            "--setting-sources", "",
            "--permission-mode", "dontAsk",
            "--max-turns", str(max_turns or (n_img + 8)),
        ]
        # 저장소 밖 빈 임시 폴더에서 실행 → 저장소의 설정·훅이 로드되지 않음. 프롬프트는 stdin으로 전달.
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                              cwd=workdir, env=env, timeout=CALL_TIMEOUT)
    USAGE["calls"] += 1
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"claude CLI 응답 파싱 실패 (exit {proc.returncode}): {proc.stderr[-300:]}")
    usage = out.get("usage") or {}
    USAGE["input"] += int(usage.get("input_tokens", 0)) + int(usage.get("cache_read_input_tokens", 0))
    USAGE["output"] += int(usage.get("output_tokens", 0))
    USAGE["cost_usd"] += float(out.get("total_cost_usd") or 0)
    if out.get("is_error") or "structured_output" not in out:
        raise RuntimeError(f"구조화 결과 없음 (subtype={out.get('subtype')})")
    return out["structured_output"]
