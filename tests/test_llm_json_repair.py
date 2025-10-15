import json
from app.test_case_generator import TestCaseGenerator


class DummyDB:
    def query(self, *_args, **_kwargs):
        return []


def test_repair_truncated_array():
    gen = TestCaseGenerator(db=DummyDB(), llm=None)
    broken = '[{"id":"TC001","title":"A"},{"id":"TC002","title":"B"}'
    repaired = gen._repair_llm_output_to_json_array(broken)
    assert isinstance(repaired, list)
    assert len(repaired) == 2
    assert repaired[0]["id"] == "TC001"


def test_repair_markdown_wrapped_single_object():
    gen = TestCaseGenerator(db=DummyDB(), llm=None)
    wrapped = """
    ```json
    {"id":"TC001","title":"Only One"}
    ```
    """
    # Simulate the sanitised stage; repair should wrap into a list
    output = wrapped.replace('```json', '').replace('```', '').strip()
    repaired = gen._repair_llm_output_to_json_array(output)
    assert isinstance(repaired, list)
    assert len(repaired) == 1
    assert repaired[0]["title"] == "Only One"


def test_repair_extract_objects_from_prose():
    gen = TestCaseGenerator(db=DummyDB(), llm=None)
    text = "Here are cases: {\"id\":\"TC1\"}{\"id\":\"TC2\"} end."
    repaired = gen._repair_llm_output_to_json_array(text)
    # Should salvage two objects as a list
    assert isinstance(repaired, list)
    assert {obj["id"] for obj in repaired} == {"TC1", "TC2"}
