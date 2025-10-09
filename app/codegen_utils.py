# codegen_utils.py

from typing import Dict, List

def generate_final_script(test_name, structure):
    if isinstance(structure, str):
        structure = {
            "imports": ["import { test, expect } from '@playwright/test';"],
            "steps": structure.splitlines()
        }

    imports = "\n".join(structure.get("imports", ["import { test, expect } from '@playwright/test';"]))
    steps = "\n".join([f"    // {s}" for s in structure.get("steps", [])])

    script = f"""
{imports}

test('{test_name}', async ({{
    page
}}) => {{
{steps}
}});
"""
    return script
