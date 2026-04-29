import argparse

from arma_watcher.watcher import ArmaWatcher


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="arma-watcher",
        description="Monitor the Arma Reforger server queue from a screenshot.",
    )
    parser.add_argument(
        "--monitor",
        type=int,
        default=None,
        metavar="N",
        help="monitor index to capture (default: auto-detect)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=20,
        metavar="SECONDS",
        help="queue poll interval in seconds (default: 20)",
    )
    parser.add_argument(
        "--detect-interval",
        type=int,
        default=5,
        metavar="SECONDS",
        dest="detect_interval",
        help="interval in seconds between Arma/queue detection attempts (default: 5)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    watcher = ArmaWatcher(
        monitor_index=args.monitor,
        queue_interval=args.interval,
        detect_interval=args.detect_interval,
    )
    watcher.run()
