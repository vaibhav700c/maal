"""Lost-job contract: restarts must surface as retryable, not 404-forever."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_unknown_job_reports_lost_not_404():
    res = client.get("/enrich/status/deadbeef1234")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "lost"
    assert body["ok"] is False
    assert "retry" in body["detail"].lower()


def test_done_job_restored_from_disk(monkeypatch, tmp_path):
    from backend import main as bm
    monkeypatch.setattr(bm, "_JOBS_DIR", tmp_path)
    (tmp_path / "feedface1234.json").write_text('{"status": "done"}')
    monkeypatch.setattr(bm, "_JOBS", {})
    res = client.get("/enrich/status/feedface1234")
    assert res.status_code == 200
    assert res.json()["status"] == "done"
