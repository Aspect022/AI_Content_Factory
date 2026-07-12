# AI Shorts Factory

AI Shorts Factory is a cloud-first Python project for reliably publishing one
Hindi health-and-body-explainer YouTube Short each day. It is being built in
the milestones defined by the Engineering Specification.

## Current state: Version 1 automated pipeline complete

This repository implements the production Version 1 pipeline:

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
- configuration-driven single-clip video generation with Google Flow and
  OpenRouter video profiles;
- official YouTube Data API upload with resumable MP4 transfer and confirmed
  video URLs;
- Telegram success and failure notifications;
- scheduled and manual GitHub Actions publishing, durable JSON run artifacts,
  and failed-MP4 artifact preservation;
- mock-backed provider tests and a complete pipeline integration test.

The text layer contains tested HTTP adapters for Groq Llama 3.1 8B Instant, NVIDIA NIM
DeepSeek-R1, and Gemini 2.5 Flash. They are constructed from environment-only
configuration and are invoked only through `ProviderRouter`. The orchestrator
depends only on provider-neutral text, video, upload, and notification contracts.

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

## One-time YouTube authorization

Create a Desktop OAuth client in Google Cloud, enable the YouTube Data API and
YouTube Analytics API, and download its client JSON outside this repository.
Then run the local, interactive bootstrap command:

```powershell
python -m app.main youtube-auth --client-secrets-file C:\secure\client_secret.json --token-output-file C:\secure\youtube-token.json
```

The browser opens for consent. The command writes the refresh token to the
chosen secret file without printing it. Copy its `refresh_token` value to the
`YOUTUBE_REFRESH_TOKEN` GitHub secret, then securely delete the local token
file when no longer needed.

## Automated runtime

`daily.yml` runs daily at 08:00 Asia/Kolkata and also supports manual dispatch.
It validates the project and runtime configuration, then runs
`python -m app.main run`. Successful runs commit their durable JSON artifacts
using GitHub Actions' built-in `GITHUB_TOKEN`; no personal access token is used.
The workflow preserves logs for every run and uploads the temporary MP4 only when
publishing fails. Successful uploads use the official YouTube Data API client,
include `#shorts`, and delete the local MP4 only after YouTube confirms a video
ID. Telegram messages include status, selected provider, generation time, and URL.

## Storage

- `data/database.sqlite` contains the queryable run state and is never
  committed.
- `data/runs/` contains durable JSON run artifacts. Successful daily workflows
  commit these artifacts using the built-in Actions token.
- `data/videos/` and `data/captions/` are local/generated artifacts and are
  not committed.

## Provider policy

The Engineering Specification controls provider ordering:

1. Text: Groq Llama 3.1 8B Instant, then NVIDIA NIM DeepSeek-R1, then Gemini
   2.5 Flash.
2. Video profiles: Google Flow Quality, OpenRouter Video, then Google Flow
   Fast/Lite, configured entirely through `VIDEO_PROVIDER_PROFILES_JSON`.

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
text sequence: Groq Llama 3.1 8B Instant, then NVIDIA NIM DeepSeek-R1, then Gemini 2.5
Flash. `ContentGenerator` loads the versioned templates in `app/prompts/`,
generates one topic or script through the router, and validates the strict JSON
contract before returning typed results. Invalid provider output is retried once
and then eligible for provider fallback.

## Version 1 video generation

Version 1 generates one high-quality portrait (`9:16`) clip per day. Its default
duration is `8` seconds and may only be configured to Veo-supported 4, 6, or
8-second lengths through `VIDEO_DURATION_SECONDS`. `VeoVideoProvider` creates,
polls, and downloads a single Veo 3.1 Fast operation through the Gemini API.
The duration-aware request contract allows Version 2 to add longer native
providers or multi-clip composition without changing an orchestrator caller.

## Video profiles and credentials

`VIDEO_PROVIDER_PROFILES_JSON` defines provider order, provider type, model, and
the environment variable that supplies each profile's key. This allows multiple
Google Flow profiles without embedding credentials or model names in the
orchestrator. Configure separate `GEMINI_API_KEY` and `GEMINI_FALLBACK_API_KEY`
values for the main and fallback Flow profiles, plus separate
`OPENROUTER_API_KEY` and `OPENROUTER_FALLBACK_API_KEY` values. OpenRouter is
registered only by the video factory and is never part of text generation.

## Remaining manual setup

The only manual authorization step is YouTube OAuth. Run the `youtube-auth`
command above once, then store the downloaded OAuth client JSON and generated
refresh token as `YOUTUBE_CLIENT_SECRET_JSON` and `YOUTUBE_REFRESH_TOKEN`
GitHub secrets. GitHub repository access uses the built-in Actions token.
