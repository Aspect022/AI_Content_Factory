# AI Shorts Factory

AI Shorts Factory is a cloud-first Python project for reliably publishing one
Hindi health-and-body-explainer YouTube Short each day. It is being built in
the milestones defined by the Engineering Specification.

## Current state: Text topic/script generation complete

This repository currently implements the foundation only:

- environment-only, secret-safe configuration validation;
- typed error and run-log models;
- JSON stdout logs plus durable per-run JSON files;
- SQLite migrations and parameterized repositories for runs, artifacts,
  provider health, and analytics;
- provider-neutral text, video, upload, and notification contracts;
- priority routing, automatic provider fallback, transient retry support, and
  dependency-free JSON-schema validation;
- versioned Hindi topic/script prompts, strict output contracts, and routed text
  generation through the specified provider order;
- mock-only unit tests and validation-only GitHub Actions workflows.

The text layer contains tested HTTP adapters for Groq Qwen3-32B, NVIDIA NIM
DeepSeek-R1, and Gemini 2.5 Flash. They are constructed from environment-only
configuration and are invoked only through `ProviderRouter`. No video, upload,
notification, browser automation, or deployment integration exists yet.

The text-generation milestone is verified with `ruff`, `black --check`,
`pytest`, and an enforced 90% coverage gate. The validation workflows run the
same quality checks on Python 3.11.

## Required environment variables

Copy `.env.example` to your secret manager or GitHub repository secrets. The
application deliberately does not read `.env` files; every runtime value must
come from environment variables.

```powershell
python -m pip install -r requirements.txt
python -m pytest
python -m ruff check .
python -m black --check .
```

To validate configuration without exposing any secret value:

```powershell
python -m app.main
```

## Storage

- `data/database.sqlite` contains the queryable run state and is never
  committed.
- `data/runs/` contains durable JSON run artifacts. Future daily workflows
  will commit these artifacts to Git after a successful run.
- `data/videos/` and `data/captions/` are local/generated artifacts and are
  not committed.

## Provider policy

The Engineering Specification controls provider ordering:

1. Text: Groq Qwen3-32B, then NVIDIA NIM DeepSeek-R1, then Gemini 2.5 Flash.
2. Video: Veo 3.1 Fast, then Wan 2.7, Seedance 2.5, then Veo 3.1 Lite.

See [the architecture notes](docs/architecture.md) and
[recorded specification decisions](docs/decisions.md).

## Core framework boundaries

The orchestrator will interact only with `ProviderRouter` and the `TextProvider`,
`VideoProvider`, `UploadProvider`, and `NotificationProvider` contracts. The
router checks health in priority order and falls forward only after an eligible
provider is unavailable or has exhausted permitted quota. `RetryManager` retries
only transient failures; permanent validation, authentication, quota, and policy
failures are not retried.

## Text generation

`app.content.factory.build_content_generator` composes the only permitted daily
text sequence: Groq Qwen3-32B, then NVIDIA NIM DeepSeek-R1, then Gemini 2.5
Flash. `ContentGenerator` loads the versioned templates in `app/prompts/`,
generates one topic or script through the router, and validates the strict JSON
contract before returning typed results. Invalid provider output is retried once
and then eligible for provider fallback.
