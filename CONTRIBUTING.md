# Team contribution workflow

## Identity and ownership

Each member uses their own GitHub account and configures their own Git identity locally. Use an email verified on that GitHub account (or its GitHub noreply address) if attribution should appear on their profile. Never change authors to simulate another member's contribution, backdate commits, or create empty commits for evaluation evidence.

```powershell
git config --local user.name "Your real name"
git config --local user.email "Your verified GitHub email"
```

The repository owner must grant teammates collaborator access before they can push directly; otherwise use forks and pull requests. No collaborator invitations are sent by this change.

## Branches and reviews

Base current work on `mid1/ollama-foundation`. Create one branch per owned task, for example `feat/ami-annotations`, `feat/spacy-extraction`, or `feat/meeting-review`. Commit meaningful increments with messages explaining the change. Push your branch and open a pull request into the shared development branch. A teammate reviews behavior, tests and alignment with requirements before merging.

```powershell
git fetch origin
git switch -c feat/your-task origin/mid1/ollama-foundation
# Implement and verify your own changes.
git add path/to/changed/files
git commit -m "feat: describe the implemented behavior"
git push -u origin feat/your-task
```

Keep PR titles specific. State the requirement, change, validation and limitations. Preserve individual commits when contribution history matters. Use co-author trailers only for real joint work with the contributors' agreement.

## Iteration 1 responsibilities

- Rana: literature review, AMI annotation, NLP design.
- Sameer: BERT classifier, spaCy NER, confidence module and evaluation.
- Azfaar: architecture, database schema, API contracts and supporting application UI.

Actual contribution evidence comes from reviewed work, not these assigned labels. Record deviations honestly.

## Checks and evidence

For backend changes run `uv run pytest` from `meetmind/backend`. For frontend changes run `npm.cmd run build` from `meetmind/frontend`. Include relevant additional validation when changing model behavior. Keep a task record linking requirement, owner, PR/commit and observed result. Tag genuine demonstration milestones when verified.

Do not commit credentials, local databases, virtual environments, node_modules, recordings or AMI datasets. Commit reproducible configs, lockfiles and dataset provenance/split metadata when appropriate and permitted. Disclose AI assistance and external components; each owner must understand and defend their code.
