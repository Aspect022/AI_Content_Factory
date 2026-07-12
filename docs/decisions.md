# Specification Decisions

## Provider-order conflict

The supplied PRD v1 and PRD v2 place NVIDIA NIM before Groq for text generation.
The Engineering Specification, which declares itself the single source of
truth, specifies Groq Qwen3-32B first, then NVIDIA NIM DeepSeek-R1, then Gemini
2.5 Flash. The implementation will follow the Engineering Specification.

**TODO(specification):** Confirm whether the superseded PRD ordering should be
retained for any special workload. Until that is confirmed, do not change the
Engineering Specification's Groq-first daily policy.

## Milestone-versus-workflow ordering

The initial engineering prompt includes CI in Milestone 1, while the detailed
specification lists GitHub Actions after persistence in its implementation order.
Milestone 1 therefore includes validation-only workflows. They run tests and
formatting checks, but do not call providers, upload videos, or send messages.
Those actions will only be enabled after their implementation milestones and
tests are complete.

## Milestone 1 verification

Milestone 1 has passed its configured local `ruff`, `black --check`, and
`pytest` quality gates. The current workflows remain validation-only until the
provider, upload, and notification milestones introduce their tested runtime
behaviors.

## Milestone 2 provider boundary

The core framework defines provider protocols and a priority router without any
vendor SDKs, HTTP calls, browser automation, or credentials. Future providers
must implement the relevant contract and be invoked through `ProviderRouter`;
the orchestrator must not call a vendor integration directly. The router uses
the Engineering Specification's configured order when concrete providers are
registered in a later milestone.

## Milestone 2 retry and persistence policy

`RetryManager` retries only errors explicitly marked transient (plus transport
timeouts and connection errors) and uses configurable exponential backoff. The
initial immutable migration already declares `runs`, `artifacts`, `analytics`,
and `provider_health`; Milestone 2 adds typed, parameterized repositories rather
than changing the schema.

## Text-generation provider order and failure policy

The text composition root registers exactly the Engineering Specification order:
Groq Qwen3-32B, NVIDIA NIM DeepSeek-R1, then Gemini 2.5 Flash. The content
service calls only `ProviderRouter`, never a concrete adapter. A transport,
server, or malformed-output failure is retried once for that provider; after the
retry budget is exhausted, the router may select the next provider. Authentication
and confirmed quota failures are not retried.

## Text output contract

Topic and script prompts are versioned files under `app/prompts/`. Their JSON
responses are validated at the service boundary before typed `Topic` or `Script`
objects are returned. This makes a malformed provider response a structured,
recoverable provider failure while preserving the original provider boundary.

## Version 1 video duration

Version 1 generates one 8-second clip rather than assembling multiple clips.
`VIDEO_DURATION_SECONDS` accepts only 4, 6, or 8 and defaults to 8. The generic
video request retains a duration field so Version 2 can add a longer native
provider or an internal composition strategy without requiring orchestrator
changes.

## Configuration-driven video routing

The daily orchestrator never imports or selects a concrete video provider. Video
profiles are read from `VIDEO_PROVIDER_PROFILES_JSON` in priority order and may
contain multiple Google Flow profiles plus OpenRouter. The initial environment
configuration places a quality Flow profile first, OpenRouter video second, and
a Flow Fast/Lite profile last. OpenRouter is confined to `OpenRouterVideoProvider`
and is not registered by the text-generation composition root.

Each profile references a key environment variable by name. Separate main and
fallback keys are required for Gemini and OpenRouter so revocation or quota loss
can be handled through a profile change rather than code edits.

## GitHub Actions authentication

The runtime does not read `GITHUB_TOKEN` as application configuration. The
daily workflow uses GitHub Actions' automatically provided token through
checkout credentials to commit successful JSON run artifacts. Its permissions
are limited to `contents: write`; no personal access token is required.
