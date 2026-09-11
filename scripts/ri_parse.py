#!/usr/bin/env python3
"""Extract chapter title + body from a chapter page, as markdown. Stdlib only.

Two profiles:

  "novelphoenix"  verified against novelphoenix.com (chapters 1, 777, 1500, 2334).
                  Title in span.chapter-title (in the header, OUTSIDE the container);
                  body in div#chapter-container, which also wraps the prev/next nav,
                  a "Tip: use arrow keys" notice and a "Report an error" widget, and
                  contains one ad div the site leaves unclosed — so we hard-stop at
                  the first end-of-content marker rather than trusting div depth.

  "generic"       for sites we haven't profiled (novelfire etc.). Walks every div,
                  counts its <p> descendants while ignoring junk subtrees, and picks
                  the busiest paragraph container. No site-specific stop markers, so
                  junk removal is class-based only.

  "auto"          try the novelphoenix profile; if it yields under `min_words`, fall
                  back to generic. Used so a site redesign degrades instead of breaking.
"""
import html
import re
from html.parser import HTMLParser

# ---------------------------------------------------------------- shared bits

BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "li", "blockquote"}

# Subtrees dropped in the novelphoenix profile while walking the chapter container.
NP_JUNK_CLASS = re.compile(
    r"(nf-ads|box-notification|sharethis|share-|advert|pubadx|skiptranslate|"
    r"control-action|frame|restore)",
    re.I,
)
# Widgets that mean the prose has ended (the container wraps these too).
NP_STOP_CLASS = re.compile(r"(box-notice|report-container|chapternav|chapindex|comment)", re.I)

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

# Class/id fragments that are never prose, in any profile. Deliberately generic.
GENERIC_JUNK_CLASS = re.compile(
    r"(^|[-_ ])("
    r"ad|ads|advert\w*|banner|promo|sponsor\w*"
    r"|share\w*|social\w*|comment\w*|disqus"
    r"|report\w*|notice|notification\w*|alert|restore"
    r"|nav\w*|navigation|breadcrumb\w*|menu|toolbar|pagination|pager"
    r"|sidebar|aside|footer|header|topbar|widget"
    r"|related|recommend\w*|popular|latest|random"
    r"|modal|popup|dialog|overlay|hidden|skiptranslate|translate"
    r"|chapter[-_]?(nav|list|index)|read[-_]?option\w*|setting\w*"
    r")([-_ ]|$)",
    re.I,
)

# Elements that never contain prose, in any profile.
GENERIC_JUNK_TAGS = {"script", "style", "nav", "header", "footer", "aside", "form",
                     "iframe", "svg", "button", "select", "option", "dialog",
                     "noscript", "figure", "figcaption", "ins", "textarea", "input"}

# Elements that start a new paragraph when encountered during extraction.
PARA_TAGS = {"p", "div", "section", "article", "li", "blockquote",
             "h1", "h2", "h3", "h4", "h5", "h6", "tr", "dd", "dt", "pre", "hr"}

# Stray UI strings that survive class filtering (e.g. a plain div-wrapped link).
GENERIC_JUNK_TEXT = re.compile(
    r"^\s*(restore scroll position|share to your friends|\*{0,2}report\*{0,2}"
    r"|report (an )?error|prev(ious)?( chapter)?|next( chapter)?"
    r"|chapter list|table of contents|tip:.*|tap .*|read (more|latest).*"
    r"|\[\s*\.\.\.\s*words?\s*\]|\*{1,2}|\s*)\s*$",
    re.I,
)


def clean_title(num, raw):
    """'Chapter 1 - 1: The heart of a demon...' -> 'The heart of a demon...'"""
    t = re.sub(r"\s+", " ", raw or "").strip()
    t = re.sub(r"^Reverend\s+Insanity\s*[-|\u2013]\s*", "", t, flags=re.I)
    t = re.sub(r"^Chapter\s+%d\s*[-:\u2013]\s*" % num, "", t, flags=re.I)
    t = re.sub(r"^\d+\s*[-:\u2013]\s*", "", t)
    t = re.sub(r"\s*[-|\u2013]\s*Novel\s*(Fire|Phoenix|Bin|Full)\s*$", "", t, flags=re.I)
    return t.strip(" -\u2013:").strip()


def _clean_blocks(blocks):
    out = [re.sub(r"[ \t]*\n[ \t]*", "\n", b) for b in blocks]
    out = [re.sub(r"\n{2,}", "\n", b).strip() for b in out]
    return [b for b in out if b and not JUNK_TEXT.match(b)]


def _attrs(attrs):
    return {k.lower(): (v or "") for k, v in attrs}


# ------------------------------------------------------- novelphoenix profile

class NovelPhoenixParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = None
        self._title_buf, self._in_title, self._title_done = [], False, False
        self._capture = self._stopped = False
        self._depth = 0
        self._skip_depth = None
        self._buf, self._blocks = [], []

    @property
    def _skipping(self):
        return self._skip_depth is not None

    def _flush(self):
        text = re.sub(r"[ \t]*\n[ \t]*", "\n", "".join(self._buf))
        text = re.sub(r"[ \t]{2,}", " ", text).strip()
        if text and not JUNK_TEXT.match(text):
            self._blocks.append(text)
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = _attrs(attrs)
        cls = a.get("class", "")
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
                    self._capture, self._depth = True, 1
                return
            if NP_STOP_CLASS.search(cls):
                self._flush()
                self._stopped = self._capture = False
                return
            self._depth += 1
            if NP_JUNK_CLASS.search(cls) or a.get("id") == "frame":
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
            self._in_title, self._title_done = False, True
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
        if not self._capture:
            return
        if tag in BLOCK_TAGS:
            self._flush()
        elif tag in ("em", "i"):
            self._buf.append("*")
        elif tag in ("strong", "b"):
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
        return re.sub(r"\s+", " ", "".join(self._title_buf)).strip(), self._blocks


# ----------------------------------------------------------- generic profile

VOID_TAGS = {"br", "img", "hr", "meta", "link", "input", "source", "wbr", "area",
             "base", "col", "embed", "param", "track"}


class _Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.children = []


class _DomBuilder(HTMLParser):
    """Minimal tolerant DOM. We need a tree (not a stream) so a container can be
    scored, then re-walked for paragraph boundaries."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", {}, None)
        self.stack = [self.root]
        self.title, self._title_buf, self._in_title = None, [], False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        node = _Node(tag, _attrs(attrs), self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(_Node(tag, _attrs(attrs), self.stack[-1]))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in VOID_TAGS:
            return
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if self._in_title:
            self._title_buf.append(data)
            return
        self.stack[-1].children.append(data)


def _is_junk(node):
    if node.tag in GENERIC_JUNK_TAGS:
        return True
    cls = node.attrs.get("class", "")
    ident = node.attrs.get("id", "")
    return bool(GENERIC_JUNK_CLASS.search(cls) or GENERIC_JUNK_CLASS.search(ident))


def _inline_text(node, skip_junk=True):
    """Text of a node, ignoring nested block elements (so a chapter <h1> that
    wraps a <p>[ ... words ]</p> doesn't leak the placeholder into the title)."""
    buf = []

    def walk(n, junk):
        for c in n.children:
            if isinstance(c, str):
                if not junk:
                    buf.append(c)
            elif c.tag in PARA_TAGS:
                continue
            else:
                j = junk or (skip_junk and _is_junk(c))
                if c.tag in ("br",):
                    if not j:
                        buf.append(" ")
                else:
                    walk(c, j)

    walk(node, skip_junk and _is_junk(node))
    return re.sub(r"\s+", " ", "".join(buf)).strip()


def _text_len(node):
    total = 0
    stack = [node]
    while stack:
        n = stack.pop()
        for c in n.children:
            if isinstance(c, str):
                total += len(c)
            else:
                stack.append(c)
    return total


def _count_p(node):
    n = 0
    stack = list(node.children)
    while stack:
        c = stack.pop()
        if isinstance(c, _Node):
            if _is_junk(c):
                continue
            if c.tag == "p":
                n += 1
            stack.extend(c.children)
    return n


def _find_title(root):
    """chapter-title-ish class first, then the first sane <h1>, then <title>."""
    class_re = re.compile(r"(chapter[-_]?title|entry-title|chaptername|chapter[-_]?name)", re.I)
    first_h1 = None
    stack = [root]
    while stack:
        n = stack.pop(0)
        for c in n.children:
            if not isinstance(c, _Node):
                continue
            cls = c.attrs.get("class", "") + " " + c.attrs.get("id", "")
            if class_re.search(cls):
                t = _inline_text(c)
                if t:
                    return t
            if c.tag == "h1" and first_h1 is None:
                t = _inline_text(c)
                if t and 3 < len(t) < 200:
                    first_h1 = t
            stack.append(c)
    return first_h1


def _pick_container(root):
    """Busiest paragraph container wins; falls back to the longest text block."""
    doc_len = max(_text_len(root), 1)
    best_p, best_text = None, None
    stack = [root]
    while stack:
        n = stack.pop()
        for c in n.children:
            if not isinstance(c, _Node) or _is_junk(c):
                continue
            if c.tag in ("div", "section", "article", "main", "td"):
                tl = _text_len(c)
                if tl > 200 and tl < 0.9 * doc_len:
                    pc = _count_p(c)
                    if pc >= 4 and (best_p is None or (pc, tl) > best_p[0]):
                        best_p = ((pc, tl), c)
                    if best_text is None or tl > best_text[0]:
                        best_text = (tl, c)
            stack.append(c)
    if best_p:
        return best_p[1]
    return best_text[1] if best_text else None


def _extract_blocks(node):
    blocks, buf = [], []

    def flush():
        text = re.sub(r"\s+", " ", "".join(buf)).strip()
        if text:
            blocks.append(text)
        buf.clear()

    def walk(n, junk):
        for c in n.children:
            if isinstance(c, str):
                if not junk:
                    buf.append(c)
                continue
            j = junk or _is_junk(c)
            if c.tag == "br":
                if not j:
                    buf.append("\n")
            elif c.tag in PARA_TAGS:
                flush()
                walk(c, j)
                flush()
            elif c.tag in ("em", "i"):
                if not j:
                    buf.append("*")
                walk(c, j)
                if not j:
                    buf.append("*")
            elif c.tag in ("strong", "b"):
                if not j:
                    buf.append("**")
                walk(c, j)
                if not j:
                    buf.append("**")
            else:
                walk(c, j)

    walk(node, _is_junk(node))
    flush()
    return blocks


class GenericParser:
    """Site-agnostic extraction: locate the prose container, then read paragraphs.
    Used for sites we haven't profiled; validated by the word-count gates and the
    verify step, since a wrong container yields far too little text."""

    def __init__(self):
        self.builder = _DomBuilder()

    def feed(self, doc):
        self.builder.feed(doc)

    def finish(self):
        root = self.builder.root
        title = _find_title(root)
        if not title:
            title = re.sub(r"\s+", " ", "".join(self.builder._title_buf)).strip()
        container = _pick_container(root)
        blocks = _extract_blocks(container) if container is not None else []
        blocks = [b for b in blocks if not GENERIC_JUNK_TEXT.match(b)]
        return title or "", blocks


# ------------------------------------------------------------------ entry point

def parse_document(doc_html, num=None, profile="novelphoenix", min_words=300):
    """Return (title, paragraphs) for a chapter page."""
    if profile == "auto":
        t, b = parse_document(doc_html, num, "novelphoenix", min_words)
        if sum(len(x.split()) for x in b) >= min_words:
            return t, b
        return parse_document(doc_html, num, "generic", min_words)

    if profile == "novelphoenix":
        p = NovelPhoenixParser()
        p.feed(doc_html)
        title, blocks = p.finish()
    elif profile == "generic":
        g = GenericParser()
        g.feed(doc_html)
        title, blocks = g.finish()
    else:
        raise ValueError(f"unknown profile {profile!r}")

    if not title:
        m = re.search(r"<title>(.*?)</title>", doc_html, re.S | re.I)
        if m:
            title = re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()
    if num is not None:
        title = clean_title(num, title)
    blocks = _clean_blocks(blocks)
    # Some sites repeat "<Site> - Chapter N - N: Title" as a block inside the prose
    # area (the generic profile picks it up where the profiled one hard-stops).
    # Drop any block that carries no information beyond the title itself.
    if title:
        blocks = [b for b in blocks if not (len(b) < 220 and clean_title(num, b) == title)]
    return title, blocks


def to_markdown(num, title, blocks, source, fetched):
    head = ["---", f"chapter: {num}",
            "title: " + (title.replace('"', "'") if title else ""),
            f"source: {source}", f"fetched: {fetched}", "---", "",
            f"# Chapter {num}" + (f" — {title}" if title else ""), ""]
    return "\n".join(head) + "\n\n".join(blocks) + "\n"


if __name__ == "__main__":
    import sys
    prof = "auto"
    args = sys.argv[1:]
    if args and args[0] in ("novelphoenix", "generic", "auto"):
        prof = args.pop(0)
    for path in args:
        n = int(re.search(r"(\d+)", path.split("ri")[-1]).group(1))
        doc = open(path, encoding="utf-8").read()
        for probe in (prof,) if prof != "auto" else ("novelphoenix", "generic"):
            t, b = parse_document(doc, n, probe)
            print(f"=== {path} [{probe}] title={t!r} blocks={len(b)} "
                  f"words={sum(len(x.split()) for x in b)}")
            if b:
                print("    first:", b[0][:80])
                print("    last :", b[-1][:80])
