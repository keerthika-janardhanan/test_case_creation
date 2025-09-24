from app.recorder import FlowRecorder

def test_sanitize_events_redacts_sensitive_fields():
    recorder = FlowRecorder()
    events = [
        {"type": "fill", "selector": "#password", "value": "mypassword"},
        {"type": "fill", "selector": "#username", "value": "admin"},
    ]
    sanitized = recorder._sanitize_events(events)

    assert sanitized[0]["value"] == "***REDACTED***"
    assert sanitized[1]["value"] == "admin"  # non-sensitive untouched
