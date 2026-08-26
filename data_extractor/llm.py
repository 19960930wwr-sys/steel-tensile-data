from __future__ import annotations

import time

from openai import OpenAI


QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
OPENAI_MODEL_PREFIXES = ("gpt-", "chatgpt-", "o1", "o3", "o4")


def resolve_llm_base_url(model_name: str, base_url: str | None = None) -> str | None:
    explicit_url = str(base_url or "").strip()
    if explicit_url:
        return explicit_url.rstrip("/")

    normalized_name = str(model_name or "").strip().lower()
    if normalized_name.startswith("qwen"):
        return QWEN_BASE_URL
    if normalized_name.startswith("deepseek"):
        return DEEPSEEK_BASE_URL
    if normalized_name.startswith(OPENAI_MODEL_PREFIXES):
        return None

    raise ValueError(
        f"Cannot infer an API provider from model_name={model_name!r}. "
        "Use a Qwen, DeepSeek, or OpenAI model name, or provide base_url."
    )


def llm_call_options(model_name: str) -> dict:
    normalized_name = str(model_name or "").strip().lower()
    if normalized_name.startswith("deepseek"):
        return {"extra_body": {"thinking": {"type": "disabled"}}}
    if normalized_name.startswith("qwen"):
        return {"extra_body": {"enable_thinking": False}}
    if normalized_name.startswith(OPENAI_MODEL_PREFIXES):
        return {"reasoning_effort": "minimal"}
    return {}


def llm_client(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    model_name: str = "qwen-plus",
    base_url: str | None = None,
) -> str:
    model_name = str(model_name or "").strip()
    if not model_name:
        raise ValueError("model_name must not be empty.")

    resolved_base_url = resolve_llm_base_url(model_name, base_url)
    client_options = {"api_key": api_key}
    if resolved_base_url:
        client_options["base_url"] = resolved_base_url
    client = OpenAI(**client_options)

    max_attempts = 3
    transient_keywords = ("connection", "timeout", "rate limit", "temporarily", "overloaded")
    last_error = None

    for attempt in range(max_attempts):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                **llm_call_options(model_name),
            )
            content = response.choices[0].message.content
            if content is None:
                raise RuntimeError(f"Model {model_name!r} returned an empty response.")
            return content
        except Exception as exc:
            last_error = exc
            is_transient = any(keyword in str(exc).lower() for keyword in transient_keywords)
            if not is_transient or attempt == max_attempts - 1:
                break
            time.sleep(2 ** attempt)

    raise RuntimeError(f"LLM request failed for model {model_name!r}: {last_error}") from last_error

