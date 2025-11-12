import subprocess
from pathlib import Path

from app import job_store, tasks


def setup_module(module):
    job_store.init_job_store()


def test_enqueue_recorder_launch(tmp_path: Path, monkeypatch):
    recordings_dir = tmp_path / "recordings"
    monkeypatch.setenv("RECORDER_OUTPUT_DIR", str(recordings_dir))
    monkeypatch.setattr(tasks, "RECORDINGS_DIR", recordings_dir)
    events: list[tuple[str, dict]] = []

    class DummyEvents:
        def publish_from_thread(self, session_id: str, message: dict) -> None:
            events.append((session_id, message))

    monkeypatch.setattr(tasks, "recorder_events", DummyEvents())
    monkeypatch.setattr(
        tasks,
        "_run_recorder_subprocess",
        lambda cmd, session_dir, session_id=None, job_id=None: (0, "stdout", ""),
    )

    payload = {"url": "https://example.com", "options": {"headless": True}}
    job_id, session_id = tasks.enqueue_recorder_launch(payload)

    job = job_store.get_job(job_id)
    assert job
    assert job["status"] == "completed"
    assert job["result"]["sessionId"] == session_id
    assert job["result"]["status"] == "completed"
    assert any(msg[0] == session_id for msg in events)


def test_stop_recorder_session_handles_running_process(monkeypatch, tmp_path: Path):
    session_id = "demo-session"
    launch_job_id = job_store.create_job("recorder.launch", {"sessionId": session_id})

    class DummyEvents:
        def __init__(self):
            self.messages: list[dict] = []

        def publish_from_thread(self, _session_id: str, message: dict) -> None:
            self.messages.append(message)

    events = DummyEvents()
    monkeypatch.setattr(tasks, "recorder_events", events)

    class FakeProcess:
        def __init__(self):
            self._terminated = False
            self._killed = False

        def poll(self):
            return 0 if self._terminated else None

        def terminate(self):
            self._terminated = True

        def wait(self, timeout=None):
            if not self._terminated:
                raise subprocess.TimeoutExpired("fake", timeout)
            return 0

        def kill(self):
            self._killed = True
            self._terminated = True

    fake_process = FakeProcess()
    session_dir = tmp_path / "recordings" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    tasks._store_recorder_session(session_id, launch_job_id, session_dir, fake_process)
    try:
        stop_job_id = tasks.enqueue_recorder_stop(session_id)
    finally:
        tasks._release_recorder_session(session_id)

    stop_job = job_store.get_job(stop_job_id)
    assert stop_job
    assert stop_job["status"] == "completed"
    assert stop_job["result"]["status"] == "stopping"
    assert any(msg["type"] == "stop-completed" for msg in events.messages)


def test_ingest_jira_task(monkeypatch):
    monkeypatch.setattr(tasks, "ingest_jira", lambda jql: [1, 2])
    job_id = tasks.enqueue_ingest_jira("project=TEST")
    job = job_store.get_job(job_id)
    assert job["status"] == "completed"
    assert job["result"]["ingested"] == 2


def test_ingest_documents_task(tmp_path: Path, monkeypatch):
    files = []
    for name in ["doc1.txt", "doc2.txt"]:
      p = tmp_path / name
      p.write_text("sample")
      files.append(str(p))
    monkeypatch.setattr(tasks, "ingest_document", lambda path: None)
    job_id = tasks.enqueue_ingest_documents(files)
    job = job_store.get_job(job_id)
    assert job["status"] == "completed"
    assert job["result"]["ingested"] == len(files)


def test_vector_delete_tasks(monkeypatch):
    monkeypatch.setattr(tasks.VectorDBClient, "delete_document", lambda self, doc_id: None)
    monkeypatch.setattr(tasks.VectorDBClient, "delete_by_source", lambda self, source: None)
    job_id = tasks.enqueue_vector_delete_by_id("doc-1")
    job = job_store.get_job(job_id)
    assert job["status"] == "completed"
    job_id = tasks.enqueue_vector_delete_by_source("jira")
    job = job_store.get_job(job_id)
    assert job["status"] == "completed"
