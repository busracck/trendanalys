"""robots.txt kontrolü. Hiçbir sayfa buradan geçmeden indirilmez."""

import urllib.request

from protego import Protego

ROBOTS_URL = "https://www.trendyol.com/robots.txt"
USER_AGENT = "*"

# robots.txt bir kez indirilir, sonra bellekten kullanılır
_robots = None


def _get_robots():
    global _robots
    if _robots is None:
        response = urllib.request.urlopen(ROBOTS_URL, timeout=15)
        text = response.read().decode("utf-8", "replace")
        _robots = Protego.parse(text)
    return _robots


def is_allowed(url: str) -> bool:
    # Dikkat: Protego'da sıra can_fetch(url, user_agent)
    return _get_robots().can_fetch(url, USER_AGENT)
