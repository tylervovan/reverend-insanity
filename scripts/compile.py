#!/usr/bin/env python3
"""Package the per-chapter markdown into a single file + an EPUB + an INDEX.

Outputs (repo root, filenames derived from the slug):
  <slug>.md      one concatenated file, Ctrl-F across the whole novel
  <slug>.epub    EPUB 3: each chapter is its own spine document, TOC nested by volume
  INDEX.md       clickable chapter list, grouped by volume

EPUB is written by hand with stdlib zipfile (no deps): an EPUB is a zip with an
uncompressed 'mimetype' first, META-INF/container.xml, and an OEBPS payload.
"""
import html
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from novel_config import load_config  # noqa: E402

CSS = """body{font-family:Georgia,serif;line-height:1.5;margin:0 5%;}
h1{font-size:1.3em;margin:1.2em 0 .8em;}
p{margin:0 0 .6em;text-indent:1.2em;}
p:first-of-type{text-indent:0;}"""


def load_chapters(cfg):
    """Walk the volume folders, return chapters sorted by number with volume info."""
    out = []
    for v in cfg.volumes:
        vdir = os.path.join(cfg.chapters_dir, cfg.folder_name(v["volume"], v["title"]))
        if not os.path.isdir(vdir):
            continue
        for f in sorted(os.listdir(vdir)):
            if not re.match(r"^\d+-.*\.md$", f):
                continue
            num = int(f.split("-")[0])
            text = open(os.path.join(vdir, f), encoding="utf-8").read()
            fm = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
            meta, body = {}, text
            if fm:
                for line in fm.group(1).splitlines():
                    if ":" in line:
                        k, val = line.split(":", 1)
                        meta[k.strip()] = val.strip()
                body = fm.group(2)
            body = re.sub(r"^#\s+Chapter\s+\d+.*?$", "", body, count=1, flags=re.M).strip()
            paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
            out.append({"num": num, "title": meta.get("title", ""),
                        "paras": paras, "file": f, "volume": v["volume"],
                        "volume_title": v["title"]})
    return sorted(out, key=lambda c: c["num"])


def vol_label(cfg, vol):
    lo, hi = cfg.volume_range_label(vol)
    return f"chapters {lo}–{hi}" if hi else f"chapters {lo}–ongoing"


def build_single(cfg, chaps):
    parts = [f"# {cfg.title}", "", f"*{cfg.author}* — {len(chaps)} chapters in "
             f"{len(cfg.volumes)} volumes", "",
             f"Source: <{cfg.source().novel_url()}> (fetched for personal offline reading)", "",
             "---", ""]
    current = None
    for c in chaps:
        if c["volume"] != current:
            current = c["volume"]
            parts += ["", f"# Volume {current} — {c['volume_title']}", "",
                      f"*({vol_label(cfg, current)})*", ""]
        parts.append(f"## Chapter {c['num']}" + (f" — {c['title']}" if c["title"] else ""))
        parts.append("")
        parts.extend(c["paras"])
        parts.append("")
    path = os.path.join(cfg.root, f"{cfg.slug}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts).rstrip() + "\n")
    return path


def build_index(cfg, chaps):
    lines = [f"# {cfg.title} — Index", "",
             f"{len(chaps)} chapters across {len(cfg.volumes)} volumes. "
             "Grouped by volume, matching the folder layout.", ""]
    current = None
    for c in chaps:
        if c["volume"] != current:
            current = c["volume"]
            lines += ["", f"## Volume {current} — {c['volume_title']} "
                          f"({vol_label(cfg, current)})", ""]
        sub = cfg.folder_name(c["volume"], c["volume_title"])
        lines.append(f"- [{c['num']}. {c['title'] or ''}](chapters/{sub}/{c['file']})")
    path = os.path.join(cfg.root, "INDEX.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def esc(s):
    return html.escape(s, quote=False)


def inline(s):
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)


def chap_xhtml(c):
    paras = "\n".join(f"<p>{inline(p)}</p>" for p in c["paras"])
    head = f"Chapter {c['num']}" + (f" — {esc(c['title'])}" if c["title"] else "")
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">\n'
            f"<head><title>{head}</title>"
            '<link rel="stylesheet" type="text/css" href="style.css"/></head>\n'
            '<body><section epub:type="chapter" '
            'xmlns:epub="http://www.idpf.org/2007/ops">'
            f"<h1>{head}</h1>\n{paras}\n</section></body>\n</html>\n")


def build_epub(cfg, chaps, path):
    files = {"mimetype": "application/epub+zip"}
    files["META-INF/container.xml"] = (
        '<?xml version="1.0"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>')
    files["OEBPS/style.css"] = CSS
    files["OEBPS/title.xhtml"] = (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>'
        f'{esc(cfg.title)}</title><link rel="stylesheet" type="text/css" href="style.css"/>'
        f'</head><body><h1>{esc(cfg.title)}</h1><p>{esc(cfg.author)}</p>'
        f"<p>{len(chaps)} chapters — fetched for personal offline reading.</p></body></html>")

    items = ['<item id="title" href="title.xhtml" media-type="application/xhtml+xml"/>',
             '<item id="css" href="style.css" media-type="text/css"/>']
    spine = ['<itemref idref="title"/>']
    navs = ['<li><a href="title.xhtml">Title</a></li>']

    by_vol = {}
    for c in chaps:
        by_vol.setdefault(c["volume"], []).append(c)

    for v in cfg.volumes:
        vol, vtitle = v["volume"], v["title"]
        group = by_vol.get(vol, [])
        if not group:
            continue
        vid = f"v{vol:02d}"
        files[f"OEBPS/{vid}.xhtml"] = (
            '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops"><head>'
            f'<title>Volume {vol}</title>'
            '<link rel="stylesheet" type="text/css" href="style.css"/></head><body>'
            f'<section epub:type="part"><h1>Volume {vol} — {esc(vtitle)}</h1>'
            f"<p>{vol_label(cfg, vol).capitalize()}</p></section></body></html>")
        items.append(f'<item id="{vid}" href="{vid}.xhtml" '
                     'media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="{vid}"/>')
        kids = []
        for c in group:
            cid = f"c{c['num']:04d}"
            files[f"OEBPS/{cid}.xhtml"] = chap_xhtml(c)
            items.append(f'<item id="{cid}" href="{cid}.xhtml" '
                         'media-type="application/xhtml+xml"/>')
            spine.append(f'<itemref idref="{cid}"/>')
            label = f"{c['num']}. {esc(c['title'])}" if c["title"] else str(c["num"])
            kids.append(f'<li><a href="{cid}.xhtml">{label}</a></li>')
        navs.append(f'<li><a href="{vid}.xhtml">Volume {vol} — {esc(vtitle)}</a><ol>'
                    + "\n".join(kids) + "</ol></li>")

    files["OEBPS/nav.xhtml"] = (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title>'
        '<link rel="stylesheet" type="text/css" href="style.css"/></head><body>'
        '<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>'
        + "\n".join(navs) + "</ol></nav></body></html>")
    items.append('<item id="nav" href="nav.xhtml" properties="nav" '
                 'media-type="application/xhtml+xml"/>')

    files["OEBPS/content.opf"] = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="bookid"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="bookid">urn:uuid:{cfg.slug}-novelphoenix-{len(chaps)}'
        f"</dc:identifier><dc:title>{esc(cfg.title)}</dc:title>"
        f"<dc:creator>{esc(cfg.author)}</dc:creator><dc:language>en</dc:language>"
        f"<dc:source>{cfg.source().novel_url()}</dc:source>"
        '<meta property="dcterms:modified">2026-09-11T00:00:00Z</meta>'
        "</metadata><manifest>" + "".join(items) + "</manifest><spine>"
        + "".join(spine) + "</spine></package>")

    tmp = path + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), files["mimetype"],
                   compress_type=zipfile.ZIP_STORED)
        for name in ["META-INF/container.xml"] + [k for k in files if k.startswith("OEBPS/")]:
            z.writestr(name, files[name], compress_type=zipfile.ZIP_DEFLATED)
    os.replace(tmp, path)
    return path


def main():
    cfg = load_config()
    chaps = load_chapters(cfg)
    if not chaps:
        sys.exit("no chapters found — run fetch_chapters.py first")
    print(f"{cfg.title}: {len(chaps)} chapters, {chaps[0]['num']}..{chaps[-1]['num']}")
    print("single:", build_single(cfg, chaps))
    print("index :", build_index(cfg, chaps))
    print("epub  :", build_epub(cfg, chaps, os.path.join(cfg.root, f"{cfg.slug}.epub")))


if __name__ == "__main__":
    main()
