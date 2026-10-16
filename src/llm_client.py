"""Official Competition LLM Client Module for Meetly Spreadsheet QA.

This module implements the direct, compliant connection to the official competition model:
- Model: Qwen3.7 Flash (ID: `qwen/qwen3.7-flash`)
- Provider: OpenRouter (https://openrouter.ai/qwen/qwen3.7-flash)
- Specification: Tài Năng Việt 2026 - Bảng C (Chủ đề 2)

Complies with all competition constraints:
1. No hardcoded API keys: Loaded from OPENROUTER_API_KEY environment variable.
2. Resource Limits: Strict timeouts, token minimization, cost estimation (< $0.10 / query).
3. Resilient Communication: Automatic retry with exponential backoff on HTTP 429 & 5xx.
"""

import os
import sys
import time
from typing import Any, Dict, List, Optional
import requests
from dotenv import load_dotenv

load_dotenv()

# Official Competition Configuration
COMPETITION_MODEL_ID = "qwen/qwen3.7-flash"
OPENROUTER_ENDPOINT = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions")

# Pricing per million tokens (USD) for Qwen 3.7 Flash on OpenRouter
PRICE_PROMPT_PER_M = 0.03
PRICE_COMPLETION_PER_M = 0.13

# Global Telemetry & Token Tracking
TOKEN_STATS: Dict[str, Any] = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "call_count": 0,
    "last_prompt_tokens": 0,
    "last_completion_tokens": 0,
    "last_total_tokens": 0,
}


class CompetitionLLMClient:
    """Official LLM Client connecting to Qwen3.7 Flash via OpenRouter API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_id: str = COMPETITION_MODEL_ID,
        endpoint: str = OPENROUTER_ENDPOINT,
        timeout: int = 60,
        max_retries: int = 5,
    ):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model_id = model_id
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_retries = max_retries

    def query(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        """Sends a query to Qwen3.7 Flash on OpenRouter with automatic backoff retry."""
        if not self.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is not set.\n"
                "Please configure it before running:\n"
                "  Linux/macOS: export OPENROUTER_API_KEY=\"sk-or-v1-...\"\n"
                "  Windows PowerShell: $env:OPENROUTER_API_KEY=\"sk-or-v1-...\"\n"
                "  Or pass via CLI flag: --api_key \"sk-or-v1-...\""
            )

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/nguyenhoangminhDUT/meetly-tainangviet2026-bangC",
            "X-Title": "Meetly AI 2026 Table QA",
        }

        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_id,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(
                    self.endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )

                # Rate Limit Handling (HTTP 429)
                if resp.status_code == 429:
                    reset_header = resp.headers.get("x-ratelimit-reset-tokens")
                    wait_time = 4.0 * (attempt + 1)
                    if reset_header and reset_header.endswith("s"):
                        try:
                            wait_time = float(reset_header[:-1]) + 1.0
                        except ValueError:
                            pass
                    print(f"[*] OpenRouter Rate limit (429). Retrying in {wait_time:.1f}s (Attempt {attempt+1}/{self.max_retries})...")
                    time.sleep(wait_time)
                    continue

                # Temporary Server Error Handling (502, 503, 504)
                if resp.status_code in (502, 503, 504):
                    wait_time = 3.0 * (attempt + 1)
                    print(f"[*] Server error ({resp.status_code}). Retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    continue

                resp.raise_for_status()
                data = resp.json()

                # Telemetry & Token accounting
                usage = data.get("usage", {})
                p_tok = usage.get("prompt_tokens", 0)
                c_tok = usage.get("completion_tokens", 0)
                t_tok = usage.get("total_tokens", p_tok + c_tok)

                TOKEN_STATS["prompt_tokens"] += p_tok
                TOKEN_STATS["completion_tokens"] += c_tok
                TOKEN_STATS["total_tokens"] += t_tok
                TOKEN_STATS["call_count"] += 1
                TOKEN_STATS["last_prompt_tokens"] = p_tok
                TOKEN_STATS["last_completion_tokens"] = c_tok
                TOKEN_STATS["last_total_tokens"] = t_tok

                return data["choices"][0]["message"]["content"]

            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries:
                    wait_time = 2.5 * (attempt + 1)
                    print(f"[*] Connection notice ({e}). Retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                else:
                    raise RuntimeError(f"OpenRouter API request failed after {self.max_retries} retries: {e}") from e

        raise RuntimeError("OpenRouter API request failed: Exceeded maximum retry attempts.")


def call_competition_llm(
    prompt: str,
    system_prompt: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: float = 0.0,
    model_id: str = COMPETITION_MODEL_ID,
) -> str:
    """Convenience helper function to call the competition Qwen 3.7 Flash model."""
    client = CompetitionLLMClient(api_key=api_key, model_id=model_id)
    return client.query(prompt, system_prompt=system_prompt, temperature=temperature)


def get_token_usage_report(query_count: int = 1) -> Dict[str, Any]:
    """Generates an official token usage and cost report for the evaluation session."""
    p_tok = TOKEN_STATS["prompt_tokens"]
    c_tok = TOKEN_STATS["completion_tokens"]
    t_tok = TOKEN_STATS["total_tokens"]
    calls = TOKEN_STATS["call_count"]

    est_cost = (p_tok * PRICE_PROMPT_PER_M + c_tok * PRICE_COMPLETION_PER_M) / 1_000_000
    avg_tokens = t_tok / max(1, query_count)
    avg_cost = est_cost / max(1, query_count)

    return {
        "call_count": calls,
        "prompt_tokens": p_tok,
        "completion_tokens": c_tok,
        "total_tokens": t_tok,
        "avg_tokens_per_query": round(avg_tokens, 1),
        "estimated_cost_usd": est_cost,
        "avg_cost_per_query_usd": avg_cost,
    }
