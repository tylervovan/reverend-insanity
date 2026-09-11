# Reverend Insanity — offline reading backup

Local, offline copy of *Reverend Insanity* (蛊真人, by **Gu Zhen Ren / 蛊真人**) pulled from
[Novel Phoenix](https://novelphoenix.com/novel/reverend-insanity) so it can be read on any
machine without touching the site again.

**Status:** complete — 2,334 chapters (the novel is finished; last chapter published 2022-02-11).

## What's in here

| Path | What it is |
| --- | --- |
| `chapters/vol-0N-.../` | one markdown file per chapter, grouped into the novel's 6 volumes; each file carries source URL + fetch date in front-matter |
| `reverend-insanity.md` | the whole novel concatenated — good for Ctrl-F across all 4.85M words |
| `reverend-insanity.epub` | EPUB 3, opens in Apple Books / Calibre / KOReader / any e-reader |
| `INDEX.md` | clickable chapter list, grouped by volume |
| `manifest.json` | the scraped chapter list (number, title, URL) — the source of truth for "did we get everything" |
| `volumes.json` | the 6 volume boundaries and their folders |
| `scripts/` | the tooling: manifest scraper, chapter downloader, parser, compile, verifier |

## Volumes

Chapters are organised by volume; boundaries from the
[RI Wiki volumes page](https://reverend-insanity.fandom.com/wiki/Volumes) (its table has exactly
2,334 rows, matching this backup).

| Volume | Chapters | Title |
| --- | --- | --- |
| 1 | 1–199 | A Demon's Nature Doesn't Change |
| 2 | 200–405 | The Demon Leaves the Mountain |
| 3 | 406–649 | The Demon Wreaks Chaos in the World |
| 4 | 650–1021 | The Demon Lord Rampages Unhindered |
| 5 | 1022–1966 | Demon King's Domination |
| 6 | 1967–2334 | Demon Venerable's Eternal Life |

The split also works around a GitHub quirk: the web UI truncates any directory listing at 1,000
entries, so a flat `chapters/` folder looked like it stopped at chapter 1,000. The largest volume
folder holds 945 files.

`raw/` (the scraped HTML) is scratch data, gitignored, and deleted after parsing — the markdown
is the artifact.

## Reading it

- **Any machine, quickest:** open `reverend-insanity.md` in any editor, or `INDEX.md` in a
  markdown viewer.
- **Proper reading experience:** open `reverend-insanity.epub` in Calibre / Apple Books / KOReader.
- **Per chapter:** `chapters/` is plain text, greppable (`rg "Spring Autumn Cicada" chapters/`).

## Reproducing / updating

```bash
python3 scripts/fetch_manifest.py         # rebuild manifest.json from the site index
python3 scripts/fetch_chapters.py         # download + extract (resumable; skips what exists)
python3 scripts/verify.py 8               # verify against manifest + spot-check 8 live chapters
python3 scripts/compile.py                # rebuild the single-file md, INDEX.md and the EPUB
```

The downloader is idempotent and resumable — re-running it after an interruption only fetches
what's missing, so a crash at chapter 2,000 costs nothing.

## Provenance and etiquette

- Fetched 2026-09-11 from novelphoenix.com with a plain identifying user-agent, three workers,
  and a delay between requests. `robots.txt` allows `*`, and the AI-training content signal on
  that site is `no` — this is a personal offline reading copy, not model training data, and it
  is deliberately kept in a **private** repository.
- The novel is the work of Gu Zhen Ren; the English translation is by the fan translation
  community, hosted by Novel Phoenix. This repo is a personal reading backup, not a
  redistribution. Do not make it public.
