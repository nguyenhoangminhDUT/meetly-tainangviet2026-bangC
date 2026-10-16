"""Program-Aided Reasoning (PoT) Solver Module.

Orchestrates:
1. System Prompt Synthesis: Guides LLM to produce vectorized Python/Pandas logic.
2. Official Competition LLM Execution: Primary route through `CompetitionLLMClient` (Qwen 3.7 Flash).
3. Optional Developer Test Providers: Groq, Gemini, Ollama adapters for zero-cost local research.
4. Sandboxed Code Execution: Executes `solve(dfs)` in an isolated scope with AST safety checking.
"""

import os
import re
import sys
import math
import datetime
import itertools
import collections
import unicodedata
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import requests
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from src.llm_client import (
        CompetitionLLMClient,
        COMPETITION_MODEL_ID,
        TOKEN_STATS,
        get_token_usage_report,
    )
except ImportError:
    from llm_client import (
        CompetitionLLMClient,
        COMPETITION_MODEL_ID,
        TOKEN_STATS,
        get_token_usage_report,
    )

# Optional Development Endpoints
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = os.getenv("GROQ_MODEL_ID", "llama-3.1-8b-instant")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL_ID", "gemini-1.5-flash")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/v1/chat/completions")
DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL_ID", "qwen2.5-coder:7b")

SELFHOSTED_URL = os.getenv("SELFHOSTED_URL", "https://llm2.dutai.site/v1/chat/completions")
DEFAULT_SELFHOSTED_MODEL = os.getenv("SELFHOSTED_MODEL_ID", "ggml-org/gemma-4-e4b-it-GGUF:Q4_0")


def build_system_prompt() -> str:
    """Constructs the high-precision system prompt for Program-Aided Reasoning."""
    return r"""You are an expert Python data scientist specializing in spreadsheet analysis and Pandas.
Your task is to write a single Python function `def solve(dfs: dict[str, pd.DataFrame]) -> Any:` that precisely answers the user's question using the provided DataFrames.

CORE PRINCIPLES:
0. Input Structure:
   - The argument `dfs` is a dictionary where KEYS ARE WORKSHEET NAMES (e.g. `df = dfs['Table A-6']` or `df = list(dfs.values())[0]`). Keys are NEVER file names or file paths.

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
   - Substring Collisions: Remember 'men' is inside 'women', and 'male' is inside 'female'. Always match 'women'/'female' before 'men'/'male', or use word boundaries (r'\bmen\b', r'\bmale\b').

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
   - Write clean, vectorized, self-contained pandas/numpy code. Keep it concise (under 25 lines).
   - Do NOT hardcode or hallucinate answers. Return ONLY the computed final value.

7. Ultra-Fast Generation & Zero Chit-Chat:
   - Output ONLY the Python code block enclosed in ```python ... ```.
   - STRICTLY NO conversation, NO introduction ('Here is the code...'), NO line-by-line comments, NO docstrings, and NO explanations after the code block.
   - Stop immediately after the final line of code.
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
    except Exception:
        err_msg = traceback.format_exc()
        return None, err_msg


def query_llm(
    prompt: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    temperature: float = 0.0,
) -> str:
    """Primary LLM caller.
    
    Defaults to the official competition model (Qwen 3.7 Flash via OpenRouter).
    Supports developer test adapters (Groq, Gemini, Ollama) when explicitly requested.
    """
    sys_prompt = build_system_prompt()

    # Determine provider: default to official competition OpenRouter
    target_provider = (provider or "openrouter").lower()

    if target_provider == "openrouter":
        client = CompetitionLLMClient(
            api_key=api_key,
            model_id=model or COMPETITION_MODEL_ID,
        )
        return client.query(prompt, system_prompt=sys_prompt, temperature=temperature)

    # Optional Testing Providers (Groq, Gemini, Ollama)
    headers = {"Content-Type": "application/json"}
    if target_provider == "groq":
        url = GROQ_URL
        key = api_key or os.getenv("GROQ_API_KEY", "")
        target_model = model or DEFAULT_GROQ_MODEL
        if not key:
            raise ValueError("GROQ_API_KEY is not set for groq provider.")
        headers["Authorization"] = f"Bearer {key}"
    elif target_provider == "gemini":
        url = GEMINI_URL
        key = api_key or os.getenv("GEMINI_API_KEY", "")
        target_model = model or DEFAULT_GEMINI_MODEL
        if not key:
            raise ValueError("GEMINI_API_KEY is not set for gemini provider.")
        headers["Authorization"] = f"Bearer {key}"
    elif target_provider == "ollama":
        url = OLLAMA_URL
        target_model = model or DEFAULT_OLLAMA_MODEL
    elif target_provider == "selfhosted":
        url = SELFHOSTED_URL
        target_model = model or DEFAULT_SELFHOSTED_MODEL
        key = api_key or os.getenv("SELFHOSTED_API_KEY", "")
        if key:
            headers["Authorization"] = f"Bearer {key}"
    else:
        raise ValueError(f"Unsupported provider: {target_provider}")

    payload = {
        "model": target_model,
        "temperature": temperature,
        "max_tokens": 1500,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt},
        ],
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    usage = data.get("usage", {})
    p_tok = usage.get("prompt_tokens", 0)
    c_tok = usage.get("completion_tokens", 0)
    TOKEN_STATS["prompt_tokens"] += p_tok
    TOKEN_STATS["completion_tokens"] += c_tok
    TOKEN_STATS["total_tokens"] += p_tok + c_tok
    TOKEN_STATS["call_count"] += 1

    return data["choices"][0]["message"]["content"]


# Backward-compatible alias
query_qwen = query_llm
