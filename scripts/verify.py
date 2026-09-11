#!/usr/bin/env python3
"""Verify the local backup against the manifest and (optionally) the live site.

  1. every manifest chapter has a non-empty markdown file
  2. no missing/duplicate numbers, no holes in min..max
  3. word counts sane (no truncated or zero-word chapters)
  4. spot-check N random chapters: refetch from the live site, re-parse, compare
     word counts and the first/last 60 characters

Exit 0 only if every check passes. With --offline, skips the live spot-check (useful
when the site is down and you only want local integrity).
"""
import argparse
import json
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import fetch_url, site_status  # noqa: E402
from novel_config import load_config, load_manifest  # noqa: E402
from ri_parse import parse_document        # noqa: E402


def load_local(cfg):
    got = {}
    for dirpath, _dirs, files in os.walk(cfg.chapters_dir):
        for f in sorted(files):
            m = re.match(r"^(\d+)-(.*)\.md$", f)
            if not m:
                continue
            n = int(m.group(1))
            text = open(os.path.join(dirpath, f), encoding="utf-8").read()
            body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
            body = re.sub(r"^#\s+Chapter.*$", "", body, count=1, flags=re.M).strip()
            paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
            got[n] = {"file": os.path.relpath(os.path.join(dirpath, f), cfg.root),
                      "paras": paras, "words": sum(len(p.split()) for p in paras)}
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", nargs="?", type=int, default=5, help="chapters to spot-check")
    ap.add_argument("--offline", action="store_true", help="skip the live spot-check")
    ap.add_argument("--thin", type=int, default=300, help="word floor for a chapter")
    args = ap.parse_args()

    cfg = load_config()
    manifest, manifest_source = load_manifest(cfg)
    src = cfg.source(manifest_source)
    want = [e["num"] for e in manifest]
    local = load_local(cfg)
    problems = []

    missing = [n for n in want if n not in local]
    extra = [n for n in local if n not in want]
    counts = {}
    for dirpath, _dirs, files in os.walk(cfg.chapters_dir):
        for f in files:
            if f.endswith(".md"):
                counts[int(f.split("-")[0])] = counts.get(int(f.split("-")[0]), 0) + 1
    dupes = sorted(n for n, c in counts.items() if c > 1)
    thin = sorted(n for n, c in local.items() if c["words"] < args.thin)
    words = sum(c["words"] for c in local.values())
    wc = sorted(c["words"] for c in local.values()) or [0]

    print(f"novel             : {cfg.title} ({cfg.slug})")
    print(f"manifest chapters : {len(want)}  ({min(want)}..{max(want)})")
    print(f"local chapters    : {len(local)}")
    print(f"missing           : {len(missing)} {missing[:10]}")
    print(f"extra (not in manifest): {len(extra)} {extra[:10]}")
    print(f"duplicate files   : {len(dupes)} {dupes[:10]}")
    print(f"thin (<{args.thin} words): {len(thin)} {thin[:10]}")
    print(f"total words       : {words:,}  (~{words/1e6:.2f}M)")
    print(f"words/chapter     : min {wc[0]}  median {wc[len(wc)//2]}  max {wc[-1]}")
    for label, bad in (("missing", missing), ("extra", extra), ("dupes", dupes),
                       ("thin", thin)):
        if bad:
            problems.append(f"{label}: {bad[:10]}")

    if args.offline:
        print("\nlive spot-check skipped (--offline)")
    else:
        ok, detail = site_status(src.novel_url())
        if not ok:
            print(f"\nlive site unreachable ({detail}) — spot-check skipped")
            problems.append(f"live site unreachable: {detail}")
        else:
            sample = sorted(random.sample(sorted(local), min(args.n, len(local))))
            print(f"\nspot-checking {sample} against {src.name} ({detail})")
            for n in sample:
                try:
                    doc = fetch_url(src.chapter_url(n))
                except Exception as e:                                # noqa: BLE001
                    print(f"  ch{n}: FETCH FAILED {e}")
                    problems.append(f"spot-check fetch failed ch{n}")
                    continue
                _, live = parse_document(doc, n, src.profile)
                lw = sum(len(p.split()) for p in live)
                loc = local[n]["words"]
                same_first = (live[0][:60] == local[n]["paras"][0][:60]) if live else False
                same_last = (live[-1][-60:] == local[n]["paras"][-1][-60:]) if live else False
                drift = abs(lw - loc) / max(lw, 1)
                status = "OK" if (same_first and same_last and drift < 0.02) else "MISMATCH"
                print(f"  ch{n}: {status} live={lw}w local={loc}w drift={drift:.2%} "
                      f"first={same_first} last={same_last}")
                if status != "OK":
                    problems.append(f"spot-check mismatch ch{n}")

    print("\n" + "=" * 60)
    if problems:
        print(f"VERIFY FAILED — {len(problems)} problem(s):")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print(f"VERIFY PASSED — {len(local)} chapters, {words:,} words")


if __name__ == "__main__":
    main()
