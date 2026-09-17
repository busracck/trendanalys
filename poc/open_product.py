import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from protego import Protego
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PRODUCT_URLS = [
    "https://www.trendyol.com/bershka/kemerli-midi-elbise-p-1122588026",
    "https://www.trendyol.com/bianco-lucci/kadin-siyah-oversize-sisme-mont-10191065-p-69782438",
    "https://www.trendyol.com/dark-seer/beyaz-unisex-sneaker-p-42713792",
    "https://www.trendyol.com/framgan/unisex-erkek-kadin-leopar-ozel-baskili-oversize-pamuklu-bisiklet-yaka-t-shirt-p-946802869",
    "https://www.trendyol.com/embeauty/ultra-siyah-dolgunlastirici-maskara-hacim-ve-uzunluk-etkili-p-1016742922",
]

ROBOTS_TXT_URL = "https://www.trendyol.com/robots.txt"

OUTPUT_DIR = Path(__file__).parent / "output"

# Polite random delay between two requests, in seconds
MIN_DELAY = 4
MAX_DELAY = 8


def load_robots(robots_url):
    try:
        with urllib.request.urlopen(robots_url, timeout=15) as response:
            robots_txt = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"Error loading robots.txt: {e}")
        return None
    return Protego.parse(robots_txt)


def is_allowed(rp, url, user_agent="*"):
    return rp.can_fetch(url, user_agent)


def extract_product_id(url):
    # Trendyol product URLs end with "-p-<id>", e.g. ".../kemerli-midi-elbise-p-1122588026"
    match = re.search(r"-p-(\d+)", url)
    return match.group(1) if match else None


def select_urls_to_fetch(rp, urls):
    # Keep only URLs that have a product id, are allowed by robots.txt and are not saved yet
    pending = []
    for url in urls:
        product_id = extract_product_id(url)
        if product_id is None:
            print(f"No product id in URL, skipping: {url}")
            continue
        if not is_allowed(rp, url):
            print(f"[{product_id}] robots.txt does not allow this URL, skipping.")
            continue
        path = OUTPUT_DIR / f"{product_id}.html"
        if path.exists():
            print(f"[{product_id}] already saved, skipping.")
            continue
        pending.append((product_id, url, path))
    return pending


def fetch_page(driver, url):
    driver.get(url)
    # Wait until the product title (h1) appears; raises TimeoutException otherwise
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.TAG_NAME, "h1"))
    )
    print(f"Title: {driver.title}")
    print(f"Current URL: {driver.current_url}")
    return driver.page_source


def save_html(html, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    print(f"Saved {len(html)} characters to {path}")


def fetch_products(driver, pending):
    # Download each pending (product_id, url, path) with a polite delay in between
    for i, (product_id, url, path) in enumerate(pending):
        if i > 0:
            delay = random.uniform(MIN_DELAY, MAX_DELAY)
            print(f"Waiting {delay:.1f} s before the next request...")
            time.sleep(delay)

        print(f"[{product_id}] fetching...")
        try:
            html = fetch_page(driver, url)
        except TimeoutException:
            # No h1 usually means a block/captcha page: stop instead of retrying
            print(f"[{product_id}] h1 did not appear, possibly blocked. Stopping.")
            print(f"Title: {driver.title}")
            print(f"Current URL: {driver.current_url}")
            break
        save_html(html, path)


def main():
    rp = load_robots(ROBOTS_TXT_URL)
    if rp is None:
        print("Failed to load robots.txt, nothing will be fetched.")
        return

    pending = select_urls_to_fetch(rp, PRODUCT_URLS)
    if not pending:
        print("Nothing to fetch.")
        return

    # One browser for all products instead of starting Chrome for every URL
    driver = webdriver.Chrome(options=webdriver.ChromeOptions())
    try:
        fetch_products(driver, pending)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
