# GitHub Actions: CI and release delivery

The `MeetMind CI and delivery` workflow runs on every branch push, pull request,
and manual dispatch. It checks the active `meetmind/` application. The earlier
root prototype is reference material and is not built.

- Backend: Python 3.13, uv 0.10.9, frozen dependency lock, full NLP dependencies,
  real spaCy availability check and pytest. The JUnit report is retained 14 days.
- Frontend: Node 22, npm ci, TypeScript/Vite production build, and actual Chrome
  upload/persistence/validation/mobile smoke checks against an isolated database.
- Delivery: after both jobs pass on a push or manual run, package the tracked
  application source and tested frontend build into a ZIP with commit provenance
  and SHA-256 checksums. PR runs do not produce a release bundle.

Open the repository's **Actions** tab, select a successful run, and download
`meetmind-release-<commit>` under **Artifacts**. The outer GitHub artifact contains
`meetmind.zip` and its checksum file. Release bundles are retained 30 days;
frontend build artifacts are retained 14 days. This is artifact delivery, not a
deployment or an automatically published GitHub Release.

No deployment credentials or secrets are needed. Meeting files, SQLite databases,
credentials, datasets and trained weights are excluded by a tracked-file allowlist.
The bundle requires Python/uv, Node (if rebuilding), FFmpeg, the trained BERT
checkpoint, and local Ollama/model setup described in `meetmind/README.md`.
The compiled frontend is included for serving with a suitable server/proxy;
the existing local Vite development setup also remains available.

CI does not download private BERT weights, train models, run Ollama, or call hosted
inference services. Backend tests use fixtures/mocks where inference would require
local weights/services; real spaCy tests run. Browser CI exercises ingestion,
not real Whisper/BERT/Ollama inference. Run the documented local model smoke
scripts separately before an evaluation/demo.

Actions are pinned to commit SHAs with read-only repository permissions.
Superseded runs on the same branch/PR are cancelled. A failed check prevents
release packaging. The workflow becomes available on any branch containing it;
merge it into the shared development/default branch so teammates inherit it.
Branch-protection settings are not changed by adding this workflow.

For a local package check, build the frontend, then from the repository root run:

```powershell
meetmind/backend/.venv-nlp/Scripts/python.exe scripts/build_release.py --output release/meetmind.zip
```

Generated release files are ignored by Git.
