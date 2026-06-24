import argparse

from arma_watcher import config as cfg_mod, updater
from arma_watcher.watcher import ArmaWatcher


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="arma-watcher",
        description="Monitor the Arma Reforger server queue from a screenshot.",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="re-run the interactive first-time setup wizard",
    )
    parser.add_argument(
        "--monitor",
        type=int,
        default=None,
        metavar="N",
        help="monitor index to capture (overrides saved config)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        metavar="SECONDS",
        help="queue poll interval in seconds (overrides saved config)",
    )
    parser.add_argument(
        "--detect-interval",
        type=int,
        default=None,
        metavar="SECONDS",
        dest="detect_interval",
        help="interval in seconds between Arma/queue detection attempts (overrides saved config)",
    )
    parser.add_argument(
        "--discord-webhook",
        metavar="URL",
        default=None,
        dest="discord_webhook",
        help="Discord webhook URL (overrides saved config)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    updater.check_for_updates()

    saved = cfg_mod.run_setup(force=args.setup)

    # CLI args take precedence over saved config
    monitor = args.monitor if args.monitor is not None else saved.get("monitor")
    interval = args.interval if args.interval is not None else saved.get("interval", 20)
    detect_interval = args.detect_interval if args.detect_interval is not None else saved.get("detect_interval", 5)
    discord_url = args.discord_webhook if args.discord_webhook is not None else saved.get("discord_webhook")
    discord_user_id = saved.get("discord_user_id")
    model = saved.get("model", "qwen3.5:9b")

    watcher = ArmaWatcher(
        monitor_index=monitor,
        queue_interval=interval,
        detect_interval=detect_interval,
        discord_url=discord_url,
        discord_user_id=discord_user_id,
        model=model,
        inference_mode=saved.get("inference_mode", "local"),
        proxy_url=saved.get("proxy_url"),
        license_key=saved.get("license_key"),
    )
    watcher.run()
