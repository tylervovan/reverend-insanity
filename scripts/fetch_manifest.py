#!/usr/bin/env python3
"""Fetch the chapter manifest for Reverend Insanity from Novel Phoenix.

Writes manifest.json: [{num, title, url}]. Since chapter URLs are strictly
sequential (/chapter-N), validation only needs to confirm the numbers shown on
each index page cover 1..max without holes.
"""
import json
import re
import sys
import urllib.request

BASE = "https://novelphoenix.com"
SLUG = "reverend-insanity"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 (personal-reading-backup; contact tylervovan)"

ENTRY = re.compile(
    r'href="(?:https://novelphoenix\.com)?/novel/'
    + SLUG
    + r'/chapter-(\d+)"[^>]*>(.*?)</a>',
    re.S,
)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def clean(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", '"')
    s = s.replace("&nbsp;", " ").replace("&mdash;", "\u2014")
    return re.sub(r"\s+", " ", s).strip()


def main():
    seen, order = {}, []
    page = 1
    while True:
        url = f"{BASE}/novel/{SLUG}/chapters?page={page}"
        try:
            html = get(url)
        except Exception as e:
            print(f"page {page} failed: {e}", file=sys.stderr)
            break
        hits = ENTRY.findall(html)
        if not hits:
            break
        new = 0
        for num, raw in hits:
            n = int(num)
            if n not in seen:
                seen[n] = clean(raw)
                order.append(n)
                new += 1
        print(f"page {page}: {len(hits)} links, {new} new", file=sys.stderr)
        if new == 0:
            break
        page += 1
        if page > 60:
            break

    out = []
    for n in sorted(seen):
        t = re.sub(r"^\s*Chapter\s+%d\s*[-:\u2013]?\s*" % n, "", seen[n]).strip()
        out.append({"num": n, "title": seen[n], "subtitle": t,
                    "url": f"{BASE}/novel/{SLUG}/chapter-{n}"})

    with open("manifest.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    nums = sorted(seen)
    print(f"\nchapters: {len(nums)}  min={nums[0]}  max={nums[-1]}")
    missing = [n for n in range(nums[0], nums[-1] + 1) if n not in seen]
    print(f"holes in sequence: {len(missing)} {missing[:20]}")
    print("sample:", json.dumps(out[:2], ensure_ascii=False)[:300])


if __name__ == "__main__":
    main()
