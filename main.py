"""Start the UniPlan HTML frontend and timetable planning pipeline."""

from __future__ import annotations

import argparse

from uniplan.server import serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run UniPlan locally")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument(
        "--allow-robots-disallowed", action="store_true",
        help="Only if you have permission to query the source despite its robots.txt rule",
    )
    args = parser.parse_args(argv)
    serve(args.port, allow_robots_disallowed=args.allow_robots_disallowed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
