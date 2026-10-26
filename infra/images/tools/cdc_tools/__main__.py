import argparse
import sys


def main():
    parser = argparse.ArgumentParser(prog="cdc_tools")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("smoke", help="validate the sample records, publish them and read them back")
    args = parser.parse_args()

    if args.cmd == "smoke":
        from .smoke import run
        return run()
    return 2


if __name__ == "__main__":
    sys.exit(main())
