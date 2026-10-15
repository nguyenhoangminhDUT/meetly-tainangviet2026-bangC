"""Program-Aided Reasoning (PoT) Solver with Qwen3.7 Flash via OpenRouter."""

import os
import re
import sys
import math
import datetime
import traceback
from typing import Any, Dict, Optional, Tuple
import requests
import pandas as pd
import numpy as np
from dotenv import load_dotenv

from typing import Any, List, Dict, Tuple, Optional, Union
import typing

load_dotenv()

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.getenv("MODEL_ID", "nvidia/nemotron-3-super-120b-a12b:free")


def build_system_prompt() -> str:
    return """You are an expert Python data scientist specializing in spreadsheet analysis and Pandas.
Your task is to write a single Python function `def solve(dfs: dict[str, pd.DataFrame]) -> Any:` that precisely answers the user's question using the provided DataFrames.

CORE PRINCIPLES:
1. Exact Computation: Write clean, vectorized pandas/numpy code. Do not hardcode or hallucinate answers. Return ONLY the computed final value.
2. Structure & Hierarchy:
   - Composite headers and hierarchical row categories are joined by ' | ' (e.g. 'Main Category | Subcategory').
   - Use robust matching: `df.iloc[:, 0].astype(str).str.lower().str.strip()` or regex/partial matching (`str.contains(..., case=False, na=False)`).
   - Distinguish data rows from aggregate/summary rows ('Total', 'All', 'Average', 'Subtotal'):
     * When finding min/max, ranking, or comparing individual categories, exclude summary/Total rows.
     * When asked for the overall total/sum across all categories or age groups, check if an aggregate/summary row already exists in the table to retrieve it directly and avoid double-counting.
3. Units & Data Fidelity:
   - Report values in the table's native units as displayed (do not multiply or scale numbers unless the query explicitly asks for a specific scaled unit).
   - Clean strings from footnote markers (e.g. '(1)', '2/'), non-numeric symbols ('$', '%', ','), and linebreaks '\\n' before numeric conversion.
4. Temporal Reasoning:
   - When calculating age, duration, or elapsed time from dates, parse with `pd.to_datetime(...)`. If an event, admission, or reference date is present in the table, calculate elapsed duration relative to that reference date.
5. Strict Query Compliance:
   - If the question asks for Yes/No, return 'Yes' or 'No'.
   - If the question asks for integer(s), return int or comma-separated integers as requested.
   - If rounded to N decimal places, return round(val, N).
   - If asked for an ordered list or ranking among specified candidates, return them as a comma-separated string matching the exact candidate names and order requested.
6. Execution Safety:
   - Enclose the code in ```python ... ``` blocks.
   - Keep the code concise and direct without verbose comments or explanations.
"""


def execute_code_safely(code: str, dfs: Dict[str, pd.DataFrame]) -> Tuple[Any, Optional[str]]:
    """Executes the generated solve(dfs) function in a sandboxed local scope."""
    # Robust code fence extraction
    match = re.search(r"```(?:python)?\s*(.*?)\s*```", code, flags=re.DOTALL)
    if match:
        clean_code = match.group(1)
    else:
        clean_code = re.sub(r"^```(?:python)?\s*", "", code.strip())
        clean_code = re.sub(r"\s*```$", "", clean_code.strip())

    local_vars: Dict[str, Any] = {}
    global_vars: Dict[str, Any] = {
        "pd": pd,
        "np": np,
        "dfs": dfs,
        "re": re,
        "math": math,
        "datetime": datetime,
        "Any": Any,
        "List": List,
        "Dict": Dict,
        "Tuple": Tuple,
        "Optional": Optional,
        "Union": Union,
        "typing": typing,
    }

    try:
        exec(clean_code, global_vars, local_vars)
        if "solve" not in local_vars:
            return None, "Function 'solve' not defined in generated code"
        result = local_vars["solve"](dfs)
        return result, None
    except Exception as e:
        err_msg = traceback.format_exc()
        return None, err_msg


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_DEFAULT_MODEL = "qwen/qwen3.8-27b"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.getenv("MODEL_ID", "qwen/qwen3.7-flash")


TOKEN_STATS = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "call_count": 0,
    "last_prompt_tokens": 0,
    "last_completion_tokens": 0,
    "last_total_tokens": 0,
}


def query_llm(
    prompt: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    temperature: float = 0.0,
) -> str:
    """Unified LLM caller supporting both OpenRouter (competition default) and Groq (free development)."""
    groq_key = os.getenv("GROQ_API_KEY", "")
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")

    # Auto-detect or select provider (Competition default: OpenRouter)
    if provider == "groq":
        target_provider = "groq"
    elif provider == "openrouter":
        target_provider = "openrouter"
    elif openrouter_key:
        target_provider = "openrouter"
    elif groq_key:
        target_provider = "groq"
    else:
        target_provider = "openrouter"

    if target_provider == "groq":
        url = GROQ_URL
        key = api_key or groq_key
        target_model = model or os.getenv("MODEL_ID") or GROQ_DEFAULT_MODEL
        if not key:
            raise ValueError("GROQ_API_KEY is not set.")
    else:
        url = OPENROUTER_URL
        key = api_key or openrouter_key
        target_model = model or os.getenv("MODEL_ID") or DEFAULT_MODEL
        if not key:
            raise ValueError("OPENROUTER_API_KEY is not set.")

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": target_model,
        "temperature": temperature,
        "max_tokens": 450,
        "messages": [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": prompt},
        ],
    }

    for attempt in range(6):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            if resp.status_code in (402, 403) and target_provider == "openrouter" and groq_key and provider is None:
                print(f"[Notice] OpenRouter key limit reached. Falling back to Groq for testing...")
                target_provider = "groq"
                url = GROQ_URL
                headers["Authorization"] = f"Bearer {groq_key}"
                payload["model"] = os.getenv("GROQ_MODEL_ID") or GROQ_DEFAULT_MODEL
                continue

            if resp.status_code == 429:
                import time
                reset_val = resp.headers.get("x-ratelimit-reset-tokens")
                if reset_val and reset_val.endswith("s"):
                    try:
                        wait_time = float(reset_val[:-1]) + 2.0
                    except ValueError:
                        wait_time = 10.0
                else:
                    wait_time = 6.0 * (attempt + 1)
                print(f"[{target_provider.upper()} RateLimit] 429 received, waiting {wait_time:.1f}s until token reset...")
                time.sleep(wait_time)
                continue
            resp.raise_for_status()
            data = resp.json()
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
        except Exception as e:
            if attempt < 5:
                import time
                time.sleep(3 * (attempt + 1))
            else:
                raise


# Backward compatible alias
query_qwen = query_llm
