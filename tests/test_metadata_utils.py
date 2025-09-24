# test_metadata_utils.py
import pytest
from app.metadata_utils import sanitize_events, canonicalize_for_hash, compute_sha256, prepare_artifact_and_metadata_for_ingest

def sample_events():
    return [
        {"type":"input","selector":"#email","value":"alice@example.com","time":123456},
        {"type":"click","selector":"button.submit","text":"Login","time":123457},
        {"type":"navigation","url":"https://example.com/dashboard","time":123458}
    ]

def test_sanitize_redacts_values():
    evs = sample_events()
    sanitized, masked = sanitize_events(evs)
    assert all("time" not in e for e in sanitized)
    assert sanitized[0]["value"] == "<REDACTED>"
    assert "#email" in masked or "input" in masked or "email" in masked

def test_canonical_and_hash_stable():
    evs = sample_events()
    artifact, metadata, doc_id = prepare_artifact_and_metadata_for_ingest(evs, flow_name="login", user="tester")
    # canonicalization should be deterministic
    s = canonicalize_for_hash(artifact)
    h1 = compute_sha256(s)
    h2 = compute_sha256(s)
    assert h1 == h2
    assert metadata["hash"] == h1

def test_doc_id_contains_flow_name():
    evs = sample_events()
    artifact, metadata, doc_id = prepare_artifact_and_metadata_for_ingest(evs, flow_name="login_flow", user="tester")
    assert "login_flow" in doc_id

if __name__ == "__main__":
    pytest.main(["-q"])
