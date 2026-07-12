# AI Shorts Factory PRD v2

This document is the implementation specification for an automated AI
YouTube Shorts pipeline. It is intended to be consumed by an AI coding
agent (e.g. Codex). Unless explicitly stated, use official APIs where
available. Browser automation should only be used when an official API
is unavailable and permitted by the service.

# Objectives

-   Publish exactly one Hindi YouTube Short per day.
-   Target duration: 15--20 seconds.
-   Aspect ratio: 9:16.
-   Cloud-first architecture (no dependency on a personal laptop).
-   Modular providers so video providers can be swapped without changing
    business logic.
-   Persist logs and metadata for every run.
-   Notify the owner after every run.

# Recommended Models

## Topic & Script Generation

Priority order: 1. NVIDIA NIM -- DeepSeek-R1 2. Groq -- Qwen3-32B 3.
Gemini 2.5 Flash

Generate: - Topic - Hook - Script - Video prompt - YouTube title -
Description - Hashtags

## Video Generation

Priority: 1. Google Flow -- Veo 3.1 Fast 2. Qwen Studio -- Wan 2.7
Text-to-Video (if available through the chosen interface) 3. Dreamina --
Seedance 2.5 4. Google Flow -- Veo 3.1 Lite

Use the next provider only if the previous one fails or no remaining
quota is available.

## Upload

Official YouTube Data API.

## Notifications

Telegram Bot API.

## Captions

If the chosen video model does not produce suitable captions, generate
subtitles with Whisper.

# Repository Structure

``` text
shorts-factory/
├── .github/workflows/
├── app/
│   ├── orchestrator.py
│   ├── scheduler.py
│   ├── config.py
│   ├── providers/
│   │   ├── base.py
│   │   ├── veo.py
│   │   ├── qwen.py
│   │   ├── dreamina.py
│   │   └── youtube.py
│   ├── prompts/
│   ├── logging/
│   ├── notifications/
│   └── analytics/
├── data/
│   ├── ideas/
│   ├── logs/
│   └── database.sqlite
└── docs/
```

# Execution Flow

1.  Scheduled GitHub Actions workflow starts.
2.  Generate today's idea.
3.  Generate script and metadata.
4.  Attempt video generation using provider priority.
5.  Upload video to YouTube.
6.  Store JSON log and SQLite record.
7.  Commit updated logs to GitHub.
8.  Send Telegram notification.

# Database Schema

Store: - date - provider - model - topic - title - script - prompt -
upload_status - youtube_url - generation_seconds - error_message -
created_at

# JSON Log Schema

``` json
{
  "date": "",
  "provider": "",
  "model": "",
  "topic": "",
  "title": "",
  "status": "",
  "youtube_url": "",
  "generation_seconds": 0,
  "error": null
}
```

# Retry Policy

-   Retry transient API failures with exponential backoff.
-   Do not retry authentication failures.
-   If a provider reports no remaining quota, immediately try the next
    provider.
-   Abort only after all providers fail.

# Content Guidelines

-   Primary language: Hindi.
-   Health content should be educational and avoid unsupported medical
    claims.
-   Preferred content pillars:
    -   Sleep
    -   Nutrition
    -   Tea & Coffee
    -   Sugar
    -   Heart
    -   Brain
    -   Liver
    -   Gut
    -   Exercise
    -   Daily Habits

# Monthly Workflow (Future)

Run on the last day of each month: - Collect YouTube Analytics. -
Evaluate performance using: - Gemini 2.5 Flash - DeepSeek-R1 -
Qwen3-32B - Produce a markdown report. - Generate a refreshed content
backlog.

# Engineering Notes

-   Keep provider-specific code isolated.
-   Read API keys from environment variables.
-   Never hardcode secrets.
-   Prefer official APIs over browser automation.
-   Browser automation should respect provider terms and only be used
    where appropriate.

# Implementation Module 1

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 1.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.

# Implementation Module 2

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 2.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.

# Implementation Module 3

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 3.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.

# Implementation Module 4

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 4.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.

# Implementation Module 5

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 5.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.

# Implementation Module 6

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 6.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.

# Implementation Module 7

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 7.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.

# Implementation Module 8

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 8.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.

# Implementation Module 9

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 9.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.

# Implementation Module 10

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 10.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.

# Implementation Module 11

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 11.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.

# Implementation Module 12

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 12.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.

# Implementation Module 13

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 13.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.

# Implementation Module 14

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 14.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.

# Implementation Module 15

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 15.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.

# Implementation Module 16

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 16.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.

# Implementation Module 17

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 17.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.

# Implementation Module 18

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 18.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.

# Implementation Module 19

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 19.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.

# Implementation Module 20

Purpose: Describe responsibilities, interfaces, inputs, outputs, error
handling, logging expectations, and unit tests for module 20.

Every public function should: - Return structured results. - Raise typed
exceptions. - Emit logs. - Be independently testable.

Add integration tests for successful execution and failure scenarios.
