#!/usr/bin/env python3
"""Package the per-chapter markdown into a single file + an EPUB.

Outputs (in the repo root):
  reverend-insanity.md      one concatenated file, Ctrl-F across the whole novel
  reverend-insanity.epub    proper EPUB 3 for any e-reader / calibre / Apple Books
  INDEX.md                  chapter list with links

EPUB is written by hand with stdlib zipfile (no deps): an EPUB is just a zip with
an uncompressed 'mimetype' first, META-INF/container.xml, and an OEBPS payload.
"""
import html
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CH = os.path.join(ROOT, "chapters")
TITLE = "Reverend Insanity"
AUTHOR = "Gu Zhen Ren"
SOURCE = "https://novelphoenix.com/novel/reverend-insanity"

sys.path.insert(0, os.path.join(ROOT, "scripts"))
from volumes import VOLUMES, folder_name  # noqa: E402


def load_chapters():
    """Walk the volume subfolders. Returns chapters sorted by number, each carrying
    its volume so the single-file build and EPUB nav can group by volume."""
    out = []
    for vol, lo, hi, vtitle in VOLUMES:
        vdir = os.path.join(CH, folder_name(vol, vtitle))
        if not os.path.isdir(vdir):
            continue
        for f in sorted(os.listdir(vdir)):
            m = re.match(r"^(\d{4})-(.*)\.md$", f)
            if not m:
                continue
            num = int(m.group(1))
            text = open(os.path.join(vdir, f), encoding="utf-8").read()
            fm = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
            meta, body = {}, text
            if fm:
                for line in fm.group(1).splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip()
                body = fm.group(2)
            body = re.sub(r"^#\s+Chapter\s+\d+.*?$", "", body, count=1, flags=re.M).strip()
            paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
            out.append({"num": num, "title": meta.get("title", ""),
                        "source": meta.get("source", ""), "paras": paras, "file": f,
                        "volume": vol, "volume_title": vtitle})
    return sorted(out, key=lambda c: c["num"])


def build_single(chaps):
    parts = [
        f"# {TITLE}",
        "",
        f"*{AUTHOR}* — {len(chaps)} chapters in {len(VOLUMES)} volumes",
        "",
        f"Source: <{SOURCE}> (fetched for personal offline reading)",
        "",
        "---",
        "",
    ]
    current = None
    for c in chaps:
        if c["volume"] != current:
            current = c["volume"]
            parts += ["", f"# Volume {current} — {c['volume_title']}", "",
                      f"*(chapters {c['num']}–"
                      f"{next(v for v in VOLUMES if v[0] == current)[2]})*", ""]
        parts.append(f"## Chapter {c['num']}" + (f" — {c['title']}" if c["title"] else ""))
        parts.append("")
        parts.extend(c["paras"])
        parts.append("")
    path = os.path.join(ROOT, "reverend-insanity.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts).rstrip() + "\n")
    return path


def build_index(chaps):
    lines = [f"# {TITLE} — Index", "",
             f"{len(chaps)} chapters across {len(VOLUMES)} volumes. "
             "Grouped by volume, matching the folder layout.", ""]
    current = None
    for c in chaps:
        if c["volume"] != current:
            current = c["volume"]
            v = next(v for v in VOLUMES if v[0] == current)
            lines += ["", f"## Volume {current} — {c['volume_title']} "
                          f"(chapters {v[1]}–{v[2]})", ""]
        sub = folder_name(c["volume"], c["volume_title"])
        lines.append(f"- [{c['num']}. {c['title'] or ''}](chapters/{sub}/{c['file']})")
    path = os.path.join(ROOT, "INDEX.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


CSS = """body{font-family:Georgia,serif;line-height:1.5;margin:0 5%;}
h1{font-size:1.3em;margin:1.2em 0 .8em;}
p{margin:0 0 .6em;text-indent:1.2em;}
p:first-of-type{text-indent:0;}"""


def xhtml_escape(s):
    return html.escape(s, quote=False)


def inline(s):
    """markdown italics -> <em>; everything else escaped."""
    s = xhtml_escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)
    return s


def chap_xhtml(c):
    paras = "\n".join(f"<p>{inline(p)}</p>" for p in c["paras"])
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">\n'
        f"<head><title>Chapter {c['num']}</title>"
        '<link rel="stylesheet" type="text/css" href="style.css"/></head>\n'
        f'<body><section epub:type="chapter" xmlns:epub="http://www.idpf.org/2007/ops">'
        f"<h1>Chapter {c['num']}" + (f" — {xhtml_escape(c['title'])}" if c["title"] else "")
        + f"</h1>\n{paras}\n</section></body>\n</html>\n"
    )


def build_epub(chaps, path):
    files = {}
    files["mimetype"] = "application/epub+zip"
    files["META-INF/container.xml"] = (
        '<?xml version="1.0"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    files["OEBPS/style.css"] = CSS
    files["OEBPS/title.xhtml"] = (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>'
        f'{TITLE}</title><link rel="stylesheet" type="text/css" href="style.css"/>'
        f'</head><body><h1>{TITLE}</h1><p>{AUTHOR}</p>'
        f"<p>{len(chaps)} chapters — fetched for personal offline reading.</p></body></html>"
    )

    items, spine, navs = [], [], []
    items.append('<item id="title" href="title.xhtml" media-type="application/xhtml+xml"/>')
    items.append('<item id="css" href="style.css" media-type="text/css"/>')
    spine.append('<itemref idref="title"/>')
    navs.append('<li><a href="title.xhtml">Title</a></li>')

    # one part page + one nested <ol> per volume, so the EPUB TOC isn't a flat
    # list of 2,334 entries
    by_vol = {}
    for c in chaps:
        by_vol.setdefault(c["volume"], []).append(c)

    for vol, lo, hi, vtitle in VOLUMES:
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
            f'<section epub:type="part"><h1>Volume {vol} — {xhtml_escape(vtitle)}</h1>'
            f'<p>Chapters {lo}–{hi}</p></section></body></html>'
        )
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
            label = f"{c['num']}. {xhtml_escape(c['title'])}" if c["title"] else str(c["num"])
            kids.append(f'<li><a href="{cid}.xhtml">{label}</a></li>')
        navs.append(f'<li><a href="{vid}.xhtml">Volume {vol} — '
                    f'{xhtml_escape(vtitle)}</a><ol>' + "\n".join(kids) + "</ol></li>")

    files["OEBPS/nav.xhtml"] = (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title>'
        '<link rel="stylesheet" type="text/css" href="style.css"/></head><body>'
        '<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>' + "\n".join(navs) +
        "</ol></nav></body></html>"
    )
    items.append('<item id="nav" href="nav.xhtml" properties="nav" '
                 'media-type="application/xhtml+xml"/>')

    files["OEBPS/content.opf"] = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="bookid"><metadata '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="bookid">urn:uuid:reverend-insanity-novelphoenix-{len(chaps)}</dc:identifier>'
        f"<dc:title>{TITLE}</dc:title><dc:creator>{AUTHOR}</dc:creator>"
        '<dc:language>en</dc:language>'
        f'<dc:source>{SOURCE}</dc:source>'
        '<meta property="dcterms:modified">2026-09-11T00:00:00Z</meta>'
        "</metadata><manifest>" + "".join(items) + "</manifest><spine>" +
        "".join(spine) + "</spine></package>"
    )

    tmp = path + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        # mimetype MUST be first and stored uncompressed
        z.writestr(zipfile.ZipInfo("mimetype"), files["mimetype"],
                   compress_type=zipfile.ZIP_STORED)
        for name in ["META-INF/container.xml"] + [k for k in files if k.startswith("OEBPS/")]:
            z.writestr(name, files[name], compress_type=zipfile.ZIP_DEFLATED)
    os.replace(tmp, path)
    return path


def main():
    chaps = load_chapters()
    if not chaps:
        sys.exit("no chapters found")
    print(f"chapters: {len(chaps)}  nums {chaps[0]['num']}..{chaps[-1]['num']}")
    print("single:", build_single(chaps))
    print("index :", build_index(chaps))
    print("epub  :", build_epub(chaps, os.path.join(ROOT, "reverend-insanity.epub")))


if __name__ == "__main__":
    main()