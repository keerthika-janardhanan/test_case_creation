import pandas as pd
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent / "app"))

from test_case_generator import map_llm_to_template

template_data = {
    "sl": [1, "", "", "", ""],
    "Action": ["Log into Oracle", "Navigate", "Navigate", "Navigate", "Navigate"],
    "Navigation Steps": ["Login to Oracle Cloud Applications Homepage\nClick Login", "Click the Navigator link", "Click the Suppliers link under the Procurement category", "Click the Task Pane icon (Sheet of Paper)", "Click Create Supplier hyperlink in the Tasks region"],
    "Key Data Element Examples": ["Enter User Name\nEnter Password", "", "", "", ""],
    "Expected Results": ["Login Successful", "Navigator opened", "The Supplier work area screen launches", "The Task Pane is displayed", "The Create Supplier pop up window is visible"]
}

df = pd.DataFrame(template_data)

llm_output = [
    {
        "id": "TC001",
        "title": "Create Supplier Happy Path",
        "type": "positive",
        "preconditions": ["User has Oracle access"],
        "step_details": [
            {"action": "Log into Oracle", "navigation": "Go to Oracle Cloud", "data": "Username: demo", "expected": "Logged in"},
            {"action": "Navigate", "navigation": "Open Navigator > Suppliers", "data": "", "expected": "Suppliers page visible"},
        ],
        "expected": "Supplier created successfully",
        "data": {"SupplierName": "Test"},
        "tags": ["smoke"],
        "assumptions": []
    }
]

result = map_llm_to_template(llm_output, df)
print(result)
