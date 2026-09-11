#!/usr/bin/env python3
"""Fetch the chapter manifest for the configured novel, into manifest.json.

The manifest (source, number, title, URL) is the source of truth for "did we get
everything". Chapter URLs are sequential, so validation is just: the numbers seen
cover min..max with no holes.

  python3 scripts/fetch_manifest.py [--source NAME]

With several mirrors configured, `--source` picks one; the orchestrator passes the
first one that actually responds. The chosen source is recorded in manifest.json so
the downloader and verifier keep using the same site.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import UA, clean_text, fetch_url, write_json_atomic  # noqa: E402
from novel_config import load_config  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="mirror name to scrape (default: first configured)")
    args = ap.parse_args()

    cfg = load_config()
    src = cfg.source(args.source)
    entry = src.chapter_regex()
    print(f"{cfg.title}: scraping {src.name} index at {src.novel_url()}/chapters",
          file=sys.stderr)

    seen, page = {}, 1
    while page <= 400:
        try:
            html = fetch_url(src.index_url(page), ua=UA)
        except Exception as e:                                        # noqa: BLE001
            print(f"page {page} failed: {e}", file=sys.stderr)
            if page == 1:
                raise SystemExit(f"could not reach {src.index_url(1)} — source down?")
            break
        hits = entry.findall(html)
        if not hits:
            break
        new = 0
        for num, raw in hits:
            n = int(num)
            if n not in seen:
                seen[n] = clean_text(raw)
                new += 1
        print(f"  page {page}: {len(hits)} links, {new} new", file=sys.stderr)
        if new == 0:
            break
        page += 1

    if not seen:
        raise SystemExit(f"{src.name}: no chapters found at {src.index_url(1)}")

    chapters = [{"num": n, "title": seen[n], "url": src.chapter_url(n)} for n in sorted(seen)]
    write_json_atomic(cfg.manifest_path, {
        "source": src.name,
        "base": src.base,
        "profile": src.profile,
        "fetched": time.strftime("%Y-%m-%d %H:%M"),
        "chapters": chapters,
    })

    nums = sorted(seen)
    holes = [n for n in range(nums[0], nums[-1] + 1) if n not in seen]
    print(f"\n{cfg.title} via {src.name}: {len(nums)} chapters, {nums[0]}..{nums[-1]}")
    print(f"holes in sequence: {len(holes)} {holes[:20]}")
    if holes:
        print("NOTE: holes are real — re-run to fill them (often page-load hiccups)")
    print(f"wrote {cfg.manifest_path}")


if __name__ == "__main__":
    main()
