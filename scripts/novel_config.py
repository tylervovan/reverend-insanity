#!/usr/bin/env python3
"""Per-novel configuration for the novel backup pipeline.

Each novel's repo root carries a `novel.json`. One novel can list several mirror
`sources`; they are tried in order, so when the first is down the run falls back to
the next (novelphoenix → novelfire, in practice).

  {
    "title": "Shadow Slave",
    "author": "Guiltythree",
    "ongoing": true,
    "sources": [
      {"name": "novelphoenix", "base": "https://novelphoenix.com",
       "slug": "shadow-slave", "slug_prefix": "chapter", "profile": "novelphoenix"},
      {"name": "novelfire", "base": "https://novelfire.net",
       "slug": "shadow-slave", "slug_prefix": "chapter", "profile": "generic"}
    ],
    "volumes": [ {"volume": 1, "first": 0, "last": 95, "title": "Child of Shadows"}, ... ]
  }

`profile` selects the parser: "novelphoenix" (verified against that site), "generic"
(auto-detect the prose container — for sites we haven't profiled), or "auto" (try
novelphoenix, fall back to generic if it yields too little text).

A legacy flat config (top-level slug/base, no `sources`) still works: it becomes a
single source with profile "auto".

Volume ranges may be open-ended for an ongoing novel: the final volume may set
"last": null and absorbs whatever the manifest ends at.
"""
import json
import os
import re

DEFAULT_BASE = "https://novelphoenix.com"
CONFIG_NAME = "novel.json"


class Source:
    def __init__(self, data):
        self.name = data["name"]
        self.base = data.get("base", DEFAULT_BASE).rstrip("/")
        self.slug = data["slug"]
        self.slug_prefix = data.get("slug_prefix", "chapter")
        self.profile = data.get("profile", "auto")

    def novel_url(self):
        return f"{self.base}/novel/{self.slug}"

    def index_url(self, page):
        return f"{self.base}/novel/{self.slug}/chapters?page={page}"

    def chapter_url(self, num):
        return f"{self.base}/novel/{self.slug}/{self.slug_prefix}-{num}"

    def chapter_regex(self):
        return re.compile(
            r'href="(?:' + re.escape(self.base) + r')?/novel/' + re.escape(self.slug)
            + r'/' + re.escape(self.slug_prefix) + r'-(\d+)"[^>]*>(.*?)</a>', re.S)

    def __repr__(self):
        return f"<Source {self.name} {self.base}/novel/{self.slug} profile={self.profile}>"


class Config:
    def __init__(self, data, root):
        self.root = root
        self.data = data
        self.title = data["title"]
        self.author = data.get("author", "")
        self.ongoing = bool(data.get("ongoing", False))
        self.volumes = data.get("volumes") or []
        if not self.volumes:
            raise ValueError(f"{CONFIG_NAME}: no volumes defined")

        if data.get("sources"):
            self.sources = [Source(s) for s in data["sources"]]
        else:  # legacy flat config
            self.sources = [Source({"name": data.get("name", "primary"),
                                    "base": data.get("base", DEFAULT_BASE),
                                    "slug": data["slug"],
                                    "slug_prefix": data.get("slug_prefix", "chapter"),
                                    "profile": data.get("profile", "auto")})]

    # ---- paths ---------------------------------------------------
    @property
    def slug(self):
        return self.sources[0].slug

    @property
    def chapters_dir(self):
        return os.path.join(self.root, "chapters")

    @property
    def manifest_path(self):
        return os.path.join(self.root, "manifest.json")

    @property
    def raw_dir(self):
        return os.path.join(self.root, "raw")

    # ---- sources -------------------------------------------------
    def source(self, name=None):
        if not name:
            return self.sources[0]
        for s in self.sources:
            if s.name == name:
                return s
        raise SystemExit(f"unknown source {name!r}; configured: "
                         f"{[s.name for s in self.sources]}")

    def source_names(self):
        return [s.name for s in self.sources]

    # ---- volumes -------------------------------------------------
    def volume_of(self, num):
        """(volume, first, last, title); the last volume may have last=None."""
        for i, v in enumerate(self.volumes):
            lo, hi = v["first"], v.get("last")
            is_last = i == len(self.volumes) - 1
            if hi is None and is_last and num >= lo:
                return v["volume"], lo, None, v["title"]
            if hi is not None and lo <= num <= hi:
                return v["volume"], lo, hi, v["title"]
        raise ValueError(f"chapter {num} is outside every configured volume")

    @staticmethod
    def folder_name(vol, title):
        slug = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
        return f"vol-{vol:02d}-{slug}" if slug else f"vol-{vol:02d}"

    def volume_dir(self, num, create=True):
        vol, _lo, _hi, t = self.volume_of(num)
        d = os.path.join(self.chapters_dir, self.folder_name(vol, t))
        if create:
            os.makedirs(d, exist_ok=True)
        return d

    def volume_range_label(self, vol):
        for v in self.volumes:
            if v["volume"] == vol:
                return (v["first"], v.get("last"))
        return (None, None)


def load_manifest(cfg):
    """Read manifest.json, tolerating both the new {source, chapters:[...]} shape and
    the legacy bare-list shape. Returns (entries, source_name_or_None)."""
    with open(cfg.manifest_path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data, None
    return data.get("chapters", []), data.get("source")


def load_config(root=None):
    """Load novel.json from `root` (default: repo root relative to this file)."""
    if root is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, CONFIG_NAME)
    if not os.path.exists(path):
        raise SystemExit(f"no {CONFIG_NAME} in {root} — see scripts/novel_config.py")
    with open(path, encoding="utf-8") as f:
        return Config(json.load(f), root)


if __name__ == "__main__":
    c = load_config()
    print(f"{c.title} by {c.author}" + ("  (ongoing)" if c.ongoing else ""))
    print("sources, in failover order:")
    for s in c.sources:
        print(f"  {s.name:<14} {s.novel_url()}  profile={s.profile}")
    known = sum((v.get("last") or 0) - v["first"] + 1 for v in c.volumes
                if v.get("last") is not None)
    print(f"volumes: {len(c.volumes)}  known chapters: {known}")
    for v in c.volumes:
        hi = v.get("last")
        print(f"  vol {v['volume']:>2}: {v['first']}-{hi if hi else '?'} "
              f"{v['title']}  -> {c.folder_name(v['volume'], v['title'])}")
