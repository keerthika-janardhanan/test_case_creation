import pytest
from app.recorder import FlowRecorder

@pytest.mark.asyncio
async def test_flow_recorder_runs_on_demo_page():
    recorder = FlowRecorder()
    flow = await recorder.record_flow("demo_login", "https://example.com")

    assert "name" in flow
    assert "events" in flow
    assert isinstance(flow["events"], list)
