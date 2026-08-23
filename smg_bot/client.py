import os
import random
import time
import logging
from typing import Dict, Tuple, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from bs4 import BeautifulSoup
from smg_bot.config import BotConfig, get_logs_dir

# User agents pool for realistic browser emulation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0"
]


class SteamGiftsClient:
    """Handles HTTP requests, session management, rate limiting, and HTML parsing."""

    def __init__(self, config: BotConfig):
        self.config = config
        self.base_url = "https://www.steamgifts.com"
        self.cookie = config.cookie
        self.min_request_interval = config.min_request_interval
        self.last_request_time: float = 0.0

        # Session with retry adapter
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            read=3,
            connect=3,
            backoff_factor=0.3,
            status_forcelist=(500, 502, 504)
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def get_headers(self) -> Dict[str, str]:
        """Generate browser headers with per-request User-Agent rotation."""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://www.steamgifts.com/",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache"
        }

    def respect_rate_limit(self) -> None:
        """Ensure minimum delay between requests."""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def get_soup(self, url: str) -> BeautifulSoup:
        """Fetch a page and parse with html.parser."""
        self.respect_rate_limit()
        headers = self.get_headers()
        try:
            r = self.session.get(url, cookies=self.cookie, headers=headers, timeout=30)
            self.last_request_time = time.time()
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
        except requests.exceptions.RequestException as e:
            logging.error(f"Error getting page {url}: {str(e)}")
            raise

    def fetch_user_info(self) -> Tuple[str, int]:
        """
        Fetch homepage and extract xsrf_token and current points.
        On failure, saves error_page.html and raises RuntimeError.
        """
        soup = self.get_soup(self.base_url)
        try:
            xsrf_input = soup.find("input", {"name": "xsrf_token"})
            points_span = soup.find("span", {"class": "nav__points"})
            if not xsrf_input or not points_span:
                raise ValueError("XSRF token or points element not found in DOM.")
            
            xsrf_token = xsrf_input["value"]
            points = int(points_span.text)
            return xsrf_token, points
        except (TypeError, AttributeError, ValueError) as e:
            logging.error(f"Cookie might be invalid or page structure changed. Error: {e}")
            if soup:
                error_page_path = os.path.join(get_logs_dir(), "error_page.html")
                try:
                    with open(error_page_path, "w", encoding="utf-8") as f:
                        f.write(soup.prettify())
                    logging.warning(f"Saved error page HTML to {error_page_path}")
                except Exception as save_err:
                    logging.error(f"Failed to save error page HTML: {save_err}")
            raise RuntimeError("Cookie invalid or failed to parse user info.") from e
        finally:
            if soup:
                soup.decompose()

    def post_entry(self, game_id: str, xsrf_token: str) -> requests.Response:
        """Submit giveaway entry via AJAX endpoint."""
        entry_url = f"{self.base_url}/ajax.php"
        data = {
            "xsrf_token": xsrf_token,
            "do": "entry_insert",
            "code": game_id
        }
        self.respect_rate_limit()
        headers = self.get_headers()
        response = self.session.post(
            entry_url,
            data=data,
            cookies=self.cookie,
            headers=headers,
            timeout=30
        )
        self.last_request_time = time.time()
        return response

    def health_check(self) -> bool:
        """Perform lightweight health check."""
        try:
            self.respect_rate_limit()
            headers = self.get_headers()
            r = self.session.get(f"{self.base_url}/", cookies=self.cookie, headers=headers, timeout=10)
            self.last_request_time = time.time()
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            points_span = soup.find("span", {"class": "nav__points"})
            is_ok = bool(points_span and points_span.text.isdigit())
            soup.decompose()
            return is_ok
        except Exception as e:
            logging.warning(f"Health check failed: {e}")
            return False
