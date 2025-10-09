# framework_adapter.py
FRAMEWORK_RULES = {
    "playwright": "You are an expert Playwright TypeScript test automation engineer.",
    "selenium-java": "You are an expert Selenium Java automation engineer. Use JUnit/TestNG style.",
    "cypress": "You are an expert Cypress JavaScript automation engineer."
}


def get_framework_prompt(framework: str) -> str:
    return FRAMEWORK_RULES.get(framework, FRAMEWORK_RULES["playwright"])


def split_into_framework_files(script: str, framework: str):
    """
    Dummy splitter — in reality you'd use regex or AST parsing.
    Returns dict of {filename: code}
    """
    files = {}
    if framework == "playwright":
        files["specs/test.spec.ts"] = script
        # you could also extract 'pages' and 'utils' blocks if your LLM outputs them
    elif framework == "selenium-java":
        files["tests/TestClass.java"] = script
    elif framework == "cypress":
        files["cypress/e2e/test.cy.js"] = script
    else:
        files["script.txt"] = script
    return files
