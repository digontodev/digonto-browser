"""What the address bar does with what you type: a web address, a file, or a search."""
import ipaddress
import os
import re
from urllib.parse import quote_plus

ENGINES = {
    "duckduckgo": ("DuckDuckGo", "https://duckduckgo.com/?q={}"),
    "startpage": ("Startpage", "https://www.startpage.com/do/search?q={}"),
    "brave": ("Brave Search", "https://search.brave.com/search?q={}"),
    "ecosia": ("Ecosia", "https://www.ecosia.org/search?q={}"),
    "google": ("Google", "https://www.google.com/search?q={}"),
    "bing": ("Bing", "https://www.bing.com/search?q={}"),
    "qwant": ("Qwant", "https://www.qwant.com/?q={}"),
}
NEWTAB = "digonto://newtab"

_TLD = re.compile(r"^[^\s/]+\.[a-z]{2,63}(:\d+)?(/.*)?$", re.I)
# endings that are files, not web domains ("notes.txt" is a search, not https://notes.txt)
_FILE_ENDS = {"txt", "pdf", "jpg", "jpeg", "png", "gif", "webp", "exe", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
              "mp3", "mp4", "wav", "html", "htm", "json", "csv", "svg", "dmg", "deb", "rar", "7z", "iso", "dll", "ini", "log"}
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)


def search_url(text, engine="duckduckgo"):
    tmpl = ENGINES.get(engine, ENGINES["duckduckgo"])[1]
    return tmpl.format(quote_plus(text))


def _is_host(s):
    host = s.split("/", 1)[0].split(":", 1)[0]
    if host == "localhost":
        return True
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def fix(text, engine="duckduckgo"):
    """the text from the address bar -> the address to open"""
    t = (text or "").strip()
    if not t:
        return NEWTAB
    if t.startswith("?"):                                   # "?word" = always search
        return search_url(t[1:].strip(), engine)
    if " " in t and not _SCHEME.match(t):
        return search_url(t, engine)
    if _SCHEME.match(t) and not re.match(r"^[^/]+:\d+(/|$)", t):   # has a scheme (but "host:8080" is not one)
        low = t.lower()
        if low.startswith(("http:", "https:", "file:", "digonto:", "view-source:", "about:", "data:", "ftp:", "mailto:")):
            return t
        if low.startswith("chrome:"):
            return t
        return search_url(t, engine)
    if t.startswith(("/", "~")) or re.match(r"^[a-zA-Z]:\\", t):
        p = os.path.expanduser(t)
        if os.path.exists(p):
            return "file:///" + os.path.abspath(p).replace("\\", "/").lstrip("/")
    if _is_host(t):
        return "http://" + t
    if _TLD.match(t):
        end = t.split("/", 1)[0].split(":", 1)[0].rsplit(".", 1)[-1].lower()
        if end in _FILE_ENDS and "/" not in t:
            return search_url(t, engine)
        return "https://" + t
    return search_url(t, engine)


def pretty(url):
    """how the address is shown when you are not typing"""
    if url.startswith(NEWTAB) or url in ("about:blank", ""):
        return ""
    return url
