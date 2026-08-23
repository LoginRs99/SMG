import os
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Set, Optional, Any
import requests
from smg_bot.config import BotConfig, get_logs_dir


class Statistics:
    """Tracks bot operational metrics for reporting."""

    def __init__(self, config: BotConfig):
        self.config = config
        self.start_time_utc = datetime.now(timezone.utc)
        self.total_entries = 0
        self.successful_entries = 0
        self.failed_entries = 0
        self.points_spent = 0
        self.daily_entries = 0
        self.daily_points = 0
        self.timezone = config.timezone
        self.timezone_str = config.timezone_str

    def reset_daily_stats(self) -> None:
        self.daily_entries = 0
        self.daily_points = 0

    def add_entry(self, success: bool, points: int) -> None:
        self.total_entries += 1
        if success:
            self.successful_entries += 1
            self.points_spent += points
            self.daily_entries += 1
            self.daily_points += points
        else:
            self.failed_entries += 1

    def get_stats(self) -> Dict[str, Any]:
        runtime_delta = datetime.now(timezone.utc) - self.start_time_utc
        hours = runtime_delta.total_seconds() / 3600

        return {
            "runtime": str(runtime_delta).split('.')[0],
            "total_entries": self.total_entries,
            "successful_entries": self.successful_entries,
            "failed_entries": self.failed_entries,
            "success_rate": f"{(self.successful_entries / self.total_entries * 100):.1f}%" if self.total_entries > 0 else "0%",
            "points_spent": self.points_spent,
            "entries_per_hour": f"{(self.total_entries / hours):.1f}" if hours > 0 else "0",
            "daily_entries": self.daily_entries,
            "daily_points": self.daily_points,
            "start_time_display": self.start_time_utc.astimezone(self.timezone).strftime('%Y-%m-%d %H:%M')
        }


class NotifiedWinsStore:
    """Persistent storage for announced wins to prevent duplicate Discord messages across restarts (APPROVED CHANGE 7)."""

    def __init__(self, store_file: Optional[str] = None):
        if store_file is None:
            store_file = os.path.join(get_logs_dir(), "notified_wins.json")
        self.store_file = store_file
        self.notified_wins: Set[str] = set()
        self.load()

    def load(self) -> None:
        if os.path.exists(self.store_file):
            try:
                with open(self.store_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.notified_wins = set(data)
                logging.info(f"Loaded {len(self.notified_wins)} previously notified wins from {self.store_file}")
            except Exception as e:
                logging.warning(f"Could not load notified wins store: {e}")
                self.notified_wins = set()

    def save(self) -> None:
        try:
            with open(self.store_file, "w", encoding="utf-8") as f:
                json.dump(sorted(list(self.notified_wins)), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Failed to save notified wins to {self.store_file}: {e}")

    def filter_unnotified(self, games: List[str]) -> List[str]:
        new_wins = []
        for g in games:
            if g not in self.notified_wins:
                new_wins.append(g)
        return new_wins

    def mark_notified(self, games: List[str]) -> None:
        for g in games:
            self.notified_wins.add(g)
        self.save()


class DiscordNotifier:
    """Handles Discord webhook notifications for stats, wins, and auth failures."""

    def __init__(self, config: BotConfig):
        self.config = config
        self.webhook_url = config.discord_webhook
        self.wins_store = NotifiedWinsStore()

    def send_win_notification(self, games: List[str]) -> None:
        """Send notification when a giveaway is won (APPROVED CHANGE 7: opt-in @here & persistent deduplication)."""
        unnotified = self.wins_store.filter_unnotified(games)
        if not unnotified:
            logging.info("👀 No new unredeemed wins to announce.")
            return

        logging.info(f"🎉 CONGRATULATIONS! You won {len(unnotified)} game(s): {', '.join(unnotified)}")
        self.wins_store.mark_notified(unnotified)

        if not self.webhook_url:
            return

        mention_prefix = "@here " if self.config.discord_mention_wins else ""
        payload = {
            "content": f"{mention_prefix}🎉 **YOU WON A GIVEAWAY!** 🎉",
            "embeds": [{
                "title": "🏆 New Games Won",
                "description": "\n".join([f"• {g}" for g in unnotified]),
                "color": 0xFFD700,
                "footer": {"text": "Check your SteamGifts account immediately!"}
            }]
        }
        try:
            requests.post(self.webhook_url, json=payload, timeout=10)
            logging.info("Sent win notification to Discord.")
        except Exception as e:
            logging.error(f"Failed to send win webhook: {e}")

    def send_cookie_expired_notification(self) -> None:
        """Send Discord alert when session cookie expires (APPROVED CHANGE 7)."""
        if not self.webhook_url:
            return

        mention_prefix = "@here " if self.config.discord_mention_alerts else ""
        payload = {
            "content": f"{mention_prefix}🚨 **SteamGifts Bot STOPPED** 🚨",
            "embeds": [{
                "title": "⛔ Cookie Expired / Invalid",
                "description": (
                    "The bot has shut down because the **PHPSESSID cookie** is no longer valid.\n\n"
                    "**What to do:**\n"
                    "1. Log in to [SteamGifts.com](https://www.steamgifts.com)\n"
                    "2. Copy your new `PHPSESSID` cookie\n"
                    "3. Update `config.ini` and restart the bot"
                ),
                "color": 0xFF0000,
                "footer": {"text": "Bot is offline until cookie is updated."},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }]
        }
        try:
            requests.post(self.webhook_url, json=payload, timeout=10)
            logging.info("Sent cookie expired Discord notification.")
        except Exception as e:
            logging.error(f"Failed to send cookie expired webhook: {e}")

    def send_daily_stats(self, stats: Statistics, giveaway_mgr_points: Any) -> None:
        """Send daily statistics summary on a background thread (APPROVED CHANGE 7)."""
        if not self.webhook_url:
            logging.debug("Discord webhook URL not configured, skipping stats report.")
            return

        def send_webhook():
            stats_data = stats.get_stats()
            current_local_time = datetime.now(stats.timezone)
            start_time_local = stats.start_time_utc.astimezone(stats.timezone).strftime('%Y-%m-%d %H:%M')

            runtime_delta = datetime.now(timezone.utc) - stats.start_time_utc
            days = runtime_delta.days
            hours = runtime_delta.seconds // 3600

            total_runtime_days = runtime_delta.total_seconds() / (24 * 3600)
            avg_daily_entries = stats.total_entries / total_runtime_days if total_runtime_days > 0 else 0
            avg_daily_points = stats.points_spent / total_runtime_days if total_runtime_days > 0 else 0

            config_info = (
                f"Gift type: **{self.config.gift_type}**\n"
                f"Min points threshold: **{self.config.min_points}**\n"
                f"Special Mode: **{'Cycling Active' if self.config.gift_type == 'Special Mode' and self.config.special_mode_cycle_enabled else 'N/A or Disabled'}**\n"
                f"Current points: **{giveaway_mgr_points}**\n"
                f"Timezone: **{stats.timezone_str}**"
            )

            embed = {
                "title": "🎮 SteamGifts Bot - Daily Report",
                "color": 0x00FF00,
                "fields": [
                    {"name": "📅 Today's Stats (since last report)", "value": f"Entries: **{stats_data['daily_entries']}**\nPoints spent: **{stats_data['daily_points']}**", "inline": True},
                    {"name": "⏱️ Bot Uptime", "value": f"**{days}** days, **{hours}** hours\nStarted: {start_time_local}", "inline": True},
                    {"name": "📊 Overall Stats", "value": f"Total entries: **{stats_data['total_entries']}**\nSuccessful: **{stats_data['successful_entries']}** ({stats_data['success_rate']})\nFailed: **{stats_data['failed_entries']}**", "inline": False},
                    {"name": "💰 Points Economy", "value": f"Total spent: **{stats_data['points_spent']}**\nAvg points/day: **{avg_daily_points:.1f}**", "inline": True},
                    {"name": "📈 Entry Rate", "value": f"Avg per hour: **{stats_data['entries_per_hour']}**\nAvg per day: **{avg_daily_entries:.1f}**", "inline": True},
                    {"name": "⚙️ Bot Configuration", "value": config_info, "inline": False}
                ],
                "footer": {"text": f"Report generated. Next report approx. {self.config.discord_notification_time} ({stats.timezone_str})"},
                "timestamp": current_local_time.isoformat()
            }

            mention_prefix = "@here " if self.config.discord_mention_stats else ""
            payload = {"content": f"{mention_prefix}📊 SteamGifts Bot Daily Report", "embeds": [embed]}

            stats.reset_daily_stats()

            max_retries, retry_delay = 3, 5
            for attempt in range(max_retries):
                try:
                    response = requests.post(self.webhook_url, json=payload, timeout=15)
                    if response.status_code in [200, 204]:
                        logging.info("Successfully sent Discord stats report.")
                        return
                    else:
                        logging.warning(f"Discord send attempt {attempt+1} failed: {response.status_code} - {response.text}")
                except Exception as e:
                    logging.error(f"Error sending Discord stats (attempt {attempt+1}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
            logging.error("Failed to send Discord stats report after all retries.")

        thread = threading.Thread(target=send_webhook, daemon=True)
        thread.start()
