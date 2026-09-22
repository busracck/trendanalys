
import random
import time

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from scraper.robots import is_allowed

# İstekler arası nazik bekleme (saniye). Siteye yük bindirmemek için düşürülmez.
MIN_DELAY = 4
MAX_DELAY = 8

# Sayfanın yüklenmesi için beklenecek en uzun süre (saniye)
PAGE_TIMEOUT = 15

# Chrome'un bir sayfayı yüklemek için harcayabileceği en uzun süre (saniye)
PAGE_LOAD_TIMEOUT = 60


def create_driver():
    # Selenium 4 sürücüyü kendisi indirir; headless kullanmıyoruz, engel sayfası geliyor.
    driver = webdriver.Chrome()
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    return driver


def restart_driver(driver):
    """Takılan tarayıcıyı kapatıp yenisini açar."""
    try:
        driver.quit()
    except Exception:  # noqa: BLE001 - zaten çökmüş tarayıcıdan gelen her hata yutulur
        pass
    print("Tarayıcı yeniden başlatılıyor...")
    return create_driver()


def polite_sleep():
    delay = random.uniform(MIN_DELAY, MAX_DELAY)
    print(f"{delay:.1f} sn bekleniyor...")
    time.sleep(delay)


def fetch_page(driver, url):
    """Sayfanın HTML'ini döndürür. İzin yoksa hata verir, sayfa gelmezse None döner."""
    if not is_allowed(url):
        raise ValueError(f"robots.txt bu adrese izin vermiyor: {url}")

    # Ağa çıkan her istek burada bekler: kural atlanamaz.
    polite_sleep()
    driver.get(url)
    try:
        WebDriverWait(driver, PAGE_TIMEOUT).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )
    except TimeoutException:
        # h1 gelmediyse sayfa engel/captcha sayfası olabilir: atlatmaya çalışmıyoruz.
        print(f"Sayfa {PAGE_TIMEOUT} sn içinde yüklenmedi, durduruluyor: {url}")
        return None

    return driver.page_source
