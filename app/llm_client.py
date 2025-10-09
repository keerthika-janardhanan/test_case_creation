# llm_client.py
import os
import json
from langchain_openai import AzureChatOpenAI

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

def update_locator_cache(old_locator, new_locator):
    cache = load_locator_cache()
    cache[old_locator] = new_locator
    save_locator_cache(cache)

# -------------------- LLM Client --------------------
llm = AzureChatOpenAI(
    openai_api_version=os.getenv("OPENAI_API_VERSION"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "GPT-4o"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    temperature=0.2,
)

# -------------------- Generate Script --------------------
def ask_llm_for_script(structure, existing_script, test_case, enriched_steps, ui_crawl, framework_prompt):
    prompt = f"""
{framework_prompt}

Rules:
- Follow the exact structure of the existing script (imports, hooks, naming, utils).
- Use enriched steps and test cases to create flows.
- If selectors are invalid, self-heal using the UI crawl data.
- Output only valid code.

Existing structure:
{structure or "N/A"}

Existing Script:
{existing_script or "N/A"}

Test Case:
{test_case or "N/A"}

Enriched Steps:
{enriched_steps or "N/A"}

UI Crawl Data:
{ui_crawl or "N/A"}
"""
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
    resp = llm.invoke(prompt)
    return resp.content.strip() if hasattr(resp, "content") else str(resp)
