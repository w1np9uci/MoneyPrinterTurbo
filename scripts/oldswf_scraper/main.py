#!/usr/bin/env python3
"""
OldSWF Scraper CLI
Extracts and downloads SWF files from oldswf.com game pages.
"""

import argparse
import csv
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from tqdm import tqdm


class OldSWFScraper:
    """Scraper for oldswf.com SWF files."""

    BASE_URL = "https://oldswf.com"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def __init__(
        self,
        output_dir: str = "./swf_downloads",
        use_playwright: bool = False,
        concurrency: int = 4,
        delay_ms: int = 0,
        retries: int = 3,
        timeout: int = 30,
    ):
        self.output_dir = Path(output_dir)
        self.use_playwright = use_playwright
        self.concurrency = concurrency
        self.delay_ms = delay_ms
        self.retries = retries
        self.timeout = timeout
        self.csv_path = self.output_dir / "downloads.csv"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})

        self.output_dir.mkdir(parents=True, exist_ok=True)

        if use_playwright:
            try:
                from playwright.sync_api import sync_playwright

                self.sync_playwright = sync_playwright
            except ImportError:
                print(
                    "ERROR: Playwright is not installed. "
                    "Please install it with: pip install playwright && python -m playwright install chromium"
                )
                sys.exit(1)

    def normalize_game_url(self, game_input: str) -> Tuple[str, str]:
        """
        Normalize game input to URL and ID.
        Returns (page_url, game_id).
        """
        if game_input.startswith("http://") or game_input.startswith("https://"):
            page_url = game_input
            match = re.search(r"/game/(\d+)", page_url)
            if match:
                game_id = match.group(1)
            else:
                game_id = "unknown"
        else:
            game_id = game_input
            page_url = f"{self.BASE_URL}/game/{game_id}"

        return page_url, game_id

    def extract_swf_static(self, page_url: str) -> Optional[Tuple[str, str]]:
        """
        Extract SWF URL from page HTML using static parsing.
        Returns (swf_url, title) or None.
        """
        try:
            headers = {
                "User-Agent": self.USER_AGENT,
                "Referer": self.BASE_URL,
            }
            response = self.session.get(
                page_url, headers=headers, timeout=self.timeout
            )
            response.raise_for_status()

            html = response.text
            title_match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else "Unknown"

            swf_patterns = [
                r'loadSwf\(["\']([^"\']+\.swf[^"\']*)["\']',
                r'file:\s*["\']([^"\']+\.swf[^"\']*)["\']',
                r'src=["\']([^"\']+\.swf[^"\']*)["\']',
                r'data=["\']([^"\']+\.swf[^"\']*)["\']',
                r'["\']([^"\']*\/data\/swf\/[^"\']+\.swf[^"\']*)["\']',
            ]

            for pattern in swf_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    swf_path = match.group(1)
                    swf_url = urljoin(page_url, swf_path)
                    return swf_url, title

            return None

        except Exception as e:
            print(f"Error extracting SWF from {page_url}: {e}")
            return None

    def extract_swf_playwright(self, page_url: str) -> Optional[Tuple[str, str]]:
        """
        Extract SWF URL using Playwright by capturing network requests.
        Returns (swf_url, title) or None.
        """
        try:
            swf_urls = []

            with self.sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                def handle_request(request):
                    url = request.url
                    if url.lower().endswith(".swf") or ".swf?" in url.lower():
                        swf_urls.append(url)

                page.on("request", handle_request)
                page.goto(page_url, wait_until="networkidle", timeout=self.timeout * 1000)
                time.sleep(2)

                title = page.title()
                browser.close()

            if swf_urls:
                return swf_urls[0], title
            return None

        except Exception as e:
            print(f"Error extracting SWF with Playwright from {page_url}: {e}")
            return None

    def download_swf(
        self, swf_url: str, game_id: str, page_url: str
    ) -> Optional[Path]:
        """
        Download SWF file with retry logic.
        Returns local file path or None on failure.
        """
        parsed = urlparse(swf_url)
        filename = os.path.basename(parsed.path)
        filename = re.sub(r"\?.*$", "", filename)

        if not filename or not filename.endswith(".swf"):
            filename = f"game_{game_id}.swf"

        local_path = self.output_dir / filename

        headers = {
            "User-Agent": self.USER_AGENT,
            "Referer": page_url,
        }

        for attempt in range(self.retries):
            try:
                response = self.session.get(
                    swf_url, headers=headers, timeout=self.timeout, stream=True
                )
                response.raise_for_status()

                total_size = int(response.headers.get("content-length", 0))
                with open(local_path, "wb") as f:
                    if total_size:
                        with tqdm(
                            total=total_size,
                            unit="B",
                            unit_scale=True,
                            desc=filename,
                            leave=False,
                        ) as pbar:
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                                    pbar.update(len(chunk))
                    else:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)

                return local_path

            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
            ) as e:
                if attempt < self.retries - 1:
                    wait_time = 2 ** attempt
                    print(
                        f"Download failed (attempt {attempt + 1}/{self.retries}), "
                        f"retrying in {wait_time}s: {e}"
                    )
                    time.sleep(wait_time)
                else:
                    print(f"Download failed after {self.retries} attempts: {e}")
                    return None

            except requests.exceptions.HTTPError as e:
                if e.response.status_code in [429, 500, 502, 503, 504]:
                    if attempt < self.retries - 1:
                        wait_time = 2 ** attempt
                        print(
                            f"HTTP error {e.response.status_code} "
                            f"(attempt {attempt + 1}/{self.retries}), "
                            f"retrying in {wait_time}s"
                        )
                        time.sleep(wait_time)
                    else:
                        print(f"Download failed after {self.retries} attempts: {e}")
                        return None
                else:
                    print(f"HTTP error: {e}")
                    return None

            except Exception as e:
                print(f"Download error: {e}")
                return None

        return None

    def write_csv_row(
        self,
        game_id: str,
        title: str,
        page_url: str,
        swf_url: str,
        local_path: Optional[Path],
        status: str,
    ):
        """Write a row to the CSV index file."""
        file_exists = self.csv_path.exists()

        with open(self.csv_path, "a", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            if not file_exists:
                writer.writerow(
                    ["game_id", "title", "page_url", "swf_url", "local_path", "status"]
                )

            writer.writerow(
                [
                    game_id,
                    title,
                    page_url,
                    swf_url,
                    str(local_path) if local_path else "",
                    status,
                ]
            )

    def process_game(self, game_input: str) -> bool:
        """
        Process a single game: extract and download SWF.
        Returns True if successful.
        """
        page_url, game_id = self.normalize_game_url(game_input)
        print(f"\nProcessing game {game_id}: {page_url}")

        result = self.extract_swf_static(page_url)

        if not result and self.use_playwright:
            print("Static extraction failed, trying Playwright fallback...")
            result = self.extract_swf_playwright(page_url)

        if not result:
            print(f"Failed to find SWF for game {game_id}")
            self.write_csv_row(
                game_id, "Unknown", page_url, "", None, "SWF not found"
            )
            return False

        swf_url, title = result
        print(f"Found SWF: {swf_url}")
        print(f"Title: {title}")

        if self.delay_ms > 0:
            time.sleep(self.delay_ms / 1000.0)

        local_path = self.download_swf(swf_url, game_id, page_url)

        if local_path:
            print(f"Downloaded to: {local_path}")
            self.write_csv_row(
                game_id, title, page_url, swf_url, local_path, "success"
            )
            return True
        else:
            print(f"Failed to download SWF for game {game_id}")
            self.write_csv_row(
                game_id, title, page_url, swf_url, None, "download failed"
            )
            return False

    def process_batch(self, game_inputs: List[str]):
        """Process multiple games with concurrency control."""
        if self.concurrency == 1:
            for game_input in game_inputs:
                self.process_game(game_input)
        else:
            with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
                futures = {
                    executor.submit(self.process_game, game_input): game_input
                    for game_input in game_inputs
                }

                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        game_input = futures[future]
                        print(f"Error processing {game_input}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract and download SWF files from oldswf.com",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://oldswf.com/game/18037
  %(prog)s 18037 12345 67890
  %(prog)s --use-playwright 18037
  %(prog)s --from-file urls.txt --out-dir swf_downloads --concurrency 8
        """,
    )

    parser.add_argument(
        "games",
        nargs="*",
        help="Game page URLs or IDs",
    )

    parser.add_argument(
        "--from-file",
        type=str,
        help="Read game URLs/IDs from a file (one per line)",
    )

    parser.add_argument(
        "--out-dir",
        type=str,
        default="./swf_downloads",
        help="Output directory for downloaded SWF files (default: ./swf_downloads)",
    )

    parser.add_argument(
        "--use-playwright",
        action="store_true",
        help="Enable Playwright fallback for dynamic content extraction",
    )

    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Number of concurrent downloads (default: 4)",
    )

    parser.add_argument(
        "--delay-ms",
        type=int,
        default=0,
        help="Delay in milliseconds between requests (default: 0)",
    )

    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Number of retry attempts for failed downloads (default: 3)",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Request timeout in seconds (default: 30)",
    )

    args = parser.parse_args()

    game_inputs = list(args.games) if args.games else []

    if args.from_file:
        try:
            with open(args.from_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        game_inputs.append(line)
        except Exception as e:
            print(f"Error reading file {args.from_file}: {e}")
            sys.exit(1)

    if not game_inputs:
        parser.print_help()
        print("\nError: No game URLs or IDs provided")
        sys.exit(1)

    scraper = OldSWFScraper(
        output_dir=args.out_dir,
        use_playwright=args.use_playwright,
        concurrency=args.concurrency,
        delay_ms=args.delay_ms,
        retries=args.retries,
        timeout=args.timeout,
    )

    print(f"Starting scraper with {len(game_inputs)} game(s)...")
    print(f"Output directory: {scraper.output_dir.absolute()}")
    print(f"Concurrency: {args.concurrency}")
    print(f"Playwright fallback: {'enabled' if args.use_playwright else 'disabled'}")

    scraper.process_batch(game_inputs)

    print(f"\nDone! Results saved to: {scraper.csv_path}")


if __name__ == "__main__":
    main()
