"""`look(question)`: answer one question about the screen without sending the image to the main agent.

Backends, tried in order:
1. MCP sampling. The server asks the host agent's client for a model call and asks for a small, fast model.
   No key, no download. Works only if the client supports sampling.
2. An OpenAI-compatible chat endpoint (Ollama, LM Studio, vLLM, or a hosted API):
   DROIDPILOT_VISION_URL (e.g. http://127.0.0.1:11434/v1/chat/completions), DROIDPILOT_VISION_MODEL,
   and optionally DROIDPILOT_VISION_KEY.
3. None: the tool says so, and the agent uses observe(image=true) instead.
"""

from __future__ import annotations

import base64
import json
import urllib.request

from . import config
from .errors import DeviceError

SYSTEM = (
    "You look at one Android phone screenshot and answer one question. "
    "Answer in at most two short sentences. Give coordinates as (x, y) in the image's pixel space when asked where something is. "
    "If the answer is not visible, say 'not visible'."
)
MAX_TOKENS = 200


def endpoint_config() -> tuple[str, str, str] | None:
    url = config.VISION_URL
    if not url:
        return None
    if not url.startswith(("http://127.0.0.1", "http://localhost", "https://")):
        raise DeviceError("DROIDPILOT_VISION_URL must be https, or http on localhost")
    return url, config.VISION_MODEL, config.VISION_KEY


def build_request(model: str, question: str, jpeg: bytes) -> dict:
    """OpenAI chat-completions body with one image. Pure."""
    b64 = base64.b64encode(jpeg).decode()
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]},
        ],
    }


def parse_response(body: dict) -> str:
    try:
        return str(body["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise DeviceError(f"vision endpoint returned an unexpected body: {str(body)[:200]}") from exc


def ask_endpoint(question: str, jpeg: bytes, timeout: float = 60) -> str:
    cfg = endpoint_config()
    if cfg is None:
        raise DeviceError("no vision endpoint configured")
    url, model, key = cfg
    req = urllib.request.Request(url, data=json.dumps(build_request(model, question, jpeg)).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return parse_response(json.loads(resp.read().decode()))
    except OSError as exc:
        raise DeviceError(f"vision endpoint failed: {exc}") from exc


async def ask_host(session, question: str, jpeg: bytes) -> str | None:
    """Ask the agent's own client for a small model through MCP sampling.
    Return the answer, or None if the client has no sampling. Raise DeviceError if sampling failed."""
    import mcp.types as mt  # local: keeps the pure helpers above importable without the MCP SDK

    if not session.check_client_capability(mt.ClientCapabilities(sampling=mt.SamplingCapability())):
        return None
    try:
        res = await session.create_message(
            [
                mt.SamplingMessage(role="user", content=mt.ImageContent(type="image", data=base64.b64encode(jpeg).decode(), mimeType="image/jpeg")),
                mt.SamplingMessage(role="user", content=mt.TextContent(type="text", text=question)),
            ],
            max_tokens=MAX_TOKENS,
            system_prompt=SYSTEM,
            model_preferences=mt.ModelPreferences(
                hints=[mt.ModelHint(name="haiku"), mt.ModelHint(name="flash"), mt.ModelHint(name="mini")],
                speedPriority=0.9, costPriority=0.8, intelligencePriority=0.3,
            ),
        )
    except Exception as exc:
        raise DeviceError(f"sampling failed: {exc}") from exc
    text = (getattr(res.content, "text", "") or "").strip()
    if not text:
        raise DeviceError("sampling returned no text")
    return f"{text} [via host sampling, model={res.model}]"
