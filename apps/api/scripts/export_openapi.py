import json
from pathlib import Path

from app.main import create_app

OUTPUT = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "openapi.json"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    schema = create_app().openapi()
    OUTPUT.write_text(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
