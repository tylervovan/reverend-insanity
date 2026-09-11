# Reverend Insanity — offline reading backup

Local, offline copy of *Reverend Insanity* (蛊真人, by **Gu Zhen Ren / 蛊真人**) pulled from
[Novel Phoenix](https://novelphoenix.com/novel/reverend-insanity) so it can be read on any
machine without touching the site again.

**Status:** complete — 2,334 chapters (the novel is finished; last chapter published 2022-02-11).

## What's in here

| Path | What it is |
| --- | --- |
| `chapters/0001-slug.md` | one markdown file per chapter, with source URL + fetch date in front-matter |
| `reverend-insanity.md` | the whole novel concatenated — good for Ctrl-F across all 5M+ words |
| `reverend-insanity.epub` | EPUB 3, opens in Apple Books / Calibre / KOReader / any e-reader |
| `INDEX.md` | clickable chapter list |
| `manifest.json` | the scraped chapter list (number, title, URL) — the source of truth for "did we get everything" |
| `scripts/` | the tooling: manifest scraper, chapter downloader, parser, compile, verifier |

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
