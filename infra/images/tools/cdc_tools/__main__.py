import argparse
import sys


def main():
    parser = argparse.ArgumentParser(prog="cdc_tools")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("smoke", help="validate the sample records, publish them and check they arrive everywhere")
    sub.add_parser("consume", help="listings.raw -> idempotent upsert into Postgres (smoke-consumer)")
    sub.add_parser("ttl-refresh", help="publish scrape requests for listings older than the TTL")
    sub.add_parser("echo", help="placeholder HTTP service that logs and echoes requests")
    args = parser.parse_args()

    if args.cmd == "smoke":
        from .smoke import run
    elif args.cmd == "consume":
        from .consume import run
    elif args.cmd == "ttl-refresh":
        from .ttl_refresh import run
    else:
        from .echo import run
    return run()


if __name__ == "__main__":
    sys.exit(main())
