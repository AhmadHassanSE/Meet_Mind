from fastapi.testclient import TestClient
from app import main


def test_ingestion_persistence_and_missing_record(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.db")
    client = TestClient(main.app)
    response = client.post("/api/meetings", json={"title": "Review", "transcript": "Sara: I will send the report Friday."})
    assert response.status_code == 201
    meeting = response.json()
    assert meeting["segments"][0]["speaker"] == "Sara"
    assert client.get(f'/api/meetings/{meeting["id"]}').json() == meeting
    assert client.get("/api/meetings/missing").status_code == 404


def test_blank_input_and_vtt():
    client = TestClient(main.app)
    assert client.post("/api/meetings", json={"title": " ", "transcript": " "}).status_code == 422
    segments = main.segments_from_text("WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\nSara: Send the report.")
    assert len(segments) == 1
    assert segments[0]["speaker"] == "Sara"
