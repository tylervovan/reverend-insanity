#!/usr/bin/env python3
"""Download + extract every chapter of the configured novel. Resumable.

A chapter whose markdown already exists and is non-empty is skipped, so re-running
after an interruption (or a site outage) only fetches what's missing. Raw HTML is
kept in raw/ during the run for re-parsing and can be deleted by the caller after
verification.

Usage: python3 scripts/fetch_chapters.py [--threads N] [--limit N] [--start N] [--end N]
"""
import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import UA, fetch_url            # noqa: E402
from novel_config import load_config, load_manifest  # noqa: E402
from ri_parse import parse_document, to_markdown  # noqa: E402

DELAY = 0.5
_lock = threading.Lock()
stats = {"ok": 0, "skip": 0, "fail": 0, "words": 0}
failures = []
_started = time.time()
_existing = set()
CFG = None
PROFILE = "auto"


def slugify(text, n):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:60]
    return f"{n:04d}-{s}.md" if s else f"{n:04d}.md"


def load_existing():
    for dirpath, _dirs, files in os.walk(CFG.chapters_dir):
        for f in files:
            m = re.match(r"^(\d+)-", f)
            if m and os.path.getsize(os.path.join(dirpath, f)) > 500:
                _existing.add(int(m.group(1)))
    return len(_existing)


def do_chapter(entry):
    n = entry["num"]
    if n in _existing:
        with _lock:
            stats["skip"] += 1
        return n, "skip", None

    raw_path = os.path.join(CFG.raw_dir, f"{n:04d}.html")
    doc = None
    if os.path.exists(raw_path) and os.path.getsize(raw_path) > 2000:
        with open(raw_path, encoding="utf-8") as f:
            doc = f.read()
    if doc is None:
        try:
            doc = fetch_url(entry["url"], ua=UA, polite_delay=DELAY)
        except Exception as e:                                        # noqa: BLE001
            with _lock:
                stats["fail"] += 1
                failures.append({"num": n, "error": str(e)[:200]})
            return n, "fail", str(e)[:120]
        tmp = raw_path + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(doc)
        os.replace(tmp, raw_path)

    title, blocks = parse_document(doc, n, PROFILE)
    words = sum(len(b.split()) for b in blocks)
    if words < 100:
        with _lock:
            stats["fail"] += 1
            failures.append({"num": n, "error": f"only {words} words extracted"})
        return n, "fail", f"thin ({words} words)"

    md = to_markdown(n, title, blocks, entry["url"], time.strftime("%Y-%m-%d"))
    path = os.path.join(CFG.volume_dir(n), slugify(title, n))
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    with _lock:
        stats["ok"] += 1
        stats["words"] += words
    return n, "ok", words


def main():
    global CFG, PROFILE
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=3)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--start", type=int)
    ap.add_argument("--end", type=int)
    ap.add_argument("--source", help="mirror name (default: whatever manifest.json used)")
    args = ap.parse_args()

    CFG = load_config()
    os.makedirs(CFG.raw_dir, exist_ok=True)
    os.makedirs(CFG.chapters_dir, exist_ok=True)

    if not os.path.exists(CFG.manifest_path):
        raise SystemExit(f"no manifest at {CFG.manifest_path} — run fetch_manifest.py first")
    manifest, manifest_source = load_manifest(CFG)
    if not manifest:
        raise SystemExit("manifest is empty — re-run fetch_manifest.py")
    src = CFG.source(args.source or manifest_source)
    profile = src.profile
    PROFILE = profile
    print(f"{CFG.title}: source={src.name} profile={profile}", flush=True)

    todo = manifest
    if args.start is not None:
        todo = [e for e in todo if e["num"] >= args.start]
    if args.end is not None:
        todo = [e for e in todo if e["num"] <= args.end]
    if args.limit:
        todo = todo[: args.limit]

    print(f"{CFG.title}: {len(todo)} chapters to consider, threads={args.threads}",
          flush=True)
    print(f"already downloaded: {load_existing()}", flush=True)

    done = 0
    with ThreadPoolExecutor(max_workers=args.threads) as ex:
        futs = {ex.submit(do_chapter, e): e for e in todo}
        for fut in as_completed(futs):
            n, status, info = fut.result()
            done += 1
            if done % 50 == 0 or done == len(todo):
                el = time.time() - _started
                extra = "" if status == "ok" else f" {info}"
                print(f"[{done}/{len(todo)}] n={n} {status}{extra} | ok={stats['ok']} "
                      f"skip={stats['skip']} fail={stats['fail']} | {el/60:.1f} min, "
                      f"{done/max(el,1):.2f} ch/s", flush=True)

    print("\nDONE:", json.dumps(stats), flush=True)
    if failures:
        with open(os.path.join(CFG.root, "failures.json"), "w", encoding="utf-8") as f:
            json.dump(failures, f, indent=1)
        print(f"failures: {len(failures)} -> failures.json", flush=True)
        for x in failures[:10]:
            print("  ", x, flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
