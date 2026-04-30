"""LLM provider wrappers for entity resolution: Claude / GPT / DeepSeek / Mock."""
from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from storytelling_bot.resolver.prompts import RESOLVE_SYSTEM, RESOLVE_USER_TEMPLATE

log = logging.getLogger(__name__)

ProviderFn = Callable[[str], str]


def claude_provider(model: str = "claude-sonnet-4-6") -> ProviderFn:
    try:
        from anthropic import Anthropic
    except ImportError:
        raise RuntimeError("pip install anthropic")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = Anthropic(api_key=api_key)

    def _call(user_prompt: str) -> str:
        resp = client.messages.create(
            model=model,
            max_tokens=2000,
            system=RESOLVE_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return resp.content[0].text
    return _call


def gpt_provider(model: str = "gpt-4o") -> ProviderFn:
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("pip install openai")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    client = OpenAI(api_key=api_key)

    def _call(user_prompt: str) -> str:
        resp = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": RESOLVE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
        )
        return resp.choices[0].message.content or ""
    return _call


def deepseek_provider(model: str = "deepseek-chat") -> ProviderFn:
    try:
        import requests
    except ImportError:
        raise RuntimeError("pip install requests")
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")

    def _call(user_prompt: str) -> str:
        r = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": RESOLVE_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    return _call


def mock_provider(provider_name: str, mock_dir: Path) -> ProviderFn:
    """Reads saved answer from llm_inputs/<provider>_*.{json,txt}"""
    def _call(user_prompt: str) -> str:
        candidates = sorted(mock_dir.glob(f"{provider_name}_*.json")) \
                     + sorted(mock_dir.glob(f"{provider_name}_*.txt"))
        if not candidates:
            raise FileNotFoundError(f"No mock file for {provider_name} in {mock_dir}")
        text = candidates[0].read_text(encoding="utf-8")
        if "RAW_ANSWER:" in text:
            text = text.split("RAW_ANSWER:", 1)[1].strip()
        return text
    return _call


def get_provider(name: str, mock_dir: Path | None = None) -> ProviderFn:
    """Factory: returns provider by name. Falls back to mock if mock_dir given."""
    if mock_dir:
        return mock_provider(name, mock_dir)
    if name == "claude":
        return claude_provider()
    if name == "gpt":
        return gpt_provider()
    if name == "deepseek":
        return deepseek_provider()
    raise ValueError(f"Unknown provider: {name}")


def build_user_prompt(query: str) -> str:
    return RESOLVE_USER_TEMPLATE.format(query=query)


def parse_provider_answer(provider: str, raw: str) -> dict[str, Any]:
    """Parse raw LLM answer → {entities: [...], uncertainty_note: ''}"""
    raw = raw.strip()
    json_match = re.search(r"\{[\s\S]+\}", raw)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            if "entities" in data:
                return data
            if "canonical_name" in data:
                return {"entities": [data], "uncertainty_note": ""}
        except Exception:
            pass
    return {"entities": [], "uncertainty_note": f"{provider}: failed to parse JSON"}
