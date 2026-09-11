#!/usr/bin/env python3
"""Download + extract all Reverend Insanity chapters from Novel Phoenix.

Resumable: a chapter whose markdown already exists and is non-empty is skipped,
so a crash/rerun costs nothing. Raw HTML is kept in raw/ during the run (needed
for re-parsing) and deleted by the caller once verification passes.

Usage: python3 scripts/fetch_chapters.py [--threads N] [--limit N] [--start N] [--end N]
"""
import argparse
import json
import os
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ri_parse import parse_document, to_markdown  # noqa: E402
from volumes import folder_name, volume_of  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "raw")
OUT = os.path.join(ROOT, "chapters")
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 (personal offline-reading backup; tylervovan)"
)
DELAY = 0.5          # seconds between requests per worker
TIMEOUT = 45
RETRIES = 4

_lock = threading.Lock()
stats = {"ok": 0, "skip": 0, "fail": 0, "words": 0}
failures = []
_started = time.time()


def slug(text, n):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:60]
    return f"{n:04d}-{s}.md" if s else f"{n:04d}.md"


def fetch(url):
    last = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept-Language": "en-US,en;q=0.9"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read().decode("utf-8", "replace"), r.status
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (429, 503):
                time.sleep(8 * (attempt + 1) + random.random() * 3)
                continue
            if e.code in (404, 410):
                break
            time.sleep(2 * (attempt + 1))
        except Exception as e:                       # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
            time.sleep(2 * (attempt + 1) + random.random())
    return None, last


_existing = set()


def volume_dir(n):
    vol, _lo, _hi, title = volume_of(n)
    d = os.path.join(OUT, folder_name(vol, title))
    os.makedirs(d, exist_ok=True)
    return d


def existing_md(n):
    return f"{n:04d}" if n in _existing else None


def load_existing():
    """One walk instead of per-chapter scans (2334 chapters would be O(n^2))."""
    for dirpath, _dirs, files in os.walk(OUT):
        for f in files:
            m = re.match(r"^(\d{4})-", f)
            if m and os.path.getsize(os.path.join(dirpath, f)) > 500:
                _existing.add(int(m.group(1)))
    print(f"already downloaded: {len(_existing)}", flush=True)


def do_chapter(entry):
    n = entry["num"]
    raw_path = os.path.join(RAW, f"{n:04d}.html")
    md_path = existing_md(n)
    if md_path:
        with _lock:
            stats["skip"] += 1
        return n, "skip", None

    doc = None
    if os.path.exists(raw_path) and os.path.getsize(raw_path) > 2000:
        with open(raw_path, encoding="utf-8") as f:
            doc = f.read()
    if doc is None:
        doc, status = fetch(entry["url"])
        time.sleep(DELAY + random.random() * 0.3)
        if doc is None:
            with _lock:
                stats["fail"] += 1
                failures.append({"num": n, "error": str(status)})
            return n, "fail", status
        tmp = raw_path + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(doc)
        os.replace(tmp, raw_path)

    title, blocks = parse_document(doc, n)
    words = sum(len(b.split()) for b in blocks)
    if words < 100:
        with _lock:
            stats["fail"] += 1
            failures.append({"num": n, "error": f"only {words} words extracted"})
        return n, "fail", f"thin ({words} words)"

    md = to_markdown(n, title, blocks, entry["url"], time.strftime("%Y-%m-%d"))
    path = os.path.join(volume_dir(n), slug(title, n))
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    with _lock:
        stats["ok"] += 1
        stats["words"] += words
    return n, "ok", words


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=3)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=10**9)
    args = ap.parse_args()

    os.makedirs(RAW, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    manifest = json.load(open(os.path.join(ROOT, "manifest.json"), encoding="utf-8"))
    todo = [e for e in manifest if args.start <= e["num"] <= args.end]
    if args.limit:
        todo = todo[: args.limit]
    print(f"chapters to consider: {len(todo)}  threads={args.threads}", flush=True)
    load_existing()

    done = 0
    with ThreadPoolExecutor(max_workers=args.threads) as ex:
        futs = {ex.submit(do_chapter, e): e for e in todo}
        for fut in as_completed(futs):
            n, status, info = fut.result()
            done += 1
            if done % 25 == 0 or done == len(todo):
                el = time.time() - _started
                print(f"[{done}/{len(todo)}] n={n} {status} {info if status!='ok' else ''} "
                      f"| ok={stats['ok']} skip={stats['skip']} fail={stats['fail']} "
                      f"| {el/60:.1f} min elapsed, {done/max(el,1):.2f} ch/s", flush=True)

    print("\nDONE:", json.dumps(stats), flush=True)
    if failures:
        with open(os.path.join(ROOT, "failures.json"), "w", encoding="utf-8") as f:
            json.dump(failures, f, indent=1)
        print(f"failures: {len(failures)} -> failures.json", flush=True)
        for x in failures[:15]:
            print("  ", x, flush=True)


if __name__ == "__main__":
    main()
