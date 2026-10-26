import argparse
import sys


def main():
    parser = argparse.ArgumentParser(prog="cdc_tools")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("smoke", help="validate the sample records, publish them and check they arrive everywhere")
    sub.add_parser("consume", help="listings.raw -> idempotent upsert into Postgres (smoke-consumer)")
    sub.add_parser("ttl-refresh", help="publish scrape requests for listings older than the TTL")
    sub.add_parser("echo", help="placeholder HTTP service that logs and echoes requests")
    lg = sub.add_parser("loadgen", help="publish N synthetic listings to listings.raw at a fixed rate")
    lg.add_argument("--count", type=int, default=1000)
    lg.add_argument("--rate", type=float, default=100, help="messages per second")
    lg.add_argument("--run-id", required=True, help="tag used in source_listing_id (LG-<run-id>-<seq>)")
    args = parser.parse_args()

    if args.cmd == "loadgen":
        from .loadgen import run
        return run(args.count, args.rate, args.run_id)
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
