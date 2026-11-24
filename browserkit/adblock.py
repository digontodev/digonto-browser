"""Digonto Ad Blocker - built in, on by default, can be switched off (Extensions page) or paused per site.

Filter lists: EasyList + EasyPrivacy (the EasyList authors; GPLv3+ / CC BY-SA 3.0+, see assets/filters/LICENCE.txt).
What it uses from them:
  - network rules anchored to a domain ("||ads.example.com^", "||example.com/banners/", options $third-party / $script ...)
  - exceptions ("@@||...")
  - generic element hiding ("##.ad-box") - injected as one forgiving CSS rule per chunk
Rules with options it does not understand are skipped (better to show an ad than to break a site).
"""
import os
import re
import threading
import time

from PySide6.QtCore import QObject, Signal
from PySide6.QtWebEngineCore import QWebEngineUrlRequestInfo, QWebEngineUrlRequestInterceptor

from . import net, store

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLED = os.path.join(os.path.dirname(HERE), "assets", "filters")
LISTS = {                                      # file -> source (updated weekly into the user's data folder)
    "easylist_adservers.txt": "easylist/easylist_adservers.txt",
    "easylist_thirdparty.txt": "easylist/easylist_thirdparty.txt",
    "easylist_general_hide.txt": "easylist/easylist_general_hide.txt",
    "easyprivacy_trackingservers.txt": "easyprivacy/easyprivacy_trackingservers.txt",
    "easyprivacy_thirdparty.txt": "easyprivacy/easyprivacy_thirdparty.txt",
    "easyprivacy_trackingservers_thirdparty.txt": "easyprivacy/easyprivacy_trackingservers_thirdparty.txt",
    "easylist_general_block.txt": "easylist/easylist_general_block.txt",
    "easyprivacy_general.txt": "easyprivacy/easyprivacy_general.txt",
}
SOURCE = "https://raw.githubusercontent.com/easylist/easylist/master/"
UPDATE_EVERY = 7 * 86400

RT = QWebEngineUrlRequestInfo.ResourceType
TYPE_OF = {
    RT.ResourceTypeScript: "script", RT.ResourceTypeImage: "image", RT.ResourceTypeStylesheet: "stylesheet",
    RT.ResourceTypeSubFrame: "subdocument", RT.ResourceTypeXhr: "xmlhttprequest", RT.ResourceTypePing: "ping",
    RT.ResourceTypeMedia: "media", RT.ResourceTypeFontResource: "font", RT.ResourceTypeObject: "object",
}
KNOWN_TYPES = {"script", "image", "stylesheet", "subdocument", "xmlhttprequest", "ping", "media", "font", "object", "other"}
# second-level parts that are not a site on their own (co.uk, com.au ...): enough for "is this the same site?"
_SLD = {"co", "com", "net", "org", "gov", "edu", "ac", "or", "ne", "go"}


def site_of(host):
    """example.co.uk / sub.example.com -> example.co.uk / example.com"""
    parts = (host or "").lower().strip(".").split(".")
    if len(parts) >= 3 and parts[-2] in _SLD and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _trie_regex(words):
    """many plain strings -> one compact regex (a trie), much faster than 'any(w in url)'"""
    trie = {}
    for w in words:
        node = trie
        for ch in w:
            node = node.setdefault(ch, {})
        node[""] = True

    def build(node):
        alts, end = [], "" in node
        for ch in sorted(k for k in node if k):
            alts.append(re.escape(ch) + build(node[ch]))
        if not alts:
            return ""
        body = alts[0] if len(alts) == 1 and not end else "(?:" + "|".join(alts) + ")"
        return body + ("?" if end and alts else "")
    return re.compile(build(trie)) if trie else None


def _pattern(path):
    """EasyList path pattern -> regex ( * = anything, ^ = separator or end )"""
    rx = re.escape(path).replace(r"\*", ".*").replace(r"\^", r"(?:[^\w.%-]|$)")
    return re.compile(rx)


# YouTube shows its video ads from its own servers, so blocking addresses is not enough. Like uBlock Origin's
# scriptlets: take the ad data out of the player's data before the player reads it, hide ad boxes, and as a last
# resort skip an ad that still starts (muted, to its end, press "Skip").
YOUTUBE_JS = r"""(function () {
  var h = location.hostname.toLowerCase();
  if (!/(^|\.)(youtube\.com|youtube-nocookie\.com)$/.test(h)) return;
  var allow = __ALLOW__;
  for (var i = 0; i < allow.length; i++) { if (h === allow[i] || h.endsWith('.' + allow[i])) return; }
  if (window.__digontoYT) return; window.__digontoYT = true;
  var KEYS = ['adPlacements', 'playerAds', 'adSlots', 'adBreakHeartbeatParams', 'adBreakParams'];
  function prune(o, depth) {
    if (!o || typeof o !== 'object' || (depth || 0) > 4) return o;
    for (var k = 0; k < KEYS.length; k++) { if (KEYS[k] in o) { try { delete o[KEYS[k]]; } catch (e) {} } }
    if (o.playerResponse) prune(o.playerResponse, (depth || 0) + 1);
    if (Array.isArray(o)) for (var j = 0; j < o.length && j < 20; j++) prune(o[j], (depth || 0) + 1);
    return o;
  }
  function hasAds(o) { return o && typeof o === 'object' && (o.adPlacements || o.playerAds || o.adSlots || o.playerResponse || Array.isArray(o)); }
  var P = JSON.parse;
  JSON.parse = function () { var r = P.apply(this, arguments); try { if (hasAds(r)) prune(r, 0); } catch (e) {} return r; };
  var J = Response.prototype.json;
  Response.prototype.json = function () { return J.call(this).then(function (r) { try { if (hasAds(r)) prune(r, 0); } catch (e) {} return r; }); };
  ['ytInitialPlayerResponse', 'ytInitialData'].forEach(function (name) {
    var held;
    try { Object.defineProperty(window, name, { configurable: true, get: function () { return held; },
                                               set: function (v) { held = prune(v, 0); } }); } catch (e) {}
  });
  var css = '#masthead-ad, ytd-ad-slot-renderer, ytd-in-feed-ad-layout-renderer, ytd-banner-promo-renderer, ' +
    'ytd-promoted-sparkles-web-renderer, ytd-promoted-video-renderer, ytd-display-ad-renderer, ytd-companion-slot-renderer, ' +
    'ytd-player-legacy-desktop-watch-ads-renderer, #player-ads, .ytp-ad-overlay-container, .ytp-ad-image-overlay, ' +
    'ytd-rich-item-renderer:has(> #content > ytd-ad-slot-renderer), ytd-merch-shelf-renderer, ytd-statement-banner-renderer, ' +
    'ytd-search-pyv-renderer, .ytd-mealbar-promo-renderer, #panels > ytd-engagement-panel-section-list-renderer[target-id="engagement-panel-ads"]' +
    '{display:none!important}';
  function addCss() { var st = document.createElement('style'); st.textContent = css; (document.head || document.documentElement).appendChild(st); }
  if (document.documentElement) addCss(); else document.addEventListener('DOMContentLoaded', addCss);
  setInterval(function () {
    var player = document.querySelector('.html5-video-player');
    if (!player || !player.classList.contains('ad-showing')) return;
    var v = player.querySelector('video');
    if (v) { v.muted = true; if (isFinite(v.duration) && v.duration > 0) v.currentTime = v.duration; }
    var skip = document.querySelector('.ytp-skip-ad-button, .ytp-ad-skip-button, .ytp-ad-skip-button-modern, .ytp-ad-skip-button-container button');
    if (skip) skip.click();
  }, 300);
})();"""


def youtube_js(allow_sites):
    import json as _json
    return YOUTUBE_JS.replace("__ALLOW__", _json.dumps(sorted(allow_sites)))


class Rule:
    __slots__ = ("path", "third", "types", "not_types", "domains", "not_domains")

    def __init__(self, path, third, types, not_types, domains, not_domains):
        self.path, self.third, self.types, self.not_types = path, third, types, not_types
        self.domains, self.not_domains = domains, not_domains

    def matches(self, rest, third_party, rtype, first_site):
        if self.third is not None and self.third != third_party:
            return False
        if self.types and rtype not in self.types:
            return False
        if rtype in self.not_types:
            return False
        if self.domains and first_site not in self.domains:
            return False
        if first_site in self.not_domains:
            return False
        return self.path is None or bool(self.path.match(rest))


class Engine:
    def __init__(self):
        self.block = {}                # domain -> [Rule]
        self.allow = {}
        self.hide = []                 # generic CSS selectors
        self.generic = []              # plain strings that block wherever they appear ("/fbevents.js", "/adsbygoogle.")
        self.generic_allow = []
        self.generic_rx = self.generic_allow_rx = None
        self.loaded_from = ""
        self.count_rules = 0

    def parse_line(self, line):
        line = line.strip()
        if not line or line.startswith(("!", "[")):
            return
        if "##" in line:
            a, sel = line.split("##", 1)
            if not a and sel and not sel.startswith(("+js", "^")) and ":-abp-" not in sel:
                self.hide.append(sel)
            return
        if "#@#" in line or "#?#" in line or "#$#" in line:
            return
        exc = line.startswith("@@")
        if exc:
            line = line[2:]
        if not line.startswith("||"):          # general rules: a plain piece of text without options
            if "$" in line or "*" in line or "^" in line or line.startswith("|") or len(line) < 5 or line.startswith("/") and line.endswith("/") and len(line) > 2 and not line[1:-1].count("/") and line[1:-1].isalnum():
                return
            if line.startswith("/") and line.endswith("/") and any(c in line for c in "()[]\\?+{}"):
                return                         # a regex rule: skip
            (self.generic_allow if exc else self.generic).append(line.lower())
            return
        body, _, opts = line[2:].partition("$")
        third, types, not_types, domains, not_domains = None, set(), set(), set(), set()
        for o in filter(None, opts.split(",")):
            neg = o.startswith("~")
            name = o[1:] if neg else o
            if name in ("third-party", "3p"):
                third = not neg
            elif name in ("first-party", "1p"):
                third = neg
            elif name in KNOWN_TYPES:
                (not_types if neg else types).add(name)
            elif name.startswith("domain="):
                for d in name[7:].split("|"):
                    if d.endswith(".*"):
                        continue
                    (not_domains if d.startswith("~") else domains).add(d.lstrip("~").lower())
            elif name in ("important", "match-case", "all"):
                continue
            else:                              # $popup, $document, $csp, $redirect, $removeparam, ... -> skip the rule
                return
        m = re.match(r"^([a-z0-9.\-_]+)(.*)$", body, re.I)
        if not m:
            return
        domain, rest = m.group(1).lower().strip("."), m.group(2)
        if not domain or "*" in domain:
            return
        path = None
        if rest and rest not in ("^", "^|", "|"):
            path = _pattern(rest.rstrip("|"))
        rule = Rule(path, third, frozenset(types), frozenset(not_types), frozenset(domains), frozenset(not_domains))
        (self.allow if exc else self.block).setdefault(domain, []).append(rule)
        self.count_rules += 1

    def load(self, folder):
        for name in LISTS:
            p = os.path.join(folder, name)
            if not os.path.isfile(p):
                p = os.path.join(BUNDLED, name)
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        self.parse_line(line)
            except OSError:
                pass
        self.generic_rx = _trie_regex(self.generic)
        self.generic_allow_rx = _trie_regex(self.generic_allow)
        self.loaded_from = folder

    def _rules(self, table, host):
        parts = host.split(".")
        for i in range(len(parts) - 1):
            d = ".".join(parts[i:])
            r = table.get(d)
            if r:
                yield d, r

    def should_block(self, host, url, rtype, first_host):
        """host = request host; url = full address; first_host = the site the page belongs to"""
        if not host:
            return False
        first_site = site_of(first_host)
        third = site_of(host) != first_site if first_host else True
        hit = False
        low = url.lower()
        if third and self.generic_rx is not None and self.generic_rx.search(low):
            hit = not (self.generic_allow_rx is not None and self.generic_allow_rx.search(low))
            if hit:
                return not any(any(r.matches(url.split(d, 1)[1] if d in url else "", third, rtype, first_site) for r in rules)
                               for d, rules in self._rules(self.allow, host))
        for d, rules in self._rules(self.block, host):
            rest = url.split(d, 1)[1] if d in url else ""
            if any(r.matches(rest, third, rtype, first_site) for r in rules):
                hit = True
                break
        if not hit:
            return False
        for d, rules in self._rules(self.allow, host):
            rest = url.split(d, 1)[1] if d in url else ""
            if any(r.matches(rest, third, rtype, first_site) for r in rules):
                return False
        return True

    def css(self, chunk=400):
        """generic element hiding as forgiving :is() rules (one bad selector does not cancel the rest)"""
        out = []
        sels = [s.replace("\\", "\\\\") for s in self.hide if "{" not in s and "}" not in s]
        for i in range(0, len(sels), chunk):
            out.append(":is(" + ",".join(sels[i:i + chunk]) + "){display:none!important}")
        return "\n".join(out)


class Blocker(QObject):
    """the part the browser talks to"""
    counted = Signal(str)                      # first-party host whose count changed (sent from the network thread)
    reloaded = Signal()

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.engine = Engine()
        self.counts = {}                      # first-party host -> blocked on the current page
        self.total = int(settings.get("adblock_total", 0) or 0)
        self.folder = os.path.join(store.data_dir(), "filters")
        os.makedirs(self.folder, exist_ok=True)
        t0 = time.time()
        self.engine.load(self.folder)
        self.load_time = time.time() - t0
        self._css = None
        self.interceptors = []

    # ---- state
    @property
    def enabled(self):
        return bool(self.settings.get("adblock_enabled", True))

    def set_enabled(self, on):
        self.settings["adblock_enabled"] = bool(on)

    def paused_on(self, host):
        return site_of(host) in set(self.settings.get("adblock_allow", []) or [])

    def set_paused(self, host, paused):
        allow = set(self.settings.get("adblock_allow", []) or [])
        s = site_of(host)
        (allow.add if paused else allow.discard)(s)
        self.settings["adblock_allow"] = sorted(allow)

    def active_for(self, host):
        return self.enabled and not self.paused_on(host)

    def css(self):
        if self._css is None:
            self._css = self.engine.css()
        return self._css

    def reset_count(self, host):
        self.counts[host] = 0

    def note(self, first_host):
        self.counts[first_host] = self.counts.get(first_host, 0) + 1
        self.total += 1
        self.counted.emit(first_host)

    def save_total(self):
        self.settings["adblock_total"] = self.total

    # ---- lists
    def last_update(self):
        times = [os.path.getmtime(os.path.join(self.folder, n)) for n in LISTS if os.path.isfile(os.path.join(self.folder, n))]
        return max(times) if times else 0.0

    def update_lists(self, force=False, done=None):
        """download the newest lists in the background (weekly, or now when asked)"""
        if not force and time.time() - self.last_update() < UPDATE_EVERY:
            return False

        state = {"left": len(LISTS), "ok": 0}

        def reload_in_background():
            def run():
                e = Engine()
                e.load(self.folder)
                self.engine = e
                self._css = None
                self.reloaded.emit()                        # queued to the main thread
            threading.Thread(target=run, daemon=True).start()

        def got(name, data, err):
            if data and len(data) > 200 and not data.lstrip()[:15].lower().startswith((b"<!doctype", b"<html", b"<")):
                try:
                    tmp = os.path.join(self.folder, name + ".tmp")
                    with open(tmp, "wb") as f:
                        f.write(data)
                    os.replace(tmp, os.path.join(self.folder, name))
                    state["ok"] += 1
                except OSError:
                    pass
            state["left"] -= 1
            if state["left"] == 0:
                if state["ok"]:
                    reload_in_background()
                if done:
                    done(state["ok"])
        queue = list(LISTS.items())                         # one after the other, through Qt (system certificates)

        def nxt():
            if queue:
                name, src = queue.pop(0)
                net.get(SOURCE + src, lambda d, e, n=name: (got(n, d, e), nxt()), 60000, "DigontoBrowser")
        nxt()
        return True


class Interceptor(QWebEngineUrlRequestInterceptor):
    """runs for every request on the network thread: keep it quick"""

    def __init__(self, blocker):
        super().__init__()
        self.b = blocker

    def interceptRequest(self, info):
        b = self.b
        try:
            if not b.enabled:
                return
            rt = info.resourceType()
            if rt == RT.ResourceTypeMainFrame:
                return
            first = info.firstPartyUrl().host()
            if first and b.paused_on(first):
                return
            u = info.requestUrl()
            scheme = u.scheme()
            if scheme not in ("http", "https", "ws", "wss"):
                return
            if b.engine.should_block(u.host().lower(), u.toString(), TYPE_OF.get(rt, "other"), first.lower()):
                info.block(True)
                b.note(first)
        except Exception:                      # never break loading because of the blocker
            pass
