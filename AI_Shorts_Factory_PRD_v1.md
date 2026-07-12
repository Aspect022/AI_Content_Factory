# AI Shorts Factory PRD (v1)

**Author:** Jayesh RL\
**Purpose:** Build a fully automated AI-powered YouTube Shorts pipeline
that publishes **one Hindi Short per day** with minimal human
intervention and near-zero ongoing cost.

------------------------------------------------------------------------

# 1. Goals

## Primary Goal

Publish **1 YouTube Short/day** automatically.

Target characteristics:

-   Language: **Hindi**
-   Length: **15--20 seconds**
-   Format: Vertical (9:16)
-   Upload: Automatic
-   Cost: Prefer free tiers or existing subscriptions.

------------------------------------------------------------------------

# 2. Design Principles

-   Modular provider architecture.
-   Official APIs preferred whenever available.
-   Fall back to another provider if generation fails or available quota
    is exhausted.
-   Every execution must be logged.
-   Entire workflow should run in the cloud (no laptop required).

------------------------------------------------------------------------

# 3. Recommended Models (Do Not Auto-Choose)

## Idea Generation

Priority:

1.  NVIDIA NIM --- **DeepSeek-R1**
2.  Groq --- **Qwen3 32B**
3.  Google Gemini API --- **Gemini 2.5 Flash**

Use temperature 0.9 and require: - one unique topic, - one hook, - one
15--20 second script, - one cinematic video prompt.

------------------------------------------------------------------------

## Video Generation Priority

### Provider 1

Google Flow

Model: **Veo 3.1 Fast**

Use only if Fast credits remain.

If unavailable:

### Provider 2

Qwen Studio

Model: **Wan 2.7 Text-to-Video**

Use browser automation only if no official API is available.

If unavailable:

### Provider 3

Dreamina

Model: **Seedance 2.5**

If unavailable:

### Provider 4

Google Flow

Model: **Veo 3.1 Lite**

This is the emergency fallback to preserve daily upload consistency.

------------------------------------------------------------------------

# 4. Daily Pipeline

08:00 IST

1.  Generate today's idea.
2.  Generate script.
3.  Generate video.
4.  Download MP4.
5.  Upload to YouTube.
6.  Store metadata.
7.  Commit log to GitHub.
8.  Send Telegram notification.

------------------------------------------------------------------------

# 5. Logging (Mandatory)

For every run create one JSON:

``` json
{
  "date":"",
  "provider":"",
  "model":"",
  "status":"",
  "youtube_url":"",
  "generation_seconds":0,
  "title":"",
  "topic":"",
  "error":null
}
```

Commit the JSON back into the repository automatically.

------------------------------------------------------------------------

# 6. Repository Structure

``` text
shorts-factory/

.github/workflows/

providers/
  veo.py
  qwen.py
  dreamina.py

youtube.py
idea.py
logger.py
notify.py

logs/
ideas/
config/
```

------------------------------------------------------------------------

# 7. Notifications

Preferred:

Telegram Bot API

Success message:

-   Provider
-   Model
-   YouTube URL
-   Generation time

Failure message:

-   Failed step
-   Error
-   Provider attempted

------------------------------------------------------------------------

# 8. Content Strategy

Language: Hindi

Content Pillars:

-   Sleep
-   Tea & Coffee
-   Sugar
-   Liver
-   Brain
-   Heart
-   Gut
-   Exercise
-   Daily Habits
-   Nutrition

Style:

-   Strong 2-second hook.
-   Visual storytelling.
-   Accurate health information.
-   Avoid unsupported medical claims.
-   Simple CTA at the end.

------------------------------------------------------------------------

# 9. Monthly (Version 2)

On the last day of each month:

-   Fetch YouTube Analytics.
-   Evaluate performance.
-   Use an LLM judge ensemble:
    -   Gemini 2.5 Flash
    -   DeepSeek-R1 (NVIDIA)
    -   Qwen3 32B (Groq)
-   Produce recommendations.
-   Generate next month's content backlog.

------------------------------------------------------------------------

# 10. Success Criteria

-   30 consecutive uploads.
-   100% execution logging.
-   Automatic Telegram notifications.
-   Fully cloud-hosted workflow.
-   No dependency on a personal laptop.

------------------------------------------------------------------------

# Notes

Provider quotas and pricing change over time. Keep provider
configuration isolated so models can be swapped without changing the
rest of the pipeline.
