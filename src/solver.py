"""Program-Aided Reasoning (PoT) Solver with Qwen3.7 Flash via OpenRouter."""

import os
import re
import sys
import traceback
from typing import Any, Dict, Optional, Tuple
import requests
import pandas as pd


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "qwen/qwen3.7-flash"


def build_system_prompt() -> str:
    return """You are an expert Python data scientist specializing in Excel/table analysis and Pandas.
Your task is to write a single Python function `def solve(dfs: dict[str, pd.DataFrame]) -> Any:` that answers the user's question about the provided Excel data.
The input `dfs` is a dictionary where keys are sheet names and values are pandas DataFrames with cleaned data.

Rules:
1. Return ONLY the final computed value (string, integer, float, etc.).
2. Do NOT hallucinate data; write precise pandas/numpy/python code to calculate the exact answer.
3. Handle missing values, clean strings (strip whitespace, remove footnotes like (1) or 2/ if needed).
4. Remove commas from number strings before converting to int/float if necessary.
5. Provide code enclosed in ```python ... ``` blocks.
"""


def execute_code_safely(code: str, dfs: Dict[str, pd.DataFrame]) -> Tuple[Any, Optional[str]]:
    """Executes the generated solve(dfs) function in a sandboxed local scope."""
    # Extract code from ```python ... ``` block if present
    match = re.search(r"```(?:python)?\s*(.*?)\s*```", code, flags=re.DOTALL)
    clean_code = match.group(1) if match else code

    local_vars: Dict[str, Any] = {}
    global_vars: Dict[str, Any] = {
        "pd": pd,
        "dfs": dfs,
        "re": re,
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


def query_qwen(
    prompt: str,
    api_key: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.0,
) -> str:
    """Sends a chat completion request to Qwen via OpenRouter."""
    key = api_key or os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        raise ValueError("OPENROUTER_API_KEY environment variable is not set.")

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": prompt},
        ],
    }

    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]
