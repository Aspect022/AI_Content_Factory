"""Safe Milestone 1 command-line entry point."""

from __future__ import annotations

import json
import sys

from app.config import load_config
from app.exceptions import ConfigurationError
from app.logging.logger import configure_structured_logging


def main() -> int:
    """Validate cloud configuration without exposing or using any secret values."""

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
