import os
import logging
from typing import Dict, List, Any, Optional
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

# Single source of truth for all configuration defaults
DEFAULT_CONFIG: Dict[str, Any] = {
    # Authentication
    "COOKIE": "",
    # Giveaway Settings
    "PINNED_GAMES": "0",
    "GIFT_TYPE": "Special Mode",
    "MIN_POINTS": "70",
    "IGNORED_WORDS": "",
    # Bot Behavior & Limits
    "MAX_ENTRIES_PER_SESSION": "8",
    "BASE_SLEEP_TIME": "120",
    "SLEEP_TIME_NO_GAMES": "1800",
    "SLEEP_TIME_NO_POINTS": "14400",
    "MIN_REQUEST_INTERVAL": "5.0",
    "MAX_CONSECUTIVE_ERRORS": "5",
    # Special Mode (Wishlist -> Group -> Recommended -> Copies -> DLC)
    "SPECIAL_MODE_CYCLE": "True",
    "SPECIAL_MODE_STAGES": "Wishlist,Group,Recommended,Copies,DLC",
    # Discord Integration
    "DISCORD_WEBHOOK": "",
    "DISCORD_NOTIFICATION_TIME": "23:00",
    "DISCORD_MENTION_STATS": "False",     # Opt-in @here for daily stats
    "DISCORD_MENTION_WINS": "True",       # Opt-in @here for won giveaways
    "DISCORD_MENTION_ALERTS": "True",     # Opt-in @here for cookie expiry
    # Runtime & Logging
    "TIMEZONE": "Europe/Budapest",
    "LOG_LEVEL": "INFO",
    "LOG_TO_FILE": "True",
    "LOG_TO_CONSOLE": "True",
}

FILTER_URLS: Dict[str, str] = {
    "Special Mode": "search?page={}&point_max={}",
    "All": "search?page={}&point_max={}",
    "Wishlist": "search?page={}&type=wishlist&point_max={}",
    "Recommended": "search?page={}&type=recommended&point_max={}",
    "Copies": "search?page={}&copy_min=2&point_max={}",
    "DLC": "search?page={}&dlc=true&point_max={}",
    "Group": "search?page={}&type=group&point_max={}",
    "New": "search?page={}&type=new&point_max={}",
}

SPECIAL_MODE_URLS: Dict[str, str] = {
    "Wishlist": "search?page={}&type=wishlist&point_max={}",
    "Recommended": "search?page={}&type=recommended&point_max={}",
    "Group": "search?page={}&type=group&point_max={}",
    "Copies": "search?page={}&copy_min=2&point_max={}",
    "DLC": "search?page={}&dlc=true&point_max={}",
    "New": "search?page={}&type=new&point_max={}",
    "All": "search?page={}&point_max={}"
}


def get_base_dir() -> str:
    """Resolve the base application directory across platforms."""
    env_base = os.environ.get("APP_DIR")
    if env_base:
        return os.path.abspath(env_base)
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(pkg_dir)


def get_logs_dir() -> str:
    """Resolve the logs directory cross-platform."""
    env_logs = os.environ.get("LOGS_DIR")
    if env_logs:
        logs_dir = os.path.abspath(env_logs)
    else:
        base_dir = get_base_dir()
        logs_dir = os.path.join(base_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    return logs_dir


def get_dotenv_paths() -> List[str]:
    """Return all candidate .env paths in order of resolution."""
    base_dir = get_base_dir()
    candidates = [
        os.path.join(base_dir, ".env"),
        os.path.join(os.getcwd(), ".env"),
        "/app/.env"
    ]
    seen = set()
    result = []
    for c in candidates:
        norm = os.path.normpath(c)
        if norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


def load_dotenv() -> None:
    """Parse .env files into os.environ (ignoring comments, empty values, and placeholders)."""
    for path in get_dotenv_paths():
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        if key:
                            os.environ[key] = val
                            os.environ[key.upper()] = val
            except Exception as e:
                logging.warning(f"Could not read .env file at {path}: {e}")


def get_setting(key: str) -> str:
    """Get setting from environment variables or DEFAULT_CONFIG fallback."""
    upper_key = key.upper()
    val = os.environ.get(upper_key) or os.environ.get(f"SMG_{upper_key}") or os.environ.get(key.lower())
    if val is not None and val.strip() != "":
        return val.strip()
    return str(DEFAULT_CONFIG.get(upper_key, ""))


class BotConfig:
    """Holds parsed and validated bot configuration from .env / environment variables."""

    def __init__(self):
        # Authentication
        self.cookie_value: str = get_setting("COOKIE")
        self.cookie: Dict[str, str] = {"PHPSESSID": self.cookie_value}

        # Giveaway Settings
        self.pinned_games: int = int(get_setting("PINNED_GAMES"))
        self.gift_type: str = get_setting("GIFT_TYPE")
        self.min_points: int = int(get_setting("MIN_POINTS"))
        
        ignored_raw = get_setting("IGNORED_WORDS")
        self.ignored_words: List[str] = [w.strip().lower() for w in ignored_raw.split(",") if w.strip()]

        # Behavior & Timing
        self.max_entries_per_session: int = int(get_setting("MAX_ENTRIES_PER_SESSION"))
        self.base_sleep_time: int = int(get_setting("BASE_SLEEP_TIME"))
        self.sleep_time_no_games: int = int(get_setting("SLEEP_TIME_NO_GAMES"))
        self.sleep_time_no_points: int = int(get_setting("SLEEP_TIME_NO_POINTS"))
        self.min_request_interval: float = float(get_setting("MIN_REQUEST_INTERVAL"))
        self.max_consecutive_errors: int = int(get_setting("MAX_CONSECUTIVE_ERRORS"))

        # Special Mode
        cycle_str = get_setting("SPECIAL_MODE_CYCLE").lower()
        self.special_mode_cycle_enabled: bool = cycle_str in ("true", "1", "yes")

        raw_stages = get_setting("SPECIAL_MODE_STAGES").split(",")
        self.special_mode_stages: List[str] = [s.strip() for s in raw_stages if s.strip() in SPECIAL_MODE_URLS]
        if not self.special_mode_stages:
            self.special_mode_stages = ["Wishlist", "Group", "Recommended", "Copies", "DLC"]

        # Discord
        self.discord_webhook: str = get_setting("DISCORD_WEBHOOK")
        self.discord_notification_time: str = get_setting("DISCORD_NOTIFICATION_TIME")
        self.discord_mention_stats: bool = get_setting("DISCORD_MENTION_STATS").lower() in ("true", "1", "yes")
        self.discord_mention_wins: bool = get_setting("DISCORD_MENTION_WINS").lower() in ("true", "1", "yes")
        self.discord_mention_alerts: bool = get_setting("DISCORD_MENTION_ALERTS").lower() in ("true", "1", "yes")

        # Timezone & Logging
        self.timezone_str: str = get_setting("TIMEZONE")
        try:
            self.timezone = ZoneInfo(self.timezone_str)
        except Exception:
            self.timezone = ZoneInfo("Europe/Budapest")
            self.timezone_str = "Europe/Budapest"

        self.log_level_str: str = get_setting("LOG_LEVEL").upper()
        self.log_to_file: bool = get_setting("LOG_TO_FILE").lower() in ("true", "1", "yes")
        self.log_to_console: bool = get_setting("LOG_TO_CONSOLE").lower() in ("true", "1", "yes")


def load_config() -> BotConfig:
    """Load and validate configuration from .env / environment."""
    load_dotenv()
    bot_config = BotConfig()
    validate_bot_config(bot_config)
    return bot_config


def validate_bot_config(config: BotConfig) -> None:
    """Validate critical configuration values."""
    cookie = config.cookie_value
    if not cookie or cookie in ("#teszt", "your_phpsessid_here"):
        logging.error("Missing or placeholder 'COOKIE' (PHPSESSID) in configuration.")
        raise ValueError("Missing or placeholder 'COOKIE'. Please specify a valid PHPSESSID in .env.")

    if config.min_points < 0:
        raise ValueError("MIN_POINTS must be >= 0")
    if config.base_sleep_time < 1:
        raise ValueError("BASE_SLEEP_TIME must be >= 1")
    if config.min_request_interval < 0.1:
        raise ValueError("MIN_REQUEST_INTERVAL must be >= 0.1")

    valid_gift_types = list(FILTER_URLS.keys()) + ["Special Mode"]
    if config.gift_type not in valid_gift_types:
        raise ValueError(f"Invalid GIFT_TYPE '{config.gift_type}'. Must be one of {valid_gift_types}")

    if config.discord_webhook and not config.discord_webhook.startswith("https://discord.com/api/webhooks/"):
        logging.warning(f"Discord webhook URL '{config.discord_webhook}' appears to be invalid.")
