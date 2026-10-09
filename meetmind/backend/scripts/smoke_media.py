"""Run the real decoder/transcriber via the API against supplied local fixtures.

Usage: uv run python -m scripts.smoke_media path/to/meeting.wav path/to/meeting.mp4
Uses an isolated temporary database; creates no records in the application DB.
The first run may download Whisper model weights. This is not an accuracy benchmark.
"""
import argparse
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient
from app import main


def run(paths, expect_failure=False):
    with tempfile.TemporaryDirectory(prefix="meetmind-smoke-") as directory:
        main.DB_PATH = Path(directory) / "test.db"
        with TestClient(main.app) as client:
            for filename in paths:
                path = Path(filename)
                with path.open("rb") as fixture:
                    response = client.post("/api/ingestion/media", data={"title": f"Smoke: {path.name}"},
                                           files={"file": (path.name, fixture)})
                response.raise_for_status()
                job_id = response.json()["id"]
                previous = None
                deadline = time.monotonic() + 900
                while time.monotonic() < deadline:
                    job = client.get(f"/api/ingestion/jobs/{job_id}").json()
                    if job["status"] != previous:
                        print(path.name, job["status"], job["message"], flush=True)
                        previous = job["status"]
                    if job["status"] == "failed":
                        if expect_failure:
                            assert client.get('/api/meetings').json() == []
                            break
                        raise RuntimeError(job["message"])
                    if job["status"] == "completed":
                        assert not expect_failure, "Expected silent/audio-free fixture to fail"
                        meeting = client.get(f"/api/meetings/{job['meeting_id']}").json()
                        assert meeting["segments"]
                        assert all(s["start"] is not None for s in meeting["segments"])
                        print("Transcript:", meeting["transcript"], flush=True)
                        for extension in ("txt", "json", "vtt"):
                            client.get(f"/api/meetings/{meeting['id']}/transcript?format={extension}").raise_for_status()
                        break
                    time.sleep(1)
                else:
                    raise TimeoutError("Transcription exceeded the smoke-check time limit")
    print("Media API smoke checks passed.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='+')
    parser.add_argument('--expect-failure', action='store_true', help='Use only silent or audio-free fixtures')
    args = parser.parse_args()
    run(args.paths, args.expect_failure)
