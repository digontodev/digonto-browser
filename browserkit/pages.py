"""The browser's own pages, served from digonto:// (new tab, and later more)."""
import base64
import html
import json
import os
from urllib.parse import parse_qsl, urlsplit

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtWebEngineCore import QWebEngineUrlRequestJob, QWebEngineUrlScheme, QWebEngineUrlSchemeHandler

from .urls import ENGINES
from . import __version__

SCHEME = b"digonto"
HERE = os.path.dirname(os.path.abspath(__file__))


def register_scheme():
    """must run before the QApplication is made"""
    s = QWebEngineUrlScheme(SCHEME)
    s.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    s.setFlags(QWebEngineUrlScheme.Flag.SecureScheme | QWebEngineUrlScheme.Flag.LocalScheme
               | QWebEngineUrlScheme.Flag.LocalAccessAllowed | QWebEngineUrlScheme.Flag.ContentSecurityPolicyIgnored
               | QWebEngineUrlScheme.Flag.CorsEnabled | QWebEngineUrlScheme.Flag.FetchApiAllowed)
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


SETTINGS_CSS = """
:root{--ink:#1B1040;--sub:#6E6475;--line:#E4DCEE;--bg:#F6F2FA;--card:#fff;--pink:#FF6F8E;--amber:#FFB05A;}
*{box-sizing:border-box} html,body{margin:0}
body{font-family:-apple-system,"Segoe UI",Roboto,"Noto Sans","Helvetica Neue",Arial,sans-serif;background:var(--bg);color:var(--ink)}
.wrap{max-width:760px;margin:0 auto;padding:34px 22px 60px}
header{display:flex;align-items:center;gap:14px;margin-bottom:22px}
header img{width:46px;height:46px;border-radius:12px}
h1{font-size:26px;margin:0}
h1 span{background:linear-gradient(90deg,var(--pink),var(--amber));-webkit-background-clip:text;background-clip:text;color:transparent}
nav{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:18px}
nav a{padding:6px 12px;border-radius:16px;color:var(--ink);text-decoration:none;font-size:13px;background:var(--card);border:1px solid var(--line)}
nav a:hover{border-color:var(--pink)}
section{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:6px 20px;margin-bottom:18px}
h2{font-size:15px;margin:16px 0 4px}
.row{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:13px 0;border-top:1px solid var(--line)}
.row:first-of-type{border-top:0}
.row .t{font-size:14px} .row .d{font-size:12px;color:var(--sub);margin-top:2px}
select,input[type=text]{font:inherit;font-size:13px;padding:7px 10px;border-radius:8px;border:1px solid #D0C4E1;background:var(--card);color:var(--ink);min-width:220px}
button{font:inherit;font-size:13px;padding:7px 14px;border-radius:8px;border:1px solid #D0C4E1;background:var(--card);color:var(--ink);cursor:pointer}
button:hover{border-color:var(--pink)}
button.primary{border:0;color:#2A1241;font-weight:600;background:linear-gradient(90deg,var(--pink),var(--amber))}
.switch{position:relative;width:42px;height:24px;flex:none}
.switch input{opacity:0;width:0;height:0}
.switch span{position:absolute;inset:0;border-radius:12px;background:#D8CFE4;transition:.15s;cursor:pointer}
.switch span:before{content:"";position:absolute;width:18px;height:18px;left:3px;top:3px;border-radius:50%;background:#fff;transition:.15s}
.switch input:checked+span{background:linear-gradient(90deg,var(--pink),var(--amber))}
.switch input:checked+span:before{transform:translateX(18px)}
.checks{display:flex;flex-direction:column;gap:8px;padding:6px 0 4px;font-size:14px}
.saved{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);background:#1B1040;color:#fff;padding:8px 16px;border-radius:18px;
       font-size:13px;opacity:0;transition:.2s;pointer-events:none}
.saved.on{opacity:1}
.folder{display:flex;gap:8px;align-items:center}
.folder input{min-width:260px}
.small{font-size:12px;color:var(--sub)}
@media (prefers-color-scheme: dark){
 :root{--ink:#EDE6F4;--sub:#A99FB8;--line:#3A2E52;--bg:#17112A;--card:#221A3A}
 .switch span{background:#4A3D66}
}
"""


def settings_html(settings, default_dir=""):
    def opts(pairs, cur):
        return "".join(f'<option value="{html.escape(str(k))}"{" selected" if str(k) == str(cur) else ""}>{html.escape(v)}</option>'
                       for k, v in pairs)

    def toggle(key, title, desc=""):
        on = " checked" if settings[key] else ""
        return (f'<div class="row"><div><div class="t">{title}</div><div class="d">{desc}</div></div>'
                f'<label class="switch"><input type="checkbox" data-k="{key}"{on}><span></span></label></div>')

    engines = opts([(k, v[0]) for k, v in ENGINES.items()], settings["engine"])
    startup = opts([("restore", "Open the tabs from last time"), ("newtab", "Open a new tab")], settings["startup"])
    zooms = opts([(z, f"{round(z * 100)} %") for z in (0.75, 0.9, 1.0, 1.1, 1.25, 1.5)], settings["default_zoom"])
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Settings</title><style>{SETTINGS_CSS}</style></head>
<body><div class="wrap">
<header><img src="{_logo_uri()}" alt=""><h1>Settings <span>· Digonto Browser</span></h1></header>
<nav><a href="#search">Search</a><a href="#start">On start</a><a href="#downloads">Downloads</a><a href="#privacy">Privacy</a>
<a href="#look">Look</a><a href="#about">About</a></nav>

<h2 id="search">Search</h2><section>
<div class="row"><div><div class="t">Search engine</div><div class="d">Used in the address bar and on the new tab page</div></div>
<select data-k="engine">{engines}</select></div></section>

<h2 id="start">On start</h2><section>
<div class="row"><div><div class="t">When Digonto Browser opens</div></div><select data-k="startup">{startup}</select></div></section>

<h2 id="downloads">Downloads</h2><section>
<div class="row"><div><div class="t">Save downloads to</div></div>
<div class="folder"><input type="text" id="folder" value="{html.escape(settings["download_dir"] or default_dir)}" placeholder="Downloads folder" readonly>
<button id="pick">Change …</button></div></div>
{toggle("ask_download", "Ask where to save each file", "Otherwise files go straight into the folder above")}
</section>

<h2 id="privacy">Privacy</h2><section>
{toggle("block_third_party_cookies", "Block third-party cookies", "Stops most tracking across websites. A few sites may sign you out.")}
<div class="row" style="display:block"><div class="t">Clear browsing data</div>
<div class="checks">
 <label>Time range <select id="range"><option value="3600">Last hour</option><option value="86400">Last 24 hours</option>
  <option value="604800">Last 7 days</option><option value="2419200">Last 4 weeks</option><option value="0" selected>All time</option></select></label>
 <label><input type="checkbox" id="c_hist" checked> Browsing history</label>
 <label><input type="checkbox" id="c_cache" checked> Cached pictures and files</label>
 <label><input type="checkbox" id="c_cookies"> Cookies and site data <span class="small">(signs you out of most sites)</span></label>
</div>
<button class="primary" id="clear">Clear data</button> <span class="small">Cookies and cache are always cleared for all time.</span>
</div></section>

<h2 id="look">Look</h2><section>
{toggle("show_bookmarks_bar", "Show the bookmarks bar", "Ctrl+Shift+B")}
<div class="row"><div><div class="t">Page zoom</div><div class="d">For every site; Ctrl + / Ctrl − change one site</div></div>
<select data-k="default_zoom">{zooms}</select></div></section>

<h2 id="about">About</h2><section>
<div class="row"><div><div class="t">Digonto Browser {html.escape(__version__)}</div>
<div class="d">Chromium engine (Qt WebEngine). Free and open source (AGPL-3.0). Your data stays on this computer.</div></div></div>
</section>
</div><div class="saved" id="saved">Saved</div>
<script>
const toast = (t) => {{ const s = document.getElementById('saved'); s.textContent = t || 'Saved'; s.classList.add('on');
  clearTimeout(window._t); window._t = setTimeout(() => s.classList.remove('on'), 1400); }};
const call = (path, args) => fetch('digonto://settings/' + path + '?' + new URLSearchParams(args)).then(r => r.json());
document.querySelectorAll('[data-k]').forEach(el => el.addEventListener('change', () => {{
  const v = el.type === 'checkbox' ? (el.checked ? '1' : '0') : el.value;
  call('set', {{k: el.dataset.k, v}}).then(() => toast());
}}));
document.getElementById('pick').onclick = () => call('pick', {{}}).then(r => {{ if (r.folder) {{ document.getElementById('folder').value = r.folder; toast(); }} }});
document.getElementById('clear').onclick = () => call('clear', {{
  since: document.getElementById('range').value, hist: +document.getElementById('c_hist').checked,
  cache: +document.getElementById('c_cache').checked, cookies: +document.getElementById('c_cookies').checked
}}).then(() => toast('Cleared'));
</script></body></html>"""


TYPES = {"engine": str, "startup": str, "default_zoom": float, "ask_download": bool, "block_third_party_cookies": bool,
         "show_bookmarks_bar": bool}


class Handler(QWebEngineUrlSchemeHandler):
    """digonto://newtab, digonto://settings (+ its small JSON calls: set, pick, clear)"""

    def __init__(self, settings, history, private=False, parent=None, actions=None):
        super().__init__(parent)
        self.settings, self.history, self.private = settings, history, private
        self.actions = actions or {}            # name -> fn(params) -> dict  (pick a folder, clear data, settings changed)

    def _reply(self, job, body, mime=b"text/html"):
        buf = QBuffer(job)
        buf.setData(QByteArray(body))
        buf.open(QIODevice.ReadOnly)
        job.reply(mime, buf)

    def requestStarted(self, job):
        url = job.requestUrl()
        host, path = url.host(), url.path().strip("/")
        if host in ("newtab", ""):
            self._reply(job, newtab_html(self.settings, self.history, self.private).encode("utf-8"))
        elif host == "settings" and not path:
            dd = self.actions["default_dir"]() if "default_dir" in self.actions else ""
            self._reply(job, settings_html(self.settings, dd).encode("utf-8"))
        elif host == "settings" and path in ("set", "pick", "clear"):
            initiator = job.initiator().toString() if hasattr(job, "initiator") else "digonto://settings"
            if not initiator.startswith("digonto://settings"):     # only the settings page itself may change settings
                job.fail(QWebEngineUrlRequestJob.Error.RequestDenied)
                return
            q = dict(parse_qsl(url.query()))
            out = {"ok": True}
            if path == "set" and q.get("k") in TYPES:
                k, t = q["k"], TYPES[q["k"]]
                self.settings[k] = (q.get("v") == "1") if t is bool else t(q.get("v", ""))
                if "changed" in self.actions:
                    self.actions["changed"](k)
            elif path in self.actions:                          # may open a dialog: answer after the event loop is free
                from PySide6.QtCore import QTimer
                fn = self.actions[path]

                def later(job=job, q=q, fn=fn):
                    res = {"ok": True}
                    try:
                        res.update(fn(q) or {})
                    except Exception as e:                       # noqa: BLE001 - reported to the page
                        res = {"ok": False, "error": str(e)}
                    self._reply(job, json.dumps(res).encode("utf-8"), b"application/json")
                QTimer.singleShot(0, later)
                return
            self._reply(job, json.dumps(out).encode("utf-8"), b"application/json")
        else:
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
