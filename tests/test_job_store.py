from app import job_store


def setup_module(module):
    job_store.init_job_store()


def test_create_and_fetch_job(tmp_path):
    job_id = job_store.create_job("unit.test", {"foo": "bar"})
    job = job_store.get_job(job_id)
    assert job
    assert job["type"] == "unit.test"
    assert job["status"] == "queued"
    assert job["payload"]["foo"] == "bar"


def test_update_job_status():
    job_id = job_store.create_job("unit.test.update")
    job_store.update_job(job_id, "running")
    job_store.update_job(job_id, "completed", result={"ok": True})
    job = job_store.get_job(job_id)
    assert job
    assert job["status"] == "completed"
    assert job["result"]["ok"] is True
