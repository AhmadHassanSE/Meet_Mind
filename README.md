# MeetMind

The active fresh implementation is in [`meetmind/`](meetmind/README.md): React/TypeScript UI, FastAPI backend, persistent local storage and local Ollama inference.

The root-level UI and Python files are the earlier reference prototype, retained for context. Use the setup instructions inside `meetmind/`, not the root npm scripts, to run the new application.

The latest application includes ingestion, a fine-tuned BERT pilot and spaCy-assisted local commitment extraction. Trained weights and datasets are supplied separately; confidence calibration and held-out extraction evaluation remain pending.

GitHub Actions runs backend tests, the frontend build and browser smoke checks. Successful push/manual runs produce a downloadable release bundle; see [CI/CD setup](docs/ci-cd.md).

See [CONTRIBUTING.md](CONTRIBUTING.md) for the team workflow and [development evidence](docs/development-evidence.md) for actual completed checks and limitations.
