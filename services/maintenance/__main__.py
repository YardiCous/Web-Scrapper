import argparse
import sys


def main():
    parser = argparse.ArgumentParser(prog="maintenance")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ttl-refresh", help="publish scrape requests for listings older than the TTL")
    lg = sub.add_parser("loadgen", help="publish N synthetic listings to listings.raw at a fixed rate")
    lg.add_argument("--count", type=int, default=1000)
    lg.add_argument("--rate", type=float, default=100, help="messages per second")
    lg.add_argument("--run-id", required=True, help="tag used in source_listing_id (LG-<run-id>-<seq>)")
    args = parser.parse_args()

    if args.cmd == "loadgen":
        from .loadgen import run
        return run(args.count, args.rate, args.run_id)
    from .ttl_refresh import run
    return run()


if __name__ == "__main__":
    sys.exit(main())
