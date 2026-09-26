"""The researcher: fetch an official documentation page and reduce it to plain text the writer can be held to."""

import re
from dataclasses import dataclass
from html.parser import HTMLParser

import httpx

MAX_SOURCE_CHARS = 5000
MIN_SOURCE_CHARS = 500
MAX_DOWNLOAD_BYTES = 2_000_000

_SKIP = {"script", "style", "nav", "header", "footer", "aside", "noscript", "svg", "form", "button", "select", "iframe"}
_BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "pre", "tr", "div", "section", "article", "br", "dt", "dd"}
_GENERIC = {"amazon", "aws", "service", "services", "deploy", "using", "with", "from", "and", "the", "for", "how",
            "setting", "create", "build", "creating", "building", "your", "managed", "cloud", "workflow", "pipeline"}


@dataclass(frozen=True)
class Source:
    text: str
    ok: bool
    note: str      # why it is not usable, or "" when ok


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip_depth += 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if len(line) > 1)


def _keywords(topic: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]{4,}", topic.lower()) if w not in _GENERIC]


def is_relevant(text: str, topic: str) -> bool:
    """Every significant word of the topic must appear (singular or plural). One shared word is not enough:
    a docs landing page mentions 'agent' and 'memory' without saying anything about agent memory."""
    lowered = text.lower()
    return all(re.sub(r"(es|s)$", "", word) in lowered for word in _keywords(topic))


def fetch_source(url: str, topic: str, client: httpx.Client | None = None) -> Source:
    """Fetch `url`; usable only if it is HTML, has enough text and actually mentions the topic."""
    own = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=15, headers={"User-Agent": "kb-agents/1.0 (documentation summarizer)"})
    try:
        if not url.startswith("https://"):
            return Source("", False, "not an https url")
        response = client.get(url)
        if response.status_code >= 400:
            return Source("", False, f"HTTP {response.status_code}")
        if "html" not in response.headers.get("content-type", "html"):
            return Source("", False, "not an HTML page")
        text = html_to_text(response.text[:MAX_DOWNLOAD_BYTES])
    except httpx.HTTPError as error:
        return Source("", False, f"unreachable ({type(error).__name__})")
    finally:
        if own:
            client.close()

    if len(text) < MIN_SOURCE_CHARS:
        return Source("", False, "page has too little text")
    if not is_relevant(text, topic):
        return Source("", False, "page does not mention the topic")
    return Source(text[:MAX_SOURCE_CHARS], True, "")
