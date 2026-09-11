#!/usr/bin/env python3
"""Extract chapter title + body from a Novel Phoenix chapter page, as markdown.

Stdlib only. Structure of a chapter page (verified on chapters 1, 777, 1500, 2334):

  <div class="titles"><h1>...<span class="chapter-title">Chapter N - N: Foo</span>
      <p class="words">[ ... words ]</p></h1></div>      <- header, has the real title
  <div class="clearfix chapternav">...</div>              <- prev/next
  <div id="chapter-container" class="d-chapter-content font_default">
      <div class="nf-ads mb-3">...</div>                  <- ad, nested inside, unbalanced
      <div class="clearfix font_default"><p>...</p>...</div>  <- the actual prose
      <div class="box-notification">Share to your friends</div>
      <div class="nf-ads ...">...</div>
  </div>
  <div class="text-center box-notice">Tip: ...</div>      <- still inside #chapter-container
  <div class="report-container mt-3">If you find any errors ... Report</div>

So: capture the title from .chapter-title anywhere in the doc; capture body only
inside #chapter-container; and hard-stop at the first end-of-text widget, because
depth counting alone bleeds the tip/report widgets into the body (one ad div
inside the container is left unclosed by the site).
"""
import html
import re
from html.parser import HTMLParser

# Subtrees to skip while walking inside the chapter container.
JUNK_CLASS = re.compile(
    r"(nf-ads|box-notification|sharethis|share-|advert|pubadx|skiptranslate|"
    r"control-action|frame|restore)",
    re.I,
)
# Widgets that mark the end of the prose; stop capturing for good.
STOP_CLASS = re.compile(r"(box-notice|report-container|chapternav|chapindex|comment)", re.I)

JUNK_TEXT = re.compile(
    r"^\s*(\[\s*\.\.\.\s*words?\s*\]"
    r"|restore scroll position"
    r"|share to your friends"
    r"|prev(ious)? chapter|next chapter|chapter list"
    r"|tip: you can use|tap the middle"
    r"|\*{0,2}report\*{0,2}"
    r"|\*{1,2}"
    r"|\s*)\s*$",
    re.I,
)
BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "li", "blockquote", "div", "section"}


class ChapterParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = None
        self._title_buf = []
        self._in_title = False
        self._title_done = False
        self._capture = False
        self._stopped = False
        self._depth = 0
        self._skip_depth = None
        self._buf = []
        self._blocks = []

    @staticmethod
    def _attrs(attrs):
        return {k.lower(): (v or "") for k, v in attrs}

    @property
    def _skipping(self):
        return self._skip_depth is not None

    def _flush(self):
        text = re.sub(r"[ \t]*\n[ \t]*", "\n", "".join(self._buf))
        text = re.sub(r"[ \t]{2,}", " ", text).strip()
        if text and not JUNK_TEXT.match(text):
            self._blocks.append(text)
        self._buf = []

    # ------------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = self._attrs(attrs)
        cls = a.get("class", "")

        # Title: first .chapter-title in the document (it sits outside the container).
        if not self._title_done and "chapter-title" in cls:
            self._in_title = True

        if tag == "div":
            if self._stopped:
                return
            if self._skipping:
                self._depth += 1
                return
            if not self._capture:
                if a.get("id") == "chapter-container":
                    self._capture = True
                    self._depth = 1
                return
            if STOP_CLASS.search(cls):
                self._flush()
                self._stopped = True
                self._capture = False
                return
            self._depth += 1
            if JUNK_CLASS.search(cls) or a.get("id") == "frame":
                self._skip_depth = self._depth - 1
            return

        if not self._capture or self._skipping:
            return
        if tag in BLOCK_TAGS:
            self._flush()
        elif tag == "br":
            self._buf.append("\n")
        elif tag in ("em", "i"):
            self._buf.append("*")
        elif tag in ("strong", "b"):
            self._buf.append("**")

    def handle_endtag(self, tag):
        if tag == "span" and self._in_title:
            self._in_title = False
            self._title_done = True
            return
        if tag == "div":
            if self._stopped:
                return
            if self._skipping:
                self._depth -= 1
                if self._depth <= self._skip_depth:
                    self._skip_depth = None
                return
            if self._capture:
                self._depth -= 1
                if self._depth <= 0:
                    self._flush()
                    self._capture = False
            return
        if self._capture and tag in BLOCK_TAGS:
            self._flush()
        elif self._capture and tag in ("em", "i"):
            self._buf.append("*")
        elif self._capture and tag in ("strong", "b"):
            self._buf.append("**")

    def handle_data(self, data):
        if self._in_title:
            self._title_buf.append(data)
            return
        if not self._capture or self._skipping or self._stopped:
            return
        self._buf.append(data)

    def finish(self):
        self._flush()
        title = re.sub(r"\s+", " ", "".join(self._title_buf)).strip()
        return title, self._blocks


def clean_title(num, raw):
    """'Chapter 1 - 1: The heart of a demon...' -> 'The heart of a demon...'"""
    t = re.sub(r"\s+", " ", raw or "").strip()
    t = re.sub(r"^Reverend\s+Insanity\s*[-|\u2013]\s*", "", t, flags=re.I)
    t = re.sub(r"^Chapter\s+%d\s*[-:\u2013]\s*" % num, "", t, flags=re.I)
    t = re.sub(r"^\d+\s*[-:\u2013]\s*", "", t)          # site's "1: Foo" duplicate
    return t.strip(" -\u2013:").strip()


def parse_document(doc_html, num=None):
    p = ChapterParser()
    p.feed(doc_html)
    title, blocks = p.finish()
    if not title:
        m = re.search(r"<title>(.*?)</title>", doc_html, re.S | re.I)
        if m:
            title = re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()
    if num is not None:
        title = clean_title(num, title)
    blocks = [re.sub(r"\n{3,}", "\n\n", b).strip() for b in blocks]
    blocks = [b for b in blocks if b]
    return title, blocks


def to_markdown(num, title, blocks, source, fetched):
    head = [
        "---",
        f"chapter: {num}",
        "title: " + (title.replace('"', "'") if title else ""),
        f"source: {source}",
        f"fetched: {fetched}",
        "---",
        "",
        f"# Chapter {num}" + (f" — {title}" if title else ""),
        "",
    ]
    return "\n".join(head) + "\n\n".join(blocks) + "\n"


if __name__ == "__main__":
    import sys
    for path in sys.argv[1:]:
        num = int(re.search(r"(\d+)", path.split("ri")[-1]).group(1))
        doc = open(path, encoding="utf-8").read()
        t, b = parse_document(doc, num)
        words = sum(len(x.split()) for x in b)
        print(f"=== {path}\n  title: {t}\n  blocks: {len(b)}  words: {words}")
        print("  first:", b[0][:90] if b else None)
        print("  last :", b[-1][:90] if b else None)
