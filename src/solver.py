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
1. Exact Computation & Vectorized Pandas:
   - Write clean, vectorized pandas/numpy code. Keep it direct and concise (under 35 lines) without long commentary or duplicate helper functions.
   - Do not hardcode or hallucinate answers. Return ONLY the computed final value.
2. Structure, Hierarchy & Substring Matching:
   - Composite headers and hierarchical row categories are joined by ' | ' (e.g. 'Main Category | Subcategory').
   - When matching column names or row categories, ALWAYS lowercase both sides: `if pattern.lower() in text.lower():` or use `re.search(pattern, text, re.IGNORECASE)`.
   - Substring Collisions: Remember that 'men' is inside 'women', and 'male' is inside 'female'. Always match 'women'/'female' before 'men'/'male', or use word boundaries (r'\\bmen\\b', r'\\bmale\\b').
   - Distinguish data rows from aggregate/summary rows ('Total', 'All', 'Average', 'Subtotal'):
     * When finding min/max, ranking, or comparing individual categories, exclude summary/Total rows.
     * When asked for the overall total/sum across all categories or age groups, check if an aggregate/summary row already exists in the table to retrieve it directly and avoid double-counting.
     * When searching for category rows (e.g. an age group) to answer an overall question across the population, capture the FIRST occurrence in the table (e.g. `df[mask].iloc[0]` or check `if target is None: target = ...`), because overall totals appear before demographic breakdowns (Men, Women, Race).
3. Safe Numeric Conversion & Cleaning:
   - Report values in the table's native units as displayed (do not multiply or scale numbers unless the query explicitly asks for a specific scaled unit).
   - Safely convert series/cells to numeric: remove footnotes in brackets/parentheses (`re.sub(r'\\(.*?\\)|\\[.*?\\]', '', str(val))`) and strip non-numeric symbols (`re.sub(r'[^\\d.-]', '', s)`). NEVER make parentheses optional (e.g. do NOT use `\\(?\\d+\\)?` as that strips data digits).
   - For scalar strings: use `re.sub(r'\\(.*?\\)|\\[.*?\\]', '', str(val))` and `re.sub(r'[^\\d.-]', '', s)`. (Note: built-in `str.replace` does NOT take `regex=True`, use `re.sub`).
   - In pandas: `pd.to_numeric(s.astype(str).str.replace(r'\\(.*?\\)|\\[.*?\\]', '', regex=True).str.replace(r'[^\\d.-]', '', regex=True), errors='coerce')`.
4. Row/Column Aggregation:
   - When asked for average or total across categories that span columns for a row, select the data columns (`row.iloc[1:]`), convert to numeric, and take `.mean()` or `.sum()`.
5. Candidate Ranking & List Formatting:
   - When ranking or listing specific candidate names explicitly provided in the question (e.g. 'Agriculture, Manufacturing, and Construction'), return the exact candidate strings from the question in the resulting comma-separated string, not the longer or modified table header strings.
6. Temporal & Age Reasoning:
   - When identifying oldest/youngest entities or calculating age, if both a Birth Date and an Event/Record/Admission Date exist in the table, determine age as elapsed duration from birth date to that event date (`event_date - birth_date`). Parse all dates using `pd.to_datetime(...)`.
7. Strict Query Compliance:
   - If the question asks for Yes/No, return 'Yes' or 'No'.
   - If the question asks for integer(s), return int or comma-separated integers as requested.
   - If rounded to N decimal places, return round(val, N).
8. Execution Safety:
   - Enclose the code in ```python ... ``` blocks.
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
        "max_tokens": 1000,
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
