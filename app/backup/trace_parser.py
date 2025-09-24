# app/trace_parser.py
import zipfile, json, os

def parse_trace_to_json(trace_zip: str):
    steps = []
    with zipfile.ZipFile(trace_zip, "r") as zip_ref:
        zip_ref.extractall("./tmp_trace")
        trace_path = os.path.join("./tmp_trace", "trace.trace")
        with open(trace_path, "r", encoding="utf-8") as f:
            trace_data = json.load(f)

    for event in trace_data["actions"]:   # trace has actions/events
        action_type = event["type"]
        step = {"action": action_type}

        if action_type == "navigate":
            step["url"] = event.get("url")
        if action_type == "click":
            step["selector"] = event.get("selector")
        if action_type == "fill":
            step["selector"] = event.get("selector")
            step["value"] = "<testdata>"   # strip runtime data

        steps.append(step)

    return steps
