import os
import configparser
import logging
from typing import Dict, List, Any
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

# Single source of truth for all configuration defaults
DEFAULT_CONFIG: Dict[str, Any] = {
    # Authentication
    "cookie": "",
    # Giveaway Settings
    "pinned_games": "0",
    "gift_type": "Special Mode",
    "min_points": "70",
    "ignored_words": "",
    # Bot Behavior & Limits
    "max_entries_per_session": "8",
    "base_sleep_time": "120",
    "sleep_time_no_games": "1800",
    "sleep_time_no_points": "14400",
    "min_request_interval": "5.0",
    "max_consecutive_errors": "5",
    # Special Mode (Wishlist -> Group -> Recommended -> Copies -> DLC)
    "special_mode_cycle": "True",
    "special_mode_stages": "Wishlist,Group,Recommended,Copies,DLC",
    # Discord Integration
    "discord_webhook": "",
    "discord_notification_time": "23:00",
    "discord_mention_stats": "False",     # Opt-in @here for daily stats (default: False)
    "discord_mention_wins": "True",       # Opt-in @here for won giveaways (default: True)
    "discord_mention_alerts": "True",     # Opt-in @here for critical cookie expiry (default: True)
    # Runtime & Logging
    "timezone": "Europe/Budapest",
    "log_level": "INFO",
    "log_to_file": "True",
    "log_to_console": "True",
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


def get_config_path() -> str:
    """Resolve the config file path cross-platform."""
    env_config = os.environ.get("CONFIG_PATH")
    if env_config:
        return os.path.abspath(env_config)
    base_dir = get_base_dir()
    return os.path.join(base_dir, "config", "config.ini")


class BotConfig:
    """Holds parsed and validated bot configuration."""

    def __init__(self, raw_config: configparser.SectionProxy):
        self.raw = raw_config

        # Authentication
        self.cookie_value: str = raw_config.get("cookie", DEFAULT_CONFIG["cookie"]).strip()
        self.cookie: Dict[str, str] = {"PHPSESSID": self.cookie_value}

        # Giveaway Settings
        self.pinned_games: int = raw_config.getint("pinned_games", int(DEFAULT_CONFIG["pinned_games"]))
        self.gift_type: str = raw_config.get("gift_type", DEFAULT_CONFIG["gift_type"])
        self.min_points: int = raw_config.getint("min_points", int(DEFAULT_CONFIG["min_points"]))
        
        ignored_raw = raw_config.get("ignored_words", DEFAULT_CONFIG["ignored_words"])
        self.ignored_words: List[str] = [w.strip().lower() for w in ignored_raw.split(",") if w.strip()]

        # Behavior & Timing
        self.max_entries_per_session: int = raw_config.getint("max_entries_per_session", int(DEFAULT_CONFIG["max_entries_per_session"]))
        self.base_sleep_time: int = raw_config.getint("base_sleep_time", int(DEFAULT_CONFIG["base_sleep_time"]))
        self.sleep_time_no_games: int = raw_config.getint("sleep_time_no_games", int(DEFAULT_CONFIG["sleep_time_no_games"]))
        self.sleep_time_no_points: int = raw_config.getint("sleep_time_no_points", int(DEFAULT_CONFIG["sleep_time_no_points"]))
        self.min_request_interval: float = raw_config.getfloat("min_request_interval", float(DEFAULT_CONFIG["min_request_interval"]))
        self.max_consecutive_errors: int = raw_config.getint("max_consecutive_errors", int(DEFAULT_CONFIG["max_consecutive_errors"]))

        # Special Mode
        self.special_mode_cycle_enabled: bool = raw_config.getboolean("special_mode_cycle", DEFAULT_CONFIG["special_mode_cycle"].lower() == "true")
        raw_stages = raw_config.get("special_mode_stages", DEFAULT_CONFIG["special_mode_stages"]).split(",")
        self.special_mode_stages: List[str] = [s.strip() for s in raw_stages if s.strip() in SPECIAL_MODE_URLS]
        if not self.special_mode_stages:
            self.special_mode_stages = ["Wishlist", "Group", "Recommended", "Copies", "DLC"]

        # Discord
        self.discord_webhook: str = raw_config.get("discord_webhook", DEFAULT_CONFIG["discord_webhook"]).strip()
        self.discord_notification_time: str = raw_config.get("discord_notification_time", DEFAULT_CONFIG["discord_notification_time"]).strip()
        self.discord_mention_stats: bool = raw_config.getboolean("discord_mention_stats", DEFAULT_CONFIG["discord_mention_stats"].lower() == "true")
        self.discord_mention_wins: bool = raw_config.getboolean("discord_mention_wins", DEFAULT_CONFIG["discord_mention_wins"].lower() == "true")
        self.discord_mention_alerts: bool = raw_config.getboolean("discord_mention_alerts", DEFAULT_CONFIG["discord_mention_alerts"].lower() == "true")

        # Timezone & Logging
        self.timezone_str: str = raw_config.get("timezone", DEFAULT_CONFIG["timezone"]).strip()
        try:
            self.timezone = ZoneInfo(self.timezone_str)
        except Exception:
            self.timezone = ZoneInfo("Europe/Budapest")
            self.timezone_str = "Europe/Budapest"

        self.log_level_str: str = raw_config.get("log_level", DEFAULT_CONFIG["log_level"]).upper()
        self.log_to_file: bool = raw_config.getboolean("log_to_file", DEFAULT_CONFIG["log_to_file"].lower() == "true")
        self.log_to_console: bool = raw_config.getboolean("log_to_console", DEFAULT_CONFIG["log_to_console"].lower() == "true")


def load_config(config_path: str = None) -> BotConfig:
    """Load, validate, and return BotConfig."""
    if config_path is None:
        config_path = get_config_path()

    if not os.path.exists(config_path):
        create_default_config_file(config_path)
        raise FileNotFoundError(f"Configuration file created at {config_path}. Please configure your cookie.")

    config = configparser.ConfigParser(defaults=DEFAULT_CONFIG)
    config.read(config_path, encoding="utf-8")
    section = config["DEFAULT"]

    validate_config(section)
    return BotConfig(section)


def validate_config(section: configparser.SectionProxy) -> None:
    """Validate critical configuration values."""
    cookie = section.get("cookie", "").strip()
    if not cookie or cookie == "#teszt" or cookie == "your_phpsessid_here":
        logging.error("Missing or placeholder 'cookie' (PHPSESSID) in config.")
        raise ValueError("Missing or placeholder 'cookie' in config. Please specify a valid PHPSESSID.")

    # Validate numeric values
    numeric_fields = {
        "min_points": 0,
        "pinned_games": 0,
        "base_sleep_time": 1,
        "sleep_time_no_games": 1,
        "sleep_time_no_points": 1,
        "max_consecutive_errors": 1,
        "max_entries_per_session": 1,
    }
    for field, min_val in numeric_fields.items():
        try:
            val = int(section.get(field, DEFAULT_CONFIG[field]))
            if val < min_val:
                raise ValueError(f"Value for '{field}' must be >= {min_val}")
        except ValueError as e:
            logging.error(f"Invalid integer for '{field}': {e}")
            raise ValueError(f"Invalid integer for '{field}'") from e

    try:
        val_float = float(section.get("min_request_interval", DEFAULT_CONFIG["min_request_interval"]))
        if val_float < 0.1:
            raise ValueError("min_request_interval must be >= 0.1")
    except ValueError as e:
        logging.error(f"Invalid float for 'min_request_interval': {e}")
        raise ValueError("Invalid float for 'min_request_interval'") from e

    # Validate timezone
    tz_str = section.get("timezone", DEFAULT_CONFIG["timezone"])
    try:
        ZoneInfo(tz_str)
    except Exception as e:
        logging.error(f"Invalid timezone string in config: {tz_str}. Error: {e}")
        raise ValueError(f"Invalid timezone string: {tz_str}") from e

    # Validate gift_type
    valid_gift_types = list(FILTER_URLS.keys()) + ["Special Mode"]
    gift_type_val = section.get("gift_type", DEFAULT_CONFIG["gift_type"])
    if gift_type_val not in valid_gift_types:
        logging.error(f"Invalid gift_type '{gift_type_val}'. Must be one of {valid_gift_types}")
        raise ValueError(f"Invalid gift_type '{gift_type_val}'")

    webhook_url = section.get("discord_webhook", "").strip()
    if webhook_url and not webhook_url.startswith("https://discord.com/api/webhooks/"):
        logging.warning(f"Discord webhook URL '{webhook_url}' appears to be invalid.")


def create_default_config_file(config_path: str) -> None:
    """Create a default configuration template."""
    directory = os.path.dirname(config_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    config = configparser.ConfigParser()
    config["DEFAULT"] = DEFAULT_CONFIG
    with open(config_path, "w", encoding="utf-8") as f:
        config.write(f)
    logging.warning(f"Default configuration template created at {config_path}.")
