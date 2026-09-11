#!/usr/bin/env python3
"""Shared HTTP + text helpers for the novelphoenix backup pipeline."""
import html as _html
import json
import random
import re
import time
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36 (personal offline-reading backup; tylervovan)")

TIMEOUT = 45
RETRIES = 4


def fetch_url(url, ua=UA, timeout=TIMEOUT, retries=RETRIES, polite_delay=0.0):
    """GET a URL with retries. Raises on final failure."""
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode("utf-8", "replace")
                if polite_delay:
                    time.sleep(polite_delay + random.random() * 0.3)
                return body
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 503):
                time.sleep(8 * (attempt + 1) + random.random() * 3)
                continue
            if e.code in (404, 410):
                break
            time.sleep(2 * (attempt + 1))
        except Exception as e:                                        # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1) + random.random())
    raise RuntimeError(f"GET {url} failed after {retries} attempts: {last}")


def site_status(url):
    """Return (ok, detail) for an availability probe — never raises."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            return True, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:                                            # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def clean_text(s):
    """Strip tags/entities from a fragment of HTML."""
    s = re.sub(r"<[^>]+>", " ", s or "")
    for a, b in (("&amp;", "&"), ("&#39;", "'"), ("&quot;", '"'), ("&nbsp;", " "),
                 ("&mdash;", "\u2014"), ("&hellip;", "\u2026"), ("&lt;", "<"),
                 ("&gt;", ">"), ("&#8217;", "\u2019")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", _html.unescape(s)).strip()


def write_json_atomic(path, obj):
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    import os
    os.replace(tmp, path)
