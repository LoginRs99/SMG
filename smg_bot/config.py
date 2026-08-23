import os
import configparser
import logging
from typing import Dict, List, Any, Optional
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


def load_dotenv(dotenv_path: Optional[str] = None) -> None:
    """Load key-value pairs from .env file into os.environ (without external dependencies)."""
    if dotenv_path is None:
        dotenv_path = os.path.join(get_base_dir(), ".env")

    if not os.path.isfile(dotenv_path):
        return

    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                # Do not overwrite already explicitly set system env vars
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception as e:
        logging.warning(f"Could not read .env file at {dotenv_path}: {e}")


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


def get_env_or_config(key: str, section: Optional[configparser.SectionProxy] = None) -> str:
    """
    Get setting with priority:
    1. Environment variable (e.g. COOKIE or SMG_COOKIE)
    2. config.ini section value
    3. DEFAULT_CONFIG fallback
    """
    # Check uppercase and SMG_ prefix
    env_val = os.environ.get(key.upper()) or os.environ.get(f"SMG_{key.upper()}")
    if env_val is not None and env_val.strip() != "":
        return env_val.strip()

    if section is not None:
        val = section.get(key, None)
        if val is not None and val.strip() != "":
            return val.strip()

    return str(DEFAULT_CONFIG.get(key, ""))


class BotConfig:
    """Holds parsed and validated bot configuration with env and config.ini support."""

    def __init__(self, raw_config: Optional[configparser.SectionProxy] = None):
        self.raw = raw_config

        # Authentication
        self.cookie_value: str = get_env_or_config("cookie", raw_config)
        self.cookie: Dict[str, str] = {"PHPSESSID": self.cookie_value}

        # Giveaway Settings
        self.pinned_games: int = int(get_env_or_config("pinned_games", raw_config))
        self.gift_type: str = get_env_or_config("gift_type", raw_config)
        self.min_points: int = int(get_env_or_config("min_points", raw_config))
        
        ignored_raw = get_env_or_config("ignored_words", raw_config)
        self.ignored_words: List[str] = [w.strip().lower() for w in ignored_raw.split(",") if w.strip()]

        # Behavior & Timing
        self.max_entries_per_session: int = int(get_env_or_config("max_entries_per_session", raw_config))
        self.base_sleep_time: int = int(get_env_or_config("base_sleep_time", raw_config))
        self.sleep_time_no_games: int = int(get_env_or_config("sleep_time_no_games", raw_config))
        self.sleep_time_no_points: int = int(get_env_or_config("sleep_time_no_points", raw_config))
        self.min_request_interval: float = float(get_env_or_config("min_request_interval", raw_config))
        self.max_consecutive_errors: int = int(get_env_or_config("max_consecutive_errors", raw_config))

        # Special Mode
        cycle_str = get_env_or_config("special_mode_cycle", raw_config).lower()
        self.special_mode_cycle_enabled: bool = cycle_str in ("true", "1", "yes")

        raw_stages = get_env_or_config("special_mode_stages", raw_config).split(",")
        self.special_mode_stages: List[str] = [s.strip() for s in raw_stages if s.strip() in SPECIAL_MODE_URLS]
        if not self.special_mode_stages:
            self.special_mode_stages = ["Wishlist", "Group", "Recommended", "Copies", "DLC"]

        # Discord
        self.discord_webhook: str = get_env_or_config("discord_webhook", raw_config)
        self.discord_notification_time: str = get_env_or_config("discord_notification_time", raw_config)
        self.discord_mention_stats: bool = get_env_or_config("discord_mention_stats", raw_config).lower() in ("true", "1", "yes")
        self.discord_mention_wins: bool = get_env_or_config("discord_mention_wins", raw_config).lower() in ("true", "1", "yes")
        self.discord_mention_alerts: bool = get_env_or_config("discord_mention_alerts", raw_config).lower() in ("true", "1", "yes")

        # Timezone & Logging
        self.timezone_str: str = get_env_or_config("timezone", raw_config)
        try:
            self.timezone = ZoneInfo(self.timezone_str)
        except Exception:
            self.timezone = ZoneInfo("Europe/Budapest")
            self.timezone_str = "Europe/Budapest"

        self.log_level_str: str = get_env_or_config("log_level", raw_config).upper()
        self.log_to_file: bool = get_env_or_config("log_to_file", raw_config).lower() in ("true", "1", "yes")
        self.log_to_console: bool = get_env_or_config("log_to_console", raw_config).lower() in ("true", "1", "yes")


def load_config(config_path: Optional[str] = None) -> BotConfig:
    """Load configuration from environment, .env file, and/or config.ini."""
    # 1. Load .env file if present
    load_dotenv()

    if config_path is None:
        config_path = get_config_path()

    section = None
    if os.path.exists(config_path):
        config = configparser.ConfigParser(defaults=DEFAULT_CONFIG)
        config.read(config_path, encoding="utf-8")
        section = config["DEFAULT"]

    # If cookie is not in env or config file
    cookie_check = os.environ.get("COOKIE") or os.environ.get("SMG_COOKIE")
    if not cookie_check and (section is None or not section.get("cookie")):
        if not os.path.exists(config_path):
            create_default_config_file(config_path)
            raise FileNotFoundError(f"Configuration file created at {config_path}. Please configure your cookie in config.ini or .env.")

    bot_config = BotConfig(section)
    validate_bot_config(bot_config)
    return bot_config


def validate_bot_config(config: BotConfig) -> None:
    """Validate critical configuration values."""
    cookie = config.cookie_value
    if not cookie or cookie in ("#teszt", "your_phpsessid_here"):
        logging.error("Missing or placeholder 'cookie' (PHPSESSID) in configuration.")
        raise ValueError("Missing or placeholder 'cookie'. Please specify a valid PHPSESSID in .env or config.ini.")

    if config.min_points < 0:
        raise ValueError("min_points must be >= 0")
    if config.base_sleep_time < 1:
        raise ValueError("base_sleep_time must be >= 1")
    if config.min_request_interval < 0.1:
        raise ValueError("min_request_interval must be >= 0.1")

    valid_gift_types = list(FILTER_URLS.keys()) + ["Special Mode"]
    if config.gift_type not in valid_gift_types:
        raise ValueError(f"Invalid gift_type '{config.gift_type}'. Must be one of {valid_gift_types}")

    if config.discord_webhook and not config.discord_webhook.startswith("https://discord.com/api/webhooks/"):
        logging.warning(f"Discord webhook URL '{config.discord_webhook}' appears to be invalid.")


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
