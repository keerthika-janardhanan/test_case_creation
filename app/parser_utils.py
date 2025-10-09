# parser_utils.py
import re
import json

def extract_structure(script_content: str):
    """Extract test suite structure (imports, describe blocks, hooks)."""
    structure = {
        "imports": re.findall(r"^import .*;", script_content, re.MULTILINE),
        "describe": re.findall(r'describe\((.*?)\)', script_content),
        "hooks": {
            "beforeAll": "beforeAll(async () => {});",
            "afterAll": "afterAll(async () => {});"
        }
    }
    return structure

def merge_recorder_flow(structure, recorder_json: str):
    """Merge recorder flow steps into script structure."""
    flow = json.loads(recorder_json)
    steps = []
    for step in flow.get("steps", []):
        steps.append(f'await page.{step["action"]}("{step["selector"]}");')
    return steps

def apply_ui_crawl_locators(steps, ui_crawl_json: str):
    """Self-heal locators using UI crawl data."""
    crawl = json.loads(ui_crawl_json)
    healed_steps = []
    for step in steps:
        for element in crawl.get("elements", []):
            if element["old_locator"] in step:
                step = step.replace(element["old_locator"], element["new_locator"])
        healed_steps.append(step)
    return healed_steps

def insert_test_variations(steps, test_case_json: str):
    """Expand recorder steps with happy/negative/edge cases."""
    cases = json.loads(test_case_json)
    enriched = []
    for case in cases.get("scenarios", []):
        enriched.append(f'// {case["type"].upper()} CASE: {case["description"]}')
        for step in steps:
            enriched.append(step)
    return enriched
