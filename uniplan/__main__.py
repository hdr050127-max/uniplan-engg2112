import argparse

from .server import serve


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run UniPlan locally")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument(
        "--allow-robots-disallowed", action="store_true",
        help="Only if you have permission to query the source despite its robots.txt rule",
    )
    args = parser.parse_args()
    serve(args.port, allow_robots_disallowed=args.allow_robots_disallowed)
