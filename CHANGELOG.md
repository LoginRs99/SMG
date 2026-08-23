# CHANGELOG - SteamGifts Bot Modernization

This document summarizes the architectural modernization from the monolithic `steamgifts_bot.py` into the modular `smg_bot/` package, including all approved baseline improvements and new advanced resilience features.

---

### Core Architecture & Baseline Improvements
1. **Local "Previously Won" Cache (`WonCache`):** Persists won games in `logs/won_cache.json` to skip already-won games before sending doomed AJAX requests.
2. **Dockerfile Secret Leak Fix:** Removed `config.ini` copy from Dockerfile. Added `.dockerignore` and `config.ini.example`. Configuration is supplied exclusively via runtime volume mounts.
3. **Consistent Config Defaults:** Single source of truth in `DEFAULT_CONFIG` (`smg_bot/config.py`).
4. **Cross-Platform Paths:** Dynamic resolution of `APP_DIR`, `LOGS_DIR`, `CONFIG_PATH` for seamless Windows, Linux, and Docker execution.
5. **Healthcheck Heartbeat:** Periodic heartbeat logs during long sleep cycles to prevent Docker healthcheck timeouts.
6. **Per-Request User-Agent Rotation:** Dynamic `random.choice(USER_AGENTS)` per HTTP request.
7. **Discord Notification Cleanup:** 3 clean notification types, opt-in `@here` toggles, and persistent `notified_wins.json` deduplication.
8. **Dependency Cleanup:** Removed `fake-useragent`, `configparser`, and `lxml`; standardized on Python stdlib `html.parser`.

---

### Advanced Resilience & Priority Enhancements (New)
9. **Dynamic Point-Based Sleep Calculation:**
   - Instead of sleeping a fixed 4 hours when points drop below threshold, the bot calculates exact estimated regeneration time ($pprox 150	ext{s per point}$) bounded between 15 minutes and the configured maximum cap with $\pm 20\%$ jitter.
10. **Zero-Crash Hot-Reload IDLE Standby Mode:**
    - On expired/invalid `PHPSESSID`, the bot sends **one** Discord alert and enters an intelligent IDLE standby loop watching `config.ini` file modifications.
    - When the user pastes a new cookie into `config.ini`, the bot automatically reloads, verifies credentials, and resumes operations without triggering container restart loops.
11. **Exponential Backoff for Consecutive Errors:**
    - Replaced static 15-minute error delays with dynamic exponential backoff with jitter ($5	ext{m} ightarrow 10	ext{m} ightarrow 20	ext{m} ightarrow 40	ext{m} ightarrow \dots 	ext{max } 2	ext{h}$) to protect against Cloudflare/network transient issues.
12. **Optimized Special Mode Category Priority:**
    - Updated cycle order to prioritize high-value and high-odds categories:
      `Wishlist` $ightarrow$ `Group` $ightarrow$ `Recommended` $ightarrow$ `Copies` $ightarrow$ `DLC`.
