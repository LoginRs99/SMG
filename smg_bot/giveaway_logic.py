import os
import json
import random
import time
import sys
import logging
from typing import List, Tuple, Optional, Set, Callable
try:
    from termcolor import colored
except ImportError:
    def colored(text, color=None, on_color=None, attrs=None):
        return text
from bs4 import BeautifulSoup
from smg_bot.config import BotConfig, FILTER_URLS, SPECIAL_MODE_URLS, get_logs_dir
from smg_bot.client import SteamGiftsClient


def log(string: str, color: str) -> None:
    """Log formatted colored message to console and file with immediate flush."""
    message = str(string)
    try:
        print(colored(message, color), flush=True)
    except Exception:
        print(message, flush=True)
    logging.info(message)
    # Ensure all logger handlers flush immediately
    for handler in logging.getLogger().handlers:
        try:
            handler.flush()
        except Exception:
            pass


def get_sleep_time(base_time: float) -> float:
    """Get randomized sleep time with +-20% jitter."""
    variance = base_time * 0.2
    return max(1.0, base_time + random.uniform(-variance, variance))


def human_delay(base: float = 2.0, variance: float = 1.5) -> None:
    """Add a human-like random delay."""
    delay = base + random.uniform(0, variance)
    time.sleep(delay)


def should_skip_randomly(probability: float = 0.15) -> bool:
    """Randomly skip some games to appear human-like (15%)."""
    return random.random() < probability


def interruptible_sleep(
    duration_seconds: float,
    heartbeat_interval: float = 600.0,
    reason: str = "",
    shutdown_check: Optional[Callable[[], bool]] = None
) -> None:
    """
    Sleep for duration_seconds while emitting periodic heartbeat log lines
    every heartbeat_interval seconds. This keeps the log file active so the
    Docker healthcheck does not misfire during long sleep cycles.
    """
    start_time = time.time()
    end_time = start_time + duration_seconds

    while time.time() < end_time:
        if shutdown_check and shutdown_check():
            break

        remaining = end_time - time.time()
        chunk = min(remaining, heartbeat_interval)
        if chunk > 0:
            time.sleep(chunk)

        current_remaining = end_time - time.time()
        if current_remaining > 60:
            rem_min = int(current_remaining / 60)
            log(f"💤 Heartbeat: still sleeping ({rem_min}m remaining) [{reason}]", "grey")


class WonCache:
    """Local cache for previously won games to avoid doomed requests."""

    def __init__(self, cache_file: Optional[str] = None):
        if cache_file is None:
            cache_file = os.path.join(get_logs_dir(), "won_cache.json")
        self.cache_file = cache_file
        self.won_games: Set[str] = set()
        self.load()

    def load(self) -> None:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.won_games = set(data)
                logging.info(f"Loaded {len(self.won_games)} cached previously won games from {self.cache_file}")
            except Exception as e:
                logging.warning(f"Could not load won cache from {self.cache_file}: {e}")
                self.won_games = set()

    def save(self) -> None:
        try:
            parent_dir = os.path.dirname(self.cache_file)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(sorted(list(self.won_games)), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Failed to save won cache to {self.cache_file}: {e}")

    def is_won(self, game_name: str) -> bool:
        return game_name.strip().lower() in self.won_games

    def add(self, game_name: str) -> bool:
        normalized = game_name.strip().lower()
        if normalized and normalized not in self.won_games:
            self.won_games.add(normalized)
            self.save()
            return True
        return False

    def add_many(self, game_names: List[str]) -> int:
        added = 0
        for name in game_names:
            normalized = name.strip().lower()
            if normalized and normalized not in self.won_games:
                self.won_games.add(normalized)
                added += 1
        if added > 0:
            self.save()
        return added


class GiveawayManager:
    """Orchestrates giveaway scanning, filtering, and entry execution."""

    def __init__(self, config: BotConfig, client: SteamGiftsClient):
        self.config = config
        self.client = client
        self.won_cache = WonCache()

        self.gift_type = config.gift_type
        self.pinned = config.pinned_games
        self.min_points = config.min_points
        self.ignored_words = config.ignored_words
        self.max_entries_per_session = config.max_entries_per_session
        self.base_sleep_time = config.base_sleep_time
        self.sleep_time_no_games = config.sleep_time_no_games
        self.sleep_time_no_points = config.sleep_time_no_points
        self.special_mode_stages = config.special_mode_stages
        self.special_mode_cycle_enabled = config.special_mode_cycle_enabled

        self.special_mode_stage = 0
        self.entries_count = 0
        self.points = 0
        self.xsrf_token: Optional[str] = None
        self.shutdown_flag = False

        if self.gift_type == "Special Mode" and self.special_mode_stages:
            self.filter_url = SPECIAL_MODE_URLS[self.special_mode_stages[self.special_mode_stage]]
        elif self.gift_type in FILTER_URLS:
            self.filter_url = FILTER_URLS[self.gift_type]
        else:
            self.gift_type = "All"
            self.filter_url = FILTER_URLS["All"]

    def update_info(self) -> None:
        """Update current points and xsrf_token."""
        human_delay(1, 1)
        log("🔄 Updating user info (points, xsrf_token)...", "blue")
        token, points = self.client.fetch_user_info()
        self.xsrf_token = token
        self.points = points
        log(f"💰 Current points: {self.points}, XSRF token updated.", "cyan")

    def sleep_if_not_enough_points(self) -> bool:
        """
        Dynamically calculate sleep duration based on missing points.
        SteamGifts awards ~20-25P per hour (~150s per point).
        Clamped between 15 minutes (900s) and sleep_time_no_points (max 4h) with jitter.
        """
        if self.points >= self.min_points:
            return False

        missing_points = max(1, self.min_points - self.points)
        estimated_regen_seconds = missing_points * 150
        clamped_wait = max(900.0, min(float(self.sleep_time_no_points), float(estimated_regen_seconds)))
        sleep_duration = get_sleep_time(clamped_wait)

        log(f"📉 Points ({self.points}) below minimum ({self.min_points}). Missing {missing_points}P. Dynamic sleep: {int(sleep_duration/60)}m.", "yellow")
        interruptible_sleep(
            sleep_duration,
            heartbeat_interval=600,
            reason=f"point regen ({missing_points}P missing)",
            shutdown_check=lambda: self.shutdown_flag
        )
        return True

    def get_game_info(self, item_soup: BeautifulSoup) -> Tuple[int, str, str]:
        """Extract cost, game name, and giveaway ID from giveaway row."""
        cost_tag = item_soup.find_all("span", {"class": "giveaway__heading__thin"})[-1]
        game_cost = int(cost_tag.getText().replace("(", "").replace(")", "").replace("P", ""))
        name_tag = item_soup.find("a", {"class": "giveaway__heading__name"})
        game_name = name_tag.text.strip()
        game_id = name_tag["href"].split("/")[2]
        return game_cost, game_name, game_id

    def get_games_list(self, page_num: int) -> List[BeautifulSoup]:
        """Fetch and filter eligible giveaway items on a specific page."""
        paginated_url = f"{self.client.base_url}/giveaways/{self.filter_url.format(page_num, self.points)}"
        log(f"🔍 Fetching games from: {paginated_url}", "magenta")
        soup = self.client.get_soup(paginated_url)

        processed_games = []
        if soup:
            try:
                all_giveaways = soup.find_all("div", {"class": "giveaway__row-inner-wrap"})
                for item_soup in all_giveaways:
                    if "is-faded" in item_soup.get("class", []):
                        continue

                    name_tag = item_soup.find("a", {"class": "giveaway__heading__name"})
                    if not name_tag:
                        log(f"⚠️ Skipping item due to missing name_tag: {item_soup.prettify()[:200]}", "yellow")
                        continue

                    game_name = name_tag.text.strip()

                    # Filter ignored words
                    if any(ignored in game_name.lower() for ignored in self.ignored_words if ignored):
                        continue

                    # Filter pinned games
                    is_pinned = item_soup.find_parent("div", class_="pinned-giveaways__inner-wrap") is not None
                    if self.pinned == 0 and is_pinned:
                        continue
                    elif self.pinned == 1 and not is_pinned:
                        continue

                    # Local cache check before considering entry
                    if self.won_cache.is_won(game_name):
                        log(f"🛡️ [WonCache] Skipping already-won game: {game_name}", "grey")
                        continue

                    processed_games.append(item_soup)
            finally:
                soup.decompose()
        return processed_games

    def entry_gift(self, game_id: str, game_cost: int, game_name: str, stats_callback: Callable[[bool, int], None]) -> bool:
        """Perform giveaway entry request."""
        if not self.xsrf_token:
            log("❌ Cannot enter gift: XSRF token is missing. Refreshing info...", "red")
            try:
                self.update_info()
                if not self.xsrf_token:
                    stats_callback(False, 0)
                    return False
            except Exception as e:
                log(f"❌ Error during XSRF token refresh: {e}", "red")
                stats_callback(False, 0)
                return False

        try:
            response = self.client.post_entry(game_id, self.xsrf_token)
            if response.status_code == 200:
                result = response.json()
                if result.get("type") == "success":
                    stats_callback(True, game_cost)
                    # Sync exact points from server response if available
                    if "points" in result and result["points"] is not None:
                        try:
                            self.points = int(result["points"])
                        except (ValueError, TypeError):
                            self.points -= game_cost
                    else:
                        self.points -= game_cost
                    return True
                else:
                    msg = result.get('msg', 'Unknown error from SG')
                    log(f"⚠️ Failed to enter giveaway ({game_id}): {msg}", "yellow")
                    stats_callback(False, 0)

                    # Update local won cache immediately on 'Previously Won' response
                    if "Previously Won" in msg:
                        self.won_cache.add(game_name)
                        log(f"🛡️ Added '{game_name}' to local won cache.", "cyan")

                    if "You do not have enough points" in msg:
                        new_points = result.get('points')
                        if new_points is not None:
                            self.points = int(new_points)
                    return False
            else:
                log(f"🚫 Server error on entry ({game_id}): {response.status_code}", "red")
                stats_callback(False, 0)
                return False
        except json.JSONDecodeError:
            log(f"🚫 Invalid JSON response on entry ({game_id}): {response.text}", "red")
            stats_callback(False, 0)
            return False
        except Exception as e:
            log(f"🚫 Error on entry ({game_id}): {str(e)}", "red")
            stats_callback(False, 0)
            return False

    def get_game_content(self, stats_callback: Callable[[bool, int], None], start_page: int = 1) -> None:
        """Run a giveaway processing session across 3 to 6 pages."""
        log(f"🚀 Starting game processing session. Current points: {self.points}", "blue")
        unaffordable_games_seen_this_session = 0
        max_unaffordable_before_break = 10
        max_pages_this_session = random.randint(3, 6)
        current_page_num = start_page

        while current_page_num <= max_pages_this_session:
            if self.shutdown_flag:
                return

            if self.points < self.min_points:
                log(f"📉 Points ({self.points}) dropped below minimum ({self.min_points}) during session.", "yellow")
                return

            if current_page_num > start_page and random.random() < 0.25:
                break_duration = random.uniform(10, 30)
                log(f"☕ Taking a short break ({int(break_duration)}s) before page {current_page_num}.", "cyan")
                time.sleep(break_duration)

            log(f"📄 Checking page {current_page_num} (up to {max_pages_this_session} this session)...", "magenta")
            games_list_soup = self.get_games_list(current_page_num)

            if not games_list_soup:
                if current_page_num == 1:
                    log("⚠️ No games found on page 1 for current filter settings.", "yellow")
                    if self.gift_type == "Special Mode":
                        log("↪️ Switching to next Special Mode stage.", "blue")
                        self.set_next_special_mode_stage(stats_callback)
                        return
                    else:
                        log("🛋️ No games available in this mode currently. Session ending.", "yellow")
                        return
                else:
                    log(f"🏁 No more games found on page {current_page_num}. Ending page scan.", "green")
                    break

            log(f"🎁 Found {len(games_list_soup)} potential games on page {current_page_num}.", "green")

            for item_soup in games_list_soup:
                if self.shutdown_flag:
                    return

                if self.entries_count >= self.max_entries_per_session:
                    sleep_duration = get_sleep_time(self.base_sleep_time * 2)
                    log(f"🛑 Reached max entries ({self.max_entries_per_session}) this activity session. Sleeping for {int(sleep_duration/60)}m.", "yellow")
                    self.entries_count = 0
                    interruptible_sleep(
                        sleep_duration,
                        heartbeat_interval=300,
                        reason="session entry limit reached",
                        shutdown_check=lambda: self.shutdown_flag
                    )
                    return

                game_cost, game_name, game_id = self.get_game_info(item_soup)

                # Cost check
                if game_cost > self.points:
                    log(f"💸 Too expensive: {game_name} ({game_cost}P). Have: {self.points}P. Skipping.", "grey")
                    unaffordable_games_seen_this_session += 1
                    if unaffordable_games_seen_this_session >= max_unaffordable_before_break:
                        log(f"📈 Seen {unaffordable_games_seen_this_session} unaffordable games. Taking a break.", "yellow")
                        break_sleep = get_sleep_time(self.sleep_time_no_points / 3)
                        interruptible_sleep(
                            break_sleep,
                            heartbeat_interval=600,
                            reason="unaffordable games threshold",
                            shutdown_check=lambda: self.shutdown_flag
                        )
                        return
                    human_delay(0.5, 0.5)
                    continue
                else:
                    unaffordable_games_seen_this_session = 0

                # 15% random skip
                if should_skip_randomly(0.15):
                    log(f"🤔 Randomly skipping: {game_name} ({game_cost}P)", "cyan")
                    human_delay(1, 1)
                    continue

                human_delay(base=2.0, variance=1.5)

                if self.entry_gift(game_id, game_cost, game_name, stats_callback):
                    self.entries_count += 1
                    log(f"🎉 Entered: {game_name} ({game_cost}P). Points left: {self.points}. Session entries: {self.entries_count}/{self.max_entries_per_session}", "green")

                    entry_sleep = get_sleep_time(self.base_sleep_time)
                    log(f"💤 Sleeping for {int(entry_sleep)}s after entry.", "cyan")
                    time.sleep(entry_sleep)

                    if random.random() < 0.15:
                        extra_pause = random.uniform(20, 50)
                        log(f"⏸️ Taking a longer pause ({int(extra_pause)}s)...", "cyan")
                        time.sleep(extra_pause)
                else:
                    log(f"❌ Failed or decided not to enter: {game_name} ({game_cost}P).", "red")

            current_page_num += 1

        log(f"🏁 Finished game processing session (scanned up to {max_pages_this_session} pages).", "blue")

    def set_next_special_mode_stage(self, stats_callback: Callable[[bool, int], None]) -> None:
        """Cycle to next Special Mode filter."""
        if not self.special_mode_stages:
            log("⚠️ No special mode stages defined. Cannot switch.", "red")
            time.sleep(self.sleep_time_no_games)
            return

        if not self.special_mode_cycle_enabled and self.special_mode_stage > 0:
            log("↪️ Special mode cycling disabled, staying on first configured stage.", "blue")
            self.special_mode_stage = 0
        else:
            self.special_mode_stage += 1

        if self.special_mode_stage >= len(self.special_mode_stages):
            log("🔄 Completed all Special Mode stages. Resetting cycle.", "blue")
            self.special_mode_stage = 0
            sleep_duration = get_sleep_time(self.sleep_time_no_games / 2)
            log(f"💤 Sleeping for {int(sleep_duration/60)}m before restarting Special Mode cycle.", "yellow")
            interruptible_sleep(
                sleep_duration,
                heartbeat_interval=300,
                reason="special mode cycle reset",
                shutdown_check=lambda: self.shutdown_flag
            )

        current_stage_name = self.special_mode_stages[self.special_mode_stage]
        self.filter_url = SPECIAL_MODE_URLS[current_stage_name]
        log(f"✨ Special Mode: Switched to '{current_stage_name}'. Filter: {self.filter_url.split('?')[0]}", "green")
        human_delay(1, 1)
        self.get_game_content(stats_callback)

    def check_for_wins(self, notify_callback: Callable[[List[str]], None]) -> List[str]:
        """Check /giveaways/won, refresh local cache, and notify newly won games."""
        log("🏆 Checking for won games...", "magenta")
        newly_won = []
        try:
            url = f"{self.client.base_url}/giveaways/won"
            soup = self.client.get_soup(url)
            won_items = soup.find_all("div", {"class": "giveaway__row-inner-wrap"})

            all_scanned_wins = []
            for item in won_items:
                if "is-faded" in item.get("class", []):
                    continue
                name_tag = item.find("a", {"class": "giveaway__heading__name"})
                if name_tag:
                    game_title = name_tag.text.strip()
                    all_scanned_wins.append(game_title)

            # Update won cache
            if all_scanned_wins:
                added = self.won_cache.add_many(all_scanned_wins)
                if added > 0:
                    log(f"🛡️ Populated {added} newly discovered game(s) into won cache.", "cyan")

            # Call notifier for announcement
            if all_scanned_wins and notify_callback:
                notify_callback(all_scanned_wins)

            soup.decompose()
        except Exception as e:
            log(f"⚠️ Error checking won games: {e}", "red")

        return newly_won
