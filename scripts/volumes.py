#!/usr/bin/env python3
"""Volume boundaries for Reverend Insanity, and the restructure into subfolders.

Boundaries sourced from the Reverend Insanity Wiki "Volumes" page
(https://reverend-insanity.fandom.com/wiki/Volumes), which lists 2,334 chapter rows
across 6 volumes — matching this backup's chapter count exactly. Cross-checked
against the wiki's Fang Yuan page ranges.

GitHub's web UI truncates any directory listing at 1,000 entries, which is why the
chapters are split: the largest volume folder here holds 945 files.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CH = os.path.join(ROOT, "chapters")

# (volume, first chapter, last chapter, title)
VOLUMES = [
    (1, 1, 199, "A Demon's Nature Doesn't Change"),
    (2, 200, 405, "The Demon Leaves the Mountain"),
    (3, 406, 649, "The Demon Wreaks Chaos in the World"),
    (4, 650, 1021, "The Demon Lord Rampages Unhindered"),
    (5, 1022, 1966, "Demon King's Domination"),
    (6, 1967, 2334, "Demon Venerable's Eternal Life"),
]


def folder_name(vol, title):
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"vol-{vol:02d}-{slug}"


def volume_of(num):
    for vol, lo, hi, title in VOLUMES:
        if lo <= num <= hi:
            return vol, lo, hi, title
    raise ValueError(f"chapter {num} is outside every volume")


def write_volumes_json():
    data = [
        {"volume": v, "first": lo, "last": hi, "title": t,
         "folder": folder_name(v, t), "chapters": hi - lo + 1}
        for v, lo, hi, t in VOLUMES
    ]
    with open(os.path.join(ROOT, "volumes.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return data


def restructure():
    data = write_volumes_json()
    moved = skipped = 0
    for vol, lo, hi, title in VOLUMES:
        dest = os.path.join(CH, folder_name(vol, title))
        os.makedirs(dest, exist_ok=True)
    # bare files sitting directly in chapters/ (the original flat layout)
    for f in sorted(os.listdir(CH)):
        path = os.path.join(CH, f)
        if not os.path.isfile(path):
            continue
        m = re.match(r"^(\d{4})-.*\.md$", f)
        if not m:
            skipped += 1
            continue
        num = int(m.group(1))
        vol, lo, hi, title = volume_of(num)
        target = os.path.join(CH, folder_name(vol, title), f)
        if not os.path.exists(target):
            os.rename(path, target)
            moved += 1
    print(f"moved {moved} chapter files into {len(VOLUMES)} volume folders "
          f"(skipped {skipped} unrecognised files)")
    for d in data:
        n = len(os.listdir(os.path.join(CH, d["folder"])))
        flag = "  <-- over GitHub's 1000 cap!" if n > 1000 else ""
        print(f"  {d['folder']}: {n} files{flag}")
    return data


if __name__ == "__main__":
    data = restructure()
    total = sum(d["chapters"] for d in data)
    print(f"\ntotal chapters across volumes: {total}")
    if total != 2334:
        sys.exit("volume ranges do not sum to 2334 — boundaries are wrong")
    print("volume ranges sum correctly to 2334")
