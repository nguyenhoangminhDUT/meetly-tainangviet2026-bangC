"""Program-Aided Reasoning (PoT) Solver with Qwen / LLM via OpenRouter and Groq."""

import os
import re
import sys
import math
import datetime
import itertools
import collections
import unicodedata
import traceback
from typing import Any, Dict, List, Optional, Tuple, Union
import requests
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = os.getenv("MODEL_ID", "qwen/qwen3.7-flash")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = os.getenv("GROQ_MODEL_ID", "llama-3.3-70b-versatile")

TOKEN_STATS = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "call_count": 0,
    "last_prompt_tokens": 0,
    "last_completion_tokens": 0,
    "last_total_tokens": 0,
}


def build_system_prompt() -> str:
    return r"""You are an expert Python data scientist specializing in spreadsheet analysis and Pandas.
Your task is to write a single Python function `def solve(dfs: dict[str, pd.DataFrame]) -> Any:` that precisely answers the user's question using the provided DataFrames.

CORE PRINCIPLES:
1. Multilingual Understanding & Strict Output Compliance:
   - The user query may be in English, Vietnamese, French, Korean, Chinese, or other languages.
   - Answer strictly according to the format asked in the query:
     * If asking for an integer without commas or units -> return int or comma-separated ints as requested.
     * If asking for 1, 2, or 3 decimal places -> return round(val, 1), round(val, 2), or round(val, 3) (or formatted float string).
     * If asking for Yes/No (or in other languages: Có/Không, Oui/Non, 是/否, 예/아니오) -> return 'Yes' or 'No'.
     * If asking for only the year / fiscal year -> return the 4-digit year as int or string (e.g. 1954, 2013).
     * If asking for a ranking or ordered list -> return comma-separated names in the exact order requested.
     * If asking for a composite output e.g. `group, difference` or `year, decrease` or `table_id, revenue` -> return tuple or string `f"{item1}, {item2}"`.

2. Hierarchical Structure, Indent Levels & Substring Matching:
   - Composite column headers and hierarchical row categories are joined by ' | ' (e.g. 'Main | Subcategory').
   - Column 0 vs Column 1: If Column 0 is 'Indent Level' (numeric integers 0, 1, 2...), the item/category names are in Column 1 ('Item and group').
     * Indent 0 = top-level, Indent 1 = category, Indent 2 = subcategory.
     * To find categories directly under a parent category (e.g. directly under 'Housing' with indent 1), look for rows that appear after 'Housing' with indent == parent_indent + 1, stopping before the next item with indent <= parent_indent.
   - Section headers in Column 0: When tables have demographic/activity sections (e.g. 'Own household children 6-17, none younger | Housework'), match using `str.contains(...)` with `case=False, na=False` or check `pattern.lower() in str(val).lower()`.
   - Substring Collisions: Remember 'men' is inside 'women', and 'male' is inside 'female'. Always match 'women'/'female' before 'men'/'male', or use word boundaries (r'\\bmen\\b', r'\\bmale\\b').

3. Safe Numeric Conversion & Cleaning:
   - Values in the table may be strings containing commas (e.g. '58,176'), currency ('$851'), percent ('10%'), negatives in parentheses '(1.5)' -> -1.5, or missing markers '..' / '-'.
   - Clean safely in pandas:
     `pd.to_numeric(s.astype(str).str.replace(r'[\$,%]', '', regex=True).str.replace(r'^\((.*?)\)$', r'-\1', regex=True).str.replace(',', '', regex=False), errors='coerce')`
   - In native Python:
     `def to_num(val): s = re.sub(r'[\$,%]', '', str(val)).replace(',', '').strip(); return float('-' + s[1:-1]) if s.startswith('(') and s.endswith(')') else float(s)`
   - Native Units: Report values in the table's native units as displayed (do not multiply by 1000 unless explicitly requested).

4. Aggregate vs Category Rows:
   - When finding min/max, ranking, or calculating differences across categories/industries/groups, EXCLUDE summary/Total rows (e.g. 'Total', 'All', 'Average', 'Subtotal', 'All industries').
   - When asked for the overall total/sum across all groups or categories, if an aggregate row already exists (e.g. 'Total', 'Total, all activities', 'Total, 16 years and over'), retrieve it directly to avoid double-counting.

5. Temporal & Age Reasoning:
   - When identifying oldest/youngest entities or calculating age, if both a Birth Date and an Admission/Event Date exist, age is elapsed duration: `(pd.to_datetime(event_date) - pd.to_datetime(birth_date)).dt.days`.

6. Execution Safety & Code Style:
   - Write clean, vectorized, self-contained pandas/numpy code. Keep it concise (under 40 lines).
   - Enclose the code strictly in ```python ... ``` blocks.
   - Do NOT hardcode or hallucinate answers. Return ONLY the computed final value.
"""


def execute_code_safely(code: str, dfs: Dict[str, pd.DataFrame]) -> Tuple[Any, Optional[str]]:
    """Executes the generated solve(dfs) function in a sandboxed local scope."""
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
        "itertools": itertools,
        "collections": collections,
        "unicodedata": unicodedata,
        "Any": Any,
        "List": List,
        "Dict": Dict,
        "Tuple": Tuple,
        "Optional": Optional,
        "Union": Union,
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


def query_llm(
    prompt: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    temperature: float = 0.0,
) -> str:
    """Unified LLM caller supporting both OpenRouter (competition default) and Groq (development testing)."""
    groq_key = os.getenv("GROQ_API_KEY", "")
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")

    # Auto-detect or select provider
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
        target_model = model or os.getenv("MODEL_ID") or DEFAULT_GROQ_MODEL
        if not key:
            raise ValueError("GROQ_API_KEY is not set. Please export GROQ_API_KEY or set in .env")
    else:
        url = OPENROUTER_URL
        key = api_key or openrouter_key
        target_model = model or os.getenv("MODEL_ID") or DEFAULT_OPENROUTER_MODEL
        if not key:
            raise ValueError("OPENROUTER_API_KEY is not set. Please export OPENROUTER_API_KEY or set in .env")

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
                payload["model"] = os.getenv("GROQ_MODEL_ID") or DEFAULT_GROQ_MODEL
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
