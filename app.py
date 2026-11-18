"""Check the credentials an order service would use at startup, without connecting."""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request

STAGES = ("test", "dev", "staging", "prod")
FIELDS = (
    ("CONFIG_STAGE", "deployment", "stage"),
    ("DATABASE_DSN", "database", "dsn"),
    ("SENTRY_DSN", "observability", "sentry_dsn"),
    ("SLACK_BOT_TOKEN", "integrations", "slack_bot_token"),
    ("GOOGLE_MAPS_API_KEY", "integrations", "google_maps_api_key"),
)


class ConfigError(Exception):
    """An error safe to display. Messages name fields and never include values."""


def load_config(path: str | None) -> dict[str, str]:
    if path == "-":
        document = json.load(sys.stdin)
    elif path is not None:
        with Path(path).open(encoding="utf-8") as stream:
            document = json.load(stream)

    if path is not None and not isinstance(document, dict):
        raise ConfigError("Expected a JSON object for the configuration.")

    config = {}
    for variable, section, field in FIELDS:
        if path is None:
            value = os.environ.get(variable)
        else:
            group = document.get(section)
            value = group.get(field) if isinstance(group, dict) else None
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"Missing {variable}.")
        if value.lstrip().startswith(("op://", "{{")):
            raise ConfigError(f"Unresolved 1Password reference for {variable}.")
        config[variable] = value
    return config


def check_dsn(name: str, value: str) -> None:
    try:
        url = urlsplit(value)
        if name == "DATABASE_DSN":
            valid = (
                url.scheme in {"postgres", "postgresql"}
                and url.username
                and url.password
                and url.hostname
                and url.port
                and url.path.strip("/")
            )
        else:
            valid = (
                url.scheme == "https"
                and url.username
                and url.hostname
                and url.path.rstrip("/").rsplit("/", 1)[-1].isdigit()
            )
    except ValueError:
        valid = False
    if not valid:
        raise ConfigError(f"Invalid {name}. Check its format in 1Password.")


def prepare_requests(config: dict[str, str]) -> tuple[Request, Request]:
    for name in ("SLACK_BOT_TOKEN", "GOOGLE_MAPS_API_KEY"):
        if not config[name].isascii() or any(c.isspace() for c in config[name]):
            raise ConfigError(f"Invalid {name}. Check its format in 1Password.")

    slack = Request(
        "https://slack.com/api/auth.test",
        headers={"Authorization": f"Bearer {config['SLACK_BOT_TOKEN']}"},
        method="POST",
    )
    route = {
        "origin": {"address": "1600 Amphitheatre Parkway, Mountain View, CA"},
        "destination": {"address": "450 Serra Mall, Stanford, CA"},
        "travelMode": "DRIVE",
    }
    maps = Request(
        "https://routes.googleapis.com/directions/v2:computeRoutes",
        data=json.dumps(route).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": config["GOOGLE_MAPS_API_KEY"],
            "X-Goog-FieldMask": "routes.distanceMeters",
        },
        method="POST",
    )
    return slack, maps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument(
        "--config", metavar="PATH", help="Read JSON from PATH or - for stdin."
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        if config["CONFIG_STAGE"] != args.stage:
            raise ConfigError(
                "Selected stage does not match CONFIG_STAGE in 1Password."
            )
        check_dsn("DATABASE_DSN", config["DATABASE_DSN"])
        check_dsn("SENTRY_DSN", config["SENTRY_DSN"])
        prepare_requests(config)
    except ConfigError as error:
        print(error, file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print("Could not read the resolved configuration.", file=sys.stderr)
        return 1

    print(f"Stage: {args.stage.upper()}")
    print("PostgreSQL and Sentry DSNs: validated")
    print("Slack and Google Maps: credential headers prepared")
    print("No connections opened or credentials logged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
