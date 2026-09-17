from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from open_product import (
    ROBOTS_TXT_URL,
    fetch_products,
    is_allowed,
    load_robots,
    select_urls_to_fetch,
)

LIMIT = 15

CATEGORY_URL = "https://www.trendyol.com/kadin-mont-x-g1-c118"

# Product cards of the category listing. "seller-store-product-card" (a store's
# ad showcase with unrelated products) is intentionally not matched.
PRODUCT_CARD_SELECTOR = "a.product-card"


def collect_product_links(driver, category_url):
    driver.get(category_url)

    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, PRODUCT_CARD_SELECTOR))
    )

    elements = driver.find_elements(By.CSS_SELECTOR, PRODUCT_CARD_SELECTOR)
    links = []
    for el in elements:
        href = el.get_attribute("href")
        if href:
            links.append(href)
    return links


def clean_links(links):
    cleaned = []
    for link in links:
        link = link.split("?")[0]
        cleaned.append(link)

    return list(dict.fromkeys(cleaned))


def main():
    rp = load_robots(ROBOTS_TXT_URL)
    if rp is None:
        print("Could not load robots.txt, nothing will be crawled.")
        return
    if not is_allowed(rp, CATEGORY_URL):
        print(f"Access to {CATEGORY_URL} is disallowed by robots.txt")
        return

    driver = webdriver.Chrome()
    try:
        links = collect_product_links(driver, CATEGORY_URL)
        links = clean_links(links)
        print(f"Found {len(links)} product links.")

        pending = select_urls_to_fetch(rp, links)[:LIMIT]
        print(f"{len(pending)} new products will be downloaded.")
        fetch_products(driver, pending)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
