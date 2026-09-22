from selenium.webdriver.common.by import By

from scraper.driver import fetch_page

PRODUCT_CARD_SELECTOR = "a.product-card"

MAX_PAGES = 10


def collect_links_from_page(driver, url):
    html = fetch_page(driver, url)
    if html is None:
        return []

    cards = driver.find_elements(By.CSS_SELECTOR, PRODUCT_CARD_SELECTOR)
    links = [card.get_attribute("href").split("?")[0] for card in cards]

    return links


def collect_category_links(driver, category_url, target):
    links = []
    page = 1
    while len(links) < target and page <= MAX_PAGES:
        url = category_url if page == 1 else f"{category_url}?pi={page}"
        print(f"Sayfa {page} indiriliyor: {url}")
        page_links = collect_links_from_page(driver, url)
        if not page_links:
            break

        for link in page_links:
            if link not in links:
                links.append(link)
        print(f"  {len(page_links)} link bulundu, toplam {len(links)}")

        page += 1

    return links[:target]

