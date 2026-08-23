import os
import sys
import signal
import time
import logging
import schedule
from typing import Optional

from smg_bot.config import BotConfig, load_config, get_logs_dir
from smg_bot.client import SteamGiftsClient
from smg_bot.giveaway_logic import GiveawayManager, get_sleep_time, log
from smg_bot.notifier import Statistics, DiscordNotifier

# Global shutdown flag
shutdown_requested = False
active_giveaway_manager: Optional[GiveawayManager] = None


def signal_handler(sig, frame):
    global shutdown_requested, active_giveaway_manager
    logging.info("Received shutdown signal, initiating graceful shutdown...")
    shutdown_requested = True
    if active_giveaway_manager:
        active_giveaway_manager.shutdown_flag = True


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def setup_logging(config: BotConfig) -> None:
    """Configure console and file logging."""
    log_level = getattr(logging, config.log_level_str, logging.INFO)
    handlers = []

    if config.log_to_console:
        handlers.append(logging.StreamHandler(sys.stdout))

    if config.log_to_file:
        log_file_path = os.path.join(get_logs_dir(), "steamgifts_bot.log")
        handlers.append(logging.FileHandler(log_file_path, encoding="utf-8"))

    # Reset root logger handlers
    root_logger = logging.getLogger()
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=handlers
    )


def run_bot() -> None:
    """Main application lifecycle runner."""
    global active_giveaway_manager

    # 1. Load configuration
    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Config validation error: {e}")
        sys.exit(1)

    setup_logging(config)
    logging.info("--- SteamGifts Bot Starting ---")
    logging.info(f"Loaded config with gift_type: {config.gift_type}, min_points: {config.min_points}, max_entries: {config.max_entries_per_session}")

    # 2. Instantiate core components
    client = SteamGiftsClient(config)
    stats = Statistics(config)
    notifier = DiscordNotifier(config)
    giveaway_mgr = GiveawayManager(config, client)
    active_giveaway_manager = giveaway_mgr

    # Initial check on startup (FROZEN auth-failure exit on invalid cookie)
    try:
        giveaway_mgr.update_info()
    except RuntimeError as e:
        log(f"🚨 CRITICAL: {str(e)}", "red")
        notifier.send_cookie_expired_notification()
        sys.exit(1)

    # 3. Register schedules
    def schedule_daily_report():
        notifier.send_daily_stats(stats, giveaway_mgr.points)

    def schedule_win_check():
        giveaway_mgr.check_for_wins(notifier.send_win_notification)

    schedule.every().day.at(config.discord_notification_time).do(schedule_daily_report)
    schedule.every(45).minutes.do(schedule_win_check)

    # Run initial win check
    schedule_win_check()

    log("🚀 Bot starting main loop...", "green")
    consecutive_errors = 0

    while not shutdown_requested and not giveaway_mgr.shutdown_flag:
        try:
            schedule.run_pending()

            giveaway_mgr.update_info()

            if giveaway_mgr.sleep_if_not_enough_points():
                continue

            giveaway_mgr.get_game_content(stats_callback=stats.add_entry)

            log("⏳ Cycle finished. Pausing...", "grey")
            cycle_sleep = get_sleep_time(config.base_sleep_time)
            time.sleep(cycle_sleep)
            consecutive_errors = 0

        except RuntimeError as e:
            # FROZEN: on expired cookie/auth failure, bot MUST raise and exit.
            log(f"🚨 CRITICAL: {str(e)}", "red")
            notifier.send_cookie_expired_notification()
            break

        except Exception as e:
            consecutive_errors += 1
            log(f"ERROR: {str(e)}", "red")
            if consecutive_errors >= config.max_consecutive_errors:
                log("🚫 Too many errors. Long sleep (15m).", "red")
                time.sleep(900)
                consecutive_errors = 0

        time.sleep(5)

    log("🛑 Bot shutting down...", "green")


if __name__ == "__main__":
    try:
        run_bot()
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt received, exiting cleanly.")
    except SystemExit as e:
        if e.code != 0:
            logging.error(f"Bot exited with code {e.code}")
        else:
            logging.info("Bot exited cleanly.")
    except Exception as e:
        logging.critical(f"Unhandled CRITICAL exception at top level: {str(e)}", exc_info=True)
    finally:
        logging.info("--- SteamGifts Bot Stopped ---")
