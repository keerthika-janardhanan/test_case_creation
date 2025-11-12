# llm_client.py
import os
import json

# Optional import: defer hard dependency to runtime to avoid import-time 500s
try:  # pragma: no cover - guarded import
    from langchain_openai import AzureChatOpenAI  # type: ignore
except ImportError:  # pragma: no cover
    AzureChatOpenAI = None  # type: ignore

CACHE_FILE = "./locator_cache.json"

# -------------------- Locator Cache --------------------
def load_locator_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_locator_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

# def update_locator_cache(old_locator, new_locator):
#     cache = load_locator_cache()
#     cache[old_locator] = new_locator
#     save_locator_cache(cache)

# -------------------- LLM Client --------------------
_llm_instance = None

def _ensure_llm():
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance
    if AzureChatOpenAI is None:
        raise RuntimeError("langchain-openai not installed; LLM features are unavailable")
    missing = [
        var for var in [
            "OPENAI_API_VERSION",
            "AZURE_OPENAI_DEPLOYMENT",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_KEY",
        ]
        if not os.getenv(var)
    ]
    if missing:
        raise RuntimeError(f"Missing Azure OpenAI env vars: {', '.join(missing)}")
    _llm_instance = AzureChatOpenAI(
        openai_api_version=os.getenv("OPENAI_API_VERSION"),
        azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "GPT-4o"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_KEY"),
        temperature=0.2,
    )
    return _llm_instance

# -------------------- Generate Script --------------------
def ask_llm_for_script(structure, existing_script, test_case, enriched_steps, ui_crawl, framework_prompt):
    prompt = f"""
{framework_prompt}

Rules:
- Follow the exact structure of the existing script (imports, hooks, naming, utils).
- Use enriched steps and test cases to create flows.
- If selectors are invalid, self-heal using the UI crawl data.
- Output only valid code.
 - Prefer Playwright getByRole/getByLabel/getByText when locator metadata is provided.
 - If a step provides a union XPath candidate, use it only as a fallback when getBy* is not viable.
 - Do not invent selectors; use provided 'locators' if present in steps. If missing, attempt minimal inference from UI crawl.

Existing structure:
{structure or "N/A"}

Existing Script:
{existing_script or "N/A"}

Test Case:
{test_case or "N/A"}

Enriched Steps (each may include a 'locators' object with 'playwright', 'xpath', 'css', etc.):
{enriched_steps or "N/A"}

UI Crawl Data:
{ui_crawl or "N/A"}
"""
    llm = _ensure_llm()
    resp = llm.invoke(prompt)
    return resp.content.strip() if hasattr(resp, "content") else str(resp)
# -------------------- Self-Healing --------------------
def ask_llm_to_self_heal(failed_script, logs, ui_crawl):
    prompt = f"""
You are debugging a Playwright TypeScript script.

Failing Script:
{failed_script}

Execution Logs:
{logs}

UI Crawl Data:
{ui_crawl or "N/A"}

Task:
- Identify failing locators from logs.
- Replace them using UI crawl or cached mappings.
- If not found, infer correct locators using semantic queries.
- Update the locator cache with old→new mappings.
- Return the full corrected TypeScript script only.
    """
    llm = _ensure_llm()
    resp = llm.invoke(prompt)
    return resp.content.strip() if hasattr(resp, "content") else str(resp)
