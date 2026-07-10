import argparse
import json

from .database import init_db
from .jobs import run_daily, run_discovery, run_evaluation, worker


def main() -> None:
    parser = argparse.ArgumentParser(description="Reddit long-term DD track-record service")
    parser.add_argument(
        "command", choices=["init-db", "discover", "daily", "evaluate", "worker"]
    )
    args = parser.parse_args()
    init_db()
    if args.command == "init-db":
        return
    if args.command == "worker":
        worker()
        return
    actions = {"discover": run_discovery, "daily": run_daily, "evaluate": run_evaluation}
    print(json.dumps(actions[args.command](), indent=2, default=str))


if __name__ == "__main__":
    main()

