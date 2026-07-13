"""Safe Milestone 1 command-line entry point."""

from __future__ import annotations

import json
import sys
from argparse import ArgumentParser
from pathlib import Path

from app.config import load_config
from app.exceptions import ConfigurationError
from app.logging.logger import configure_structured_logging
from app.runtime import build_daily_orchestrator
from app.youtube_auth import authorize_youtube


def main(arguments: list[str] | None = None) -> int:
    """Validate cloud configuration without exposing or using any secret values."""

    parser = ArgumentParser(description="AI Shorts Factory commands")
    subparsers = parser.add_subparsers(dest="command")
    auth_parser = subparsers.add_parser(
        "youtube-auth", help="Run one-time local YouTube OAuth consent."
    )
    auth_parser.add_argument("--client-secrets-file", required=True, type=Path)
    auth_parser.add_argument("--token-output-file", required=True, type=Path)
    run_parser = subparsers.add_parser("run", help="Run one scheduled daily pipeline.")
    run_parser.add_argument("--pillar")
    subparsers.add_parser(
        "test-groq", help="Run standalone test for Groq text provider."
    )
    subparsers.add_parser(
        "test-gemini", help="Run standalone test for Gemini text provider."
    )
    subparsers.add_parser(
        "test-nvidia", help="Run standalone test for NVIDIA NIM text provider."
    )
    parsed = parser.parse_args(arguments)

    if parsed.command in {"test-groq", "test-gemini", "test-nvidia"}:
        configure_structured_logging()
        try:
            configuration = load_config()
        except ConfigurationError as error:
            sys.stderr.write(
                json.dumps(
                    {"event": "configuration_failed", "error": error.error.to_dict()}
                )
                + "\n"
            )
            return 2

        from app.providers.base import TextGenerationRequest
        from app.providers.gemini_provider import GeminiTextProvider
        from app.providers.groq_provider import GroqTextProvider
        from app.providers.nvidia_provider import NvidiaNimTextProvider

        prompt_text = (
            "Reply with exactly one valid JSON object containing a "
            '"status" field with the value "OK".'
        )
        req = TextGenerationRequest(
            prompt=prompt_text,
            schema={"type": "object", "properties": {"status": {"type": "string"}}},
        )

        try:
            if parsed.command == "test-groq":
                provider = GroqTextProvider(configuration.groq_api_key)
            elif parsed.command == "test-nvidia":
                provider = NvidiaNimTextProvider(configuration.nvidia_api_key)
            else:
                provider = GeminiTextProvider(configuration.gemini_api_key)

            sys.stdout.write(
                f"Running standalone test for {provider.name} ({provider.model})...\n"
            )
            sys.stdout.flush()
            response = provider.generate_json(req)
            sys.stdout.write(f"SUCCESS: {provider.name} responded successfully!\n")
            sys.stdout.write(f"Response: {response.content}\n")
            sys.stdout.flush()
            return 0
        except Exception as error:
            err_type = type(error).__name__
            sys.stderr.write(
                f"ERROR: {parsed.command} failed with {err_type}: {error}\n"
            )
            sys.stderr.flush()
            return 1

    if parsed.command == "youtube-auth":
        try:
            output_path = authorize_youtube(
                parsed.client_secrets_file, parsed.token_output_file
            )
        except ConfigurationError as error:
            sys.stderr.write(
                json.dumps(
                    {"event": "youtube_auth_failed", "error": error.error.to_dict()}
                )
                + "\n"
            )
            return 2
        sys.stdout.write(
            json.dumps({"event": "youtube_auth_saved", "token_file": str(output_path)})
            + "\n"
        )
        return 0

    configure_structured_logging()
    try:
        configuration = load_config()
    except ConfigurationError as error:
        sys.stderr.write(
            json.dumps(
                {"event": "configuration_failed", "error": error.error.to_dict()}
            )
            + "\n"
        )
        return 2

    if parsed.command == "run":
        result = build_daily_orchestrator(configuration).run(parsed.pillar)
        return 0 if result.run_log.status.value == "uploaded" else 1

    sys.stdout.write(
        json.dumps(
            {
                "event": "configuration_valid",
                "configuration": configuration.redacted_summary(),
            }
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
