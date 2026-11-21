"""The browser's own pages, served from digonto:// (new tab, and later more)."""
import base64
import html
import json
import os
from urllib.parse import urlsplit

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtWebEngineCore import QWebEngineUrlRequestJob, QWebEngineUrlScheme, QWebEngineUrlSchemeHandler

from .urls import ENGINES

SCHEME = b"digonto"
HERE = os.path.dirname(os.path.abspath(__file__))


def register_scheme():
    """must run before the QApplication is made"""
    s = QWebEngineUrlScheme(SCHEME)
    s.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    s.setFlags(QWebEngineUrlScheme.Flag.SecureScheme | QWebEngineUrlScheme.Flag.LocalScheme
               | QWebEngineUrlScheme.Flag.LocalAccessAllowed | QWebEngineUrlScheme.Flag.ContentSecurityPolicyIgnored)
    QWebEngineUrlScheme.registerScheme(s)


def _logo_uri():
    p = os.path.join(os.path.dirname(HERE), "assets", "digonto-browser-128.png")
    try:
        with open(p, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode()
    except OSError:
        return ""


def _host(url):
    try:
        return urlsplit(url).hostname or url
    except ValueError:
        return url


NEWTAB_CSS = """
:root{--ink:#1B1040;--sub:#6E6475;--line:#E4DCEE;--bg:#F6F2FA;--pink:#FF6F8E;--amber:#FFB05A;}
*{box-sizing:border-box} html,body{margin:0;height:100%}
body{font-family:-apple-system,"Segoe UI",Roboto,"Noto Sans","Helvetica Neue",Arial,sans-serif;background:var(--bg);color:var(--ink);
     display:flex;flex-direction:column;align-items:center}
.wrap{width:min(720px,92vw);margin-top:12vh;display:flex;flex-direction:column;align-items:center}
.logo{width:88px;height:88px;border-radius:22px;box-shadow:0 8px 28px rgba(90,42,134,.25)}
h1{font-weight:700;font-size:28px;margin:18px 0 4px;letter-spacing:.2px}
h1 span{background:linear-gradient(90deg,var(--pink),var(--amber));-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{color:var(--sub);font-size:14px;margin-bottom:26px}
form{width:100%;display:flex;background:#fff;border:1px solid var(--line);border-radius:28px;padding:6px 6px 6px 20px;
     box-shadow:0 4px 18px rgba(27,16,64,.06)}
form:focus-within{border-color:var(--pink);box-shadow:0 4px 22px rgba(255,111,142,.22)}
input{flex:1;border:0;outline:0;font-size:17px;background:transparent;color:var(--ink)}
button{border:0;border-radius:22px;padding:10px 22px;font-size:15px;font-weight:600;color:#2A1241;cursor:pointer;
       background:linear-gradient(90deg,var(--pink),var(--amber))}
.engine{color:var(--sub);font-size:12px;margin-top:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(112px,1fr));gap:14px;width:100%;margin-top:40px}
.tile{display:flex;flex-direction:column;align-items:center;gap:8px;padding:14px 8px;border-radius:16px;text-decoration:none;color:var(--ink);
      background:#fff;border:1px solid var(--line);transition:transform .12s,box-shadow .12s}
.tile:hover{transform:translateY(-2px);box-shadow:0 6px 18px rgba(27,16,64,.10)}
.tile img{width:32px;height:32px;border-radius:8px}
.tile .t{font-size:12.5px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.letter{width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-weight:700;color:#fff;
        background:linear-gradient(135deg,#5A2A86,var(--pink))}
h2{font-size:13px;font-weight:600;color:var(--sub);align-self:flex-start;margin:34px 0 -26px 4px;text-transform:uppercase;letter-spacing:.8px}
@media (prefers-color-scheme: dark){
 :root{--ink:#EDE6F4;--sub:#A99FB8;--line:#3A2E52;--bg:#17112A}
 form,.tile{background:#221A3A}
}
"""


def newtab_html(settings, history, private=False):
    name, tmpl = ENGINES.get(settings["engine"], ENGINES["duckduckgo"])
    links = list(settings["quick_links"] or [])
    seen = {l["url"] for l in links}
    top = [] if private else [(u, t) for u, t in history.top(12) if u not in seen][:8]

    def tile(url, title):
        h = _host(url)
        letter = html.escape((title or h or "?").strip()[:1].upper())
        fav = f"https://{h}/favicon.ico" if url.startswith(("http:", "https:")) else ""
        img = (f'<img src="{html.escape(fav)}" onerror="this.outerHTML=\'<div class=letter>{letter}</div>\'">' if fav
               else f'<div class="letter">{letter}</div>')
        return (f'<a class="tile" href="{html.escape(url)}" title="{html.escape(url)}">{img}'
                f'<span class="t">{html.escape(title or h)}</span></a>')

    quick = "".join(tile(l["url"], l.get("title", "")) for l in links)
    often = "".join(tile(u, t) for u, t in top)
    title = "Private window" if private else "New tab"
    sub = ("Nothing you do in this window is saved: no history, no cookies after you close it." if private
           else "Search the web or type an address")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>{NEWTAB_CSS}</style></head>
<body><div class="wrap">
<img class="logo" src="{_logo_uri()}" alt="">
<h1>Digonto <span>Browser</span></h1>
<div class="sub">{html.escape(sub)}</div>
<form id="f"><input id="q" autofocus autocomplete="off" placeholder="Search with {html.escape(name)}"><button>Search</button></form>
<div class="engine">Change the search engine in Settings</div>
<div class="grid">{quick}</div>
{'<h2>Often visited</h2><div class="grid">' + often + '</div>' if often else ''}
</div>
<script>
const T = {json.dumps(tmpl)};
document.getElementById('f').addEventListener('submit', e => {{
  e.preventDefault(); const q = document.getElementById('q').value.trim(); if (!q) return;
  const looks = /^[^\\s]+\\.[a-z]{{2,}}(\\/.*)?$/i.test(q) && !q.includes(' ');
  location.href = looks ? (q.match(/^[a-z]+:/i) ? q : 'https://' + q) : T.replace('{{}}', encodeURIComponent(q));
}});
</script></body></html>"""


class Handler(QWebEngineUrlSchemeHandler):
    def __init__(self, settings, history, private=False, parent=None):
        super().__init__(parent)
        self.settings, self.history, self.private = settings, history, private
        self._keep = []

    def requestStarted(self, job):
        host = job.requestUrl().host()
        if host in ("newtab", ""):
            body = newtab_html(self.settings, self.history, self.private).encode("utf-8")
        else:
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            return
        buf = QBuffer(job)
        buf.setData(QByteArray(body))
        buf.open(QIODevice.ReadOnly)
        job.reply(b"text/html", buf)
