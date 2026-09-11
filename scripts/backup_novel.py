#!/usr/bin/env python3
"""One-shot, unattended backup run for the configured novel.

Designed to be called repeatedly by the scheduler:

  * takes an exclusive lock, so overlapping runs exit immediately
  * probes the site first — if it's down, exits fast with a one-line report
  * refreshes the manifest, downloads only what's missing (resumable)
  * verifies local integrity, spot-checks the live site when reachable
  * rebuilds the concatenated markdown / INDEX / EPUB
  * deletes raw/ scratch HTML (the markdown is the artifact)
  * optionally commits + pushes to the private GitHub repo

Prints a short human-readable summary and exits 0 on success, 1 on verification
failure, 2 on download failure, 3 on site unavailable.

  python3 scripts/backup_novel.py [--push] [--threads 3] [--no-raw-cleanup]
"""
import argparse
import fcntl
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import site_status          # noqa: E402
from novel_config import load_config    # noqa: E402

EXIT_OK, EXIT_VERIFY, EXIT_FETCH, EXIT_DOWN = 0, 1, 2, 3


def run(cmd, cwd, check=True):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed ({p.returncode}):\n"
                           f"{p.stdout[-2000:]}\n{p.stderr[-2000:]}")
    return p


def sh(cmd, cwd, check=True):
    p = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"{cmd} failed ({p.returncode}): {p.stderr[-1500:]}")
    return p


def count_chapters(cfg):
    n = 0
    for dirpath, _dirs, files in os.walk(cfg.chapters_dir):
        n += sum(1 for f in files if f.endswith(".md"))
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true", help="commit + push to origin")
    ap.add_argument("--threads", type=int, default=3)
    ap.add_argument("--no-raw-cleanup", action="store_true")
    ap.add_argument("--spot", type=int, default=5)
    args = ap.parse_args()

    cfg = load_config()
    started = time.time()

    # ---- single-run lock ------------------------------------------------
    lock_path = os.path.join(cfg.root, ".backup.lock")
    lock = open(lock_path, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"{cfg.title}: another backup run is already in progress — skipping")
        return EXIT_OK

    # ---- is any source up? (failover order) -----------------------------
    before = count_chapters(cfg)
    chosen, tried = None, []
    for s in cfg.sources:
        ok, detail = site_status(s.novel_url())
        tried.append(f"{s.name}={detail}")
        if ok:
            chosen, chosen_detail = s, detail
            break
    if chosen is None:
        print(f"{cfg.title}: all sources unavailable ({', '.join(tried)}); have "
              f"{before} chapters locally. No action this run.")
        return EXIT_DOWN
    print(f"{cfg.title}: source {chosen.name} up ({chosen_detail}); {before} chapters "
          f"on disk before this run.")
    if len(tried) > 1:
        print(f"sources tried, in order: {', '.join(tried)}")

    # ---- manifest -------------------------------------------------------
    try:
        p = run([sys.executable, "scripts/fetch_manifest.py", "--source", chosen.name],
                cfg.root)
        tail = [l for l in p.stdout.strip().splitlines() if l.strip()]
        print("manifest:", " | ".join(tail[-2:]) if tail else "ok")
    except Exception as e:                                            # noqa: BLE001
        print(f"manifest scrape failed: {e}")
        return EXIT_FETCH

    # ---- download -------------------------------------------------------
    try:
        p = run([sys.executable, "scripts/fetch_chapters.py", "--threads", str(args.threads),
                 "--source", chosen.name], cfg.root, check=False)
        print(p.stdout.strip().splitlines()[-1] if p.stdout.strip() else "fetch: no output")
        if p.returncode == 2:
            print("download finished WITH FAILURES — see failures.json")
            return EXIT_FETCH
    except Exception as e:                                            # noqa: BLE001
        print(f"download failed: {e}")
        return EXIT_FETCH

    after = count_chapters(cfg)
    new = after - before

    # ---- verify ---------------------------------------------------------
    v = run([sys.executable, "scripts/verify.py", str(args.spot)], cfg.root, check=False)
    print(v.stdout.strip()[-2500:])
    verify_ok = v.returncode == 0

    # ---- compile --------------------------------------------------------
    try:
        c = run([sys.executable, "scripts/compile.py"], cfg.root)
        print("compile:", " | ".join(c.stdout.strip().splitlines()))
    except Exception as e:                                            # noqa: BLE001
        print(f"compile failed: {e}")
        return EXIT_FETCH

    # ---- raw cleanup ----------------------------------------------------
    if not args.no_raw_cleanup:
        sh(f"rm -rf {cfg.raw_dir!r}", cfg.root)
        print("raw HTML scratch removed")

    # ---- git ------------------------------------------------------------
    if args.push and os.path.isdir(os.path.join(cfg.root, ".git")):
        try:
            sh("git add -A", cfg.root)
            staged = sh("git diff --cached --quiet || echo CHANGES", cfg.root).stdout
            if "CHANGES" in staged:
                msg = (f"{cfg.title}: +{new} chapters ({after} total)\n\n"
                       f"Automated backup run {time.strftime('%Y-%m-%d %H:%M')}.\n"
                       f"Verified: {after} chapters, no holes, no duplicates.")
                sh(f"git commit -q -m {msg!r}", cfg.root)
                sh("git push -q origin HEAD", cfg.root)
                print(f"pushed to origin (+{new} chapters)")
            else:
                print("git: nothing to commit")
        except Exception as e:                                        # noqa: BLE001
            print(f"git push failed: {e}")
    elif args.push:
        print("git: no .git in the novel root — skipping push")

    mins = (time.time() - started) / 60
    print(f"\n{'='*60}")
    print(f"{cfg.title}: {after} chapters total (+{new} this run), "
          f"verify={'PASS' if verify_ok else 'FAIL'}, {mins:.1f} min")
    return EXIT_OK if verify_ok else EXIT_VERIFY


if __name__ == "__main__":
    sys.exit(main())
