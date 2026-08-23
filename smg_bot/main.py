import os
import sys
import signal
import time
import logging
import schedule
from typing import Optional

from smg_bot.config import BotConfig, load_config, get_logs_dir, get_config_path
from smg_bot.client import SteamGiftsClient
from smg_bot.giveaway_logic import GiveawayManager, get_sleep_time, interruptible_sleep, log
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

    root_logger = logging.getLogger()
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=handlers
    )


def wait_for_cookie_hot_reload(
    config: BotConfig,
    client: SteamGiftsClient,
    giveaway_mgr: GiveawayManager,
    notifier: DiscordNotifier
) -> BotConfig:
    """
    Standby IDLE loop when authentication fails (ENHANCEMENT 2: Zero-crash Hot-Reload).
    Watches config.ini for changes, reloads, and resumes automatically without container restart.
    """
    notifier.send_cookie_expired_notification()
    log("🚨 Authentication failed (cookie invalid/expired). Entering IDLE standby mode...", "red")
    log("💡 Paste the new PHPSESSID into config.ini - the bot will automatically hot-reload and resume!", "cyan")

    config_path = get_config_path()
    last_mtime = os.path.getmtime(config_path) if os.path.exists(config_path) else 0

    while not shutdown_requested:
        time.sleep(15)

        if not os.path.exists(config_path):
            continue

        try:
            current_mtime = os.path.getmtime(config_path)
            if current_mtime > last_mtime:
                log("🔍 Config file change detected! Checking updated configuration...", "cyan")
                new_config = load_config(config_path)

                # Test new credentials
                client.config = new_config
                client.cookie = new_config.cookie
                giveaway_mgr.config = new_config

                token, points = client.fetch_user_info()
                giveaway_mgr.xsrf_token = token
                giveaway_mgr.points = points

                log(f"✅ New cookie verified successfully! Current points: {points}. Resuming bot operations.", "green")
                notifier.config = new_config
                notifier.send_cookie_recovered_notification()
                return new_config

        except Exception as e:
            log(f"⏳ Cookie test failed ({e}). Remaining in IDLE standby mode...", "yellow")
            last_mtime = os.path.getmtime(config_path) if os.path.exists(config_path) else 0

    return config


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
    logging.info(f"Loaded config with gift_type: {config.gift_type}, min_points: {config.min_points}, stages: {', '.join(config.special_mode_stages)}")

    # 2. Instantiate core components
    client = SteamGiftsClient(config)
    stats = Statistics(config)
    notifier = DiscordNotifier(config)
    giveaway_mgr = GiveawayManager(config, client)
    active_giveaway_manager = giveaway_mgr

    # Initial check on startup
    try:
        giveaway_mgr.update_info()
    except RuntimeError:
        config = wait_for_cookie_hot_reload(config, client, giveaway_mgr, notifier)

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
    error_backoff_cycle = 0

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

            # Reset error counters on successful cycle
            consecutive_errors = 0
            error_backoff_cycle = 0

        except RuntimeError as e:
            # Authentication failure during runtime -> Enter Hot-Reload IDLE mode
            log(f"🚨 Auth exception: {str(e)}", "red")
            config = wait_for_cookie_hot_reload(config, client, giveaway_mgr, notifier)
            consecutive_errors = 0
            error_backoff_cycle = 0

        except Exception as e:
            consecutive_errors += 1
            log(f"ERROR: {str(e)}", "red")

            # ENHANCEMENT 3: Exponential backoff with jitter on consecutive errors
            if consecutive_errors >= config.max_consecutive_errors:
                error_backoff_cycle += 1
                # 300s (5m) -> 600s (10m) -> 1200s (20m) -> 2400s (40m) -> max 7200s (2h)
                backoff_base = min(7200.0, 300.0 * (2 ** min(error_backoff_cycle - 1, 4)))
                backoff_sleep = get_sleep_time(backoff_base)

                log(f"🚫 Too many consecutive errors ({consecutive_errors}). Backoff cooldown: {int(backoff_sleep/60)}m (Cycle {error_backoff_cycle}).", "red")
                interruptible_sleep(
                    backoff_sleep,
                    heartbeat_interval=300,
                    reason=f"error backoff cycle {error_backoff_cycle}",
                    shutdown_check=lambda: shutdown_requested
                )
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
