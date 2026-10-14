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
    return """You are an expert Python data scientist specializing in Excel/table analysis and Pandas.
Your task is to write a single Python function `def solve(dfs: dict[str, pd.DataFrame]) -> Any:` that answers the user's question about the provided Excel data.
The input `dfs` is a dictionary where keys are sheet names and values are pandas DataFrames with cleaned data.

Rules:
1. Return ONLY the final computed value (string, integer, float, etc.).
2. Do NOT hallucinate data; write precise pandas/numpy/python code to calculate the exact answer.
3. Be CONCISE. Do NOT write verbose comments or lengthy explanations. Keep code short and direct.
4. Handle missing values, clean strings (strip whitespace, newlines '\\n', remove footnotes like (1) or 2/ using regex e.g. `re.sub(r'\\(\\d+\\)', '', str(val)).strip()`).
5. Unit convention: Do NOT scale or multiply numbers by thousands. If table numbers are 265 under '[In thousands]', return 265 directly as the integer, do NOT multiply by 1000 unless explicitly requested.
6. In pandas, use `df.iloc[:, 0].astype(str).str.lower().str.strip()` or regex/partial matching (`str.contains(..., case=False, na=False)`) to locate row labels accurately, ignoring footnote markers like (1) or (2).
   Note that section headers are prepended to row labels with ' | ' (e.g. 'Women | Unemployment rate', 'Men | Civilian labor force').
7. Summary rows: When finding min, max, ranking, or calculating proportions among categories/industries/hours, EXCLUDE summary or 'Total' rows (e.g. 'Total, persons at work', 'Total', 'All industries').
8. Age calculation: In tables with both Date of Birth and Date of Admission, calculate person's age on admission date as (pd.to_datetime(Admission) - pd.to_datetime(Birth)).dt.days.
9. Multiple values format:
   - If asked for two integers (e.g. "order `1 to 34 hours, 35 hours or more`"), return a string formatted as f"{val1}, {val2}".
   - If asked for "men, women" averages with two decimal places, return f"{men:.2f}, {women:.2f}".
10. Candidate names: When candidate names are listed in the question (e.g. 'Agriculture, Manufacturing, and Construction'), return exactly those requested names in descending order, separated by a comma and one space.
11. Provide code enclosed in ```python ... ``` blocks.
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
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt < 5:
                import time
                time.sleep(3 * (attempt + 1))
            else:
                raise


# Backward compatible alias
query_qwen = query_llm
