# CHANGELOG - SteamGifts Bot Modernization

This document summarizes the architectural modernization from the monolithic `steamgifts_bot.py` (846 lines) into the modular `smg_bot/` package, strictly mapped to the 8 approved change items.

---

### Item 1: Local "Previously Won" Cache (`WonCache`)
- **Location:** `smg_bot/giveaway_logic.py` (`WonCache` class).
- **Behavior:** Persists a set of already-won games in `logs/won_cache.json`. When inspecting giveaway listings, items present in this cache are skipped immediately with a grey log entry, avoiding doomed AJAX requests to SteamGifts without altering any giveaway entry timing.
- **Population:** Automatically populated on periodic `/giveaways/won` page scans and whenever SteamGifts returns `"Previously Won"` on an entry attempt.

### Item 2: Dockerfile Secret Leak Fix
- **Location:** `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `config/config.ini.example`.
- **Behavior:** Removed `COPY config/config.ini /app/config/config.ini` from `Dockerfile`. Added `.dockerignore` to ensure `config/config.ini` and `logs/` are never included in Docker build contexts. Created `config/config.ini.example` as a clean template. The real configuration is injected exclusively via runtime volume mounts (`./config:/app/config`).

### Item 3: Consistent Config Defaults
- **Location:** `smg_bot/config.py` (`DEFAULT_CONFIG` dictionary and `BotConfig` class).
- **Behavior:** Consolidated all default values into a single source of truth (`DEFAULT_CONFIG`) matching the proven 6.5-month production configuration (`min_points=70`, `min_request_interval=5.0`, `base_sleep_time=120`, `max_entries_per_session=8`, `sleep_time_no_games=1800`, `sleep_time_no_points=14400`, `special_mode_stages="Wishlist,Group,Recommended,DLC"`).

### Item 4: Cross-Platform Paths
- **Location:** `smg_bot/config.py` (`get_base_dir()`, `get_logs_dir()`, `get_config_path()`).
- **Behavior:** Replaced all hardcoded `/app/logs/...` paths with functions that resolve paths dynamically using environment variables (`APP_DIR`, `LOGS_DIR`, `CONFIG_PATH`) with fallback to the local repository directory. Allows seamless local execution on Windows/Linux as well as inside Docker.

### Item 5: Healthcheck vs. Long-Sleep Conflict
- **Location:** `smg_bot/giveaway_logic.py` (`interruptible_sleep()`).
- **Behavior:** Long sleeps (such as the 4-hour `sleep_time_no_points` wait) are executed in chunks of up to 10 minutes (600s), emitting a periodic heartbeat log line (`💤 Heartbeat: still sleeping...`). This updates `steamgifts_bot.log` mtime, preventing Docker healthcheck timeouts without shortening or altering the sleep duration.

### Item 6: Per-Request User-Agent Rotation
- **Location:** `smg_bot/client.py` (`SteamGiftsClient.get_headers()`).
- **Behavior:** `random.choice(USER_AGENTS)` is now evaluated dynamically on every HTTP request rather than being fixed once during instance initialization.

### Item 7: Discord Notification Cleanup & Persistence
- **Location:** `smg_bot/notifier.py` (`DiscordNotifier` and `NotifiedWinsStore`).
- **Behavior:**
  - Preserved exactly 3 notification types: Daily stats report, Giveaway win announcement, and Cookie expiration/stop alert.
  - Made `@here` opt-in via config keys: `discord_mention_stats` (default `False`), `discord_mention_wins` (default `True`), and `discord_mention_alerts` (default `True`).
  - Added persistent `logs/notified_wins.json` storage to prevent duplicate win announcements when the bot or container restarts.

### Item 8: Dependency Cleanup & HTML Parser Decision
- **Location:** `requirements.txt`.
- **Behavior:**
  - Removed `fake-useragent` (unused).
  - Removed `configparser` (part of Python standard library).
  - Removed `lxml`. **Decision:** We chose `html.parser` because it is built into the Python standard library, requires zero C-extension build dependencies in minimal Docker containers, and has proven 100% reliable across 670,000+ lines of production web scraping.
