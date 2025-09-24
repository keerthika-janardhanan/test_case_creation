import re

# Regex patterns to capture Playwright actions
ACTION_PATTERNS = {
    "goto": re.compile(r'page\.goto\(["\'](.*?)["\']\)'),
    "click": re.compile(r'page\.(getByRole|getByText|getByLabel|getByTitle|locator)\(.*?\)\.click\(\)'),
    "fill": re.compile(r'page\.(getByRole|getByLabel|getByTitle|locator)\(.*?\)\.fill\(["\'].*?["\']\)'),
    "select_option": re.compile(r'page\.(getByRole|getByLabel|locator)\(.*?\)\.selectOption\(["\'].*?["\']\)'),
}

def parse_playwright_code(code: str):
    """
    Parse pasted Playwright TypeScript code and return a list of steps.
    """
    steps = []
    for line in code.splitlines():
        line = line.strip()

        # Goto
        match = ACTION_PATTERNS["goto"].search(line)
        if match:
            steps.append({"action": "goto", "url": match.group(1)})
            continue

        # Fill
        match = ACTION_PATTERNS["fill"].search(line)
        if match:
            selector = line.split(".fill")[0]
            steps.append({"action": "fill", "selector": selector, "value": "<PLACEHOLDER>"})
            continue

        # Click
        match = ACTION_PATTERNS["click"].search(line)
        if match:
            selector = line.split(".click")[0]
            steps.append({"action": "click", "selector": selector})
            continue

        # Select option
        match = ACTION_PATTERNS["select_option"].search(line)
        if match:
            selector = line.split(".selectOption")[0]
            steps.append({"action": "select_option", "selector": selector, "value": "<PLACEHOLDER>"})
            continue

    return steps
