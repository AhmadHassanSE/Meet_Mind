# MeetMind

The active fresh implementation is in [`meetmind/`](meetmind/README.md): React/TypeScript UI, FastAPI backend, persistent local storage and local Ollama inference.

The root-level UI and Python files are the earlier reference prototype, retained for context. Use the setup instructions inside `meetmind/`, not the root npm scripts, to run the new application.

The application now covers the following:
- **Iteration 1:** multilingual ingestion and Google Meet capture; a fine-tuned BERT-base dialogue-act classifier (held-out test macro F1 0.527, see `meetmind/backend/reports/bert-base-test-v1`); spaCy-grounded commitment extraction with deadline and priority resolution; human review.
- **Iteration 2:** accounts and roles; a LangGraph meeting workflow with human pauses; a policy rules engine; email and Jira drafting; owner approval; execution at most once through Gmail and Jira.

Trained weights and datasets are supplied separately. The team's own annotation and the end-to-end extraction scores are still to be produced; the tools are in `meetmind/backend/evaluation`. The design overview is in [docs/design/DESIGN.md](docs/design/DESIGN.md) and the demo script in [docs/DEMO.md](docs/DEMO.md).

GitHub Actions runs backend tests, the frontend build and browser smoke checks. Successful push/manual runs produce a downloadable release bundle; see [CI/CD setup](docs/ci-cd.md).

See [CONTRIBUTING.md](CONTRIBUTING.md) for the team workflow and [development evidence](docs/development-evidence.md) for actual completed checks and limitations.
