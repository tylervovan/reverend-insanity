#!/usr/bin/env python3
"""Verify the local backup against the manifest and the live site.

Checks:
  1. every manifest chapter has a non-empty markdown file
  2. no duplicate or missing numbers, no holes in 1..max
  3. word counts sane (no truncated chapters, no zero-word files)
  4. spot-check N random chapters: refetch from the live site, re-parse,
     compare word counts and the first/last 60 chars of text
Exit code 0 only if everything passes.
"""
import json
import os
import random
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CH = os.path.join(ROOT, "chapters")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from ri_parse import parse_document  # noqa: E402

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36 (verification)"


def load_local():
    got = {}
    for dirpath, _dirs, files in os.walk(CH):
        for f in sorted(files):
            m = re.match(r"^(\d{4})-(.*)\.md$", f)
            if not m:
                continue
            n = int(m.group(1))
            text = open(os.path.join(dirpath, f), encoding="utf-8").read()
            body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
            body = re.sub(r"^#\s+Chapter.*$", "", body, count=1, flags=re.M).strip()
            paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
            got[n] = {"file": os.path.relpath(os.path.join(dirpath, f), ROOT),
                      "paras": paras, "words": sum(len(p.split()) for p in paras),
                      "size": len(text)}
    return got


def all_chapter_files():
    out = []
    for dirpath, _dirs, files in os.walk(CH):
        out += [os.path.join(dirpath, f) for f in files if f.endswith(".md")]
    return out


def main():
    manifest = json.load(open(os.path.join(ROOT, "manifest.json"), encoding="utf-8"))
    want = [e["num"] for e in manifest]
    local = load_local()
    problems = []

    missing = [n for n in want if n not in local]
    extra = [n for n in local if n not in want]
    dupes = []
    seen_nums = {}
    for p in all_chapter_files():
        n = int(os.path.basename(p)[:4])
        seen_nums.setdefault(n, []).append(p)
    dupes = sorted(n for n, ps in seen_nums.items() if len(ps) > 1)
    thin = sorted(n for n, c in local.items() if c["words"] < 300)
    words = sum(c["words"] for c in local.values())
    wc = sorted(c["words"] for c in local.values())
    print(f"manifest chapters : {len(want)}  (range {min(want)}..{max(want)})")
    print(f"local chapters    : {len(local)}")
    print(f"missing           : {len(missing)} {missing[:10]}")
    print(f"extra (not in manifest): {len(extra)} {extra[:10]}")
    print(f"duplicate files   : {len(dupes)} {dupes[:10]}")
    print(f"thin (<300 words) : {len(thin)} {thin[:10]}")
    print(f"total words       : {words:,}  (~{words/1e6:.2f}M)")
    print(f"words/chapter     : min {wc[0]}  median {wc[len(wc)//2]}  max {wc[-1]}")
    for label, bad in (("missing", missing), ("extra", extra), ("dupes", dupes), ("thin", thin)):
        if bad:
            problems.append(f"{label}: {bad[:10]}")

    # spot-check against the live site
    sample = sorted(random.sample(sorted(local), min(int(sys.argv[1]) if len(sys.argv) > 1 else 5,
                                                  len(local))))
    print(f"\nspot-checking {sample} against live site")
    for n in sample:
        url = f"https://novelphoenix.com/novel/reverend-insanity/chapter-{n}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45) as r:
                doc = r.read().decode("utf-8", "replace")
        except Exception as e:                                   # noqa: BLE001
            print(f"  ch{n}: FETCH FAILED {e}")
            problems.append(f"spot-check fetch failed ch{n}")
            continue
        _, live_paras = parse_document(doc, n)
        live_w = sum(len(p.split()) for p in live_paras)
        loc_w = local[n]["words"]
        lf, ll = live_paras[0][:60] if live_paras else "", live_paras[-1][-60:] if live_paras else ""
        lof = local[n]["paras"][0][:60]
        lol = local[n]["paras"][-1][-60:]
        ok_first, ok_last = lf == lof, ll == lol
        drift = abs(live_w - loc_w) / max(live_w, 1)
        status = "OK" if (ok_first and ok_last and drift < 0.02) else "MISMATCH"
        print(f"  ch{n}: {status} live={live_w}w local={loc_w}w drift={drift:.2%} "
              f"first={ok_first} last={ok_last}")
        if status != "OK":
            problems.append(f"spot-check mismatch ch{n}: first={ok_first} last={ok_last} "
                            f"live={live_w} local={loc_w}")

    print("\n" + ("=" * 60))
    if problems:
        print(f"VERIFY FAILED — {len(problems)} problem(s):")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print(f"VERIFY PASSED — {len(local)} chapters, {words:,} words, "
          f"{len(sample)}/{len(sample)} spot-checks matched live")


if __name__ == "__main__":
    main()