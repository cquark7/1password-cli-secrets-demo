"""Generate synthetic demo credentials for a secure input pipe or a desktop import."""

import argparse
import json
from secrets import token_hex
from urllib.parse import quote

from app import FIELDS, STAGES


def demo_values(stage: str) -> dict[str, str]:
    password = quote(f"demo-{token_hex(16)}:@+", safe="")
    database = f"postgres://orders_{stage}:{password}@my-{stage}-host.us-east-2.rds.amazonaws.com:5432/data"
    return {
        "CONFIG_STAGE": stage,
        "DATABASE_DSN": database,
        "SENTRY_DSN": f"https://{token_hex(16)}@o100000.ingest.sentry.example/{4001 + STAGES.index(stage)}",
        "SLACK_BOT_TOKEN": f"xoxb-demo-{stage}-{token_hex(16)}",
        "GOOGLE_MAPS_API_KEY": f"demo-maps-{stage}-{token_hex(16)}",
    }


def vault_item(stage: str, values: dict[str, str]) -> dict:
    sections = {
        section: {"id": token_hex(13), "label": section}
        for section in dict.fromkeys(section for _, section, _ in FIELDS)
    }
    return {
        "title": f"enterprise-orders-{stage}",
        "category": "SECURE_NOTE",
        "sections": list(sections.values()),
        "fields": [
            {
                "id": token_hex(13),
                "label": field,
                "section": sections[section],
                "type": "STRING" if variable == "CONFIG_STAGE" else "CONCEALED",
                "value": values[variable],
            }
            for variable, section, field in FIELDS
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=STAGES)
    parser.add_argument("--format", required=True, choices=("item", "dotenv"))
    args = parser.parse_args()
    values = demo_values(args.stage)
    if args.format == "item":
        print(json.dumps(vault_item(args.stage, values)))
    else:
        for name, value in values.items():
            print(f"{name}={value}")


if __name__ == "__main__":
    main()
