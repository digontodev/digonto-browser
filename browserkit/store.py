"""Everything the browser remembers: settings, bookmarks, history, the last session, zoom per site.

All of it lives in one folder per user (data_dir()). Private windows never write here.
"""
import json
import os
import sqlite3
import sys
import threading
import time

APP_DIR = "Digonto Browser"


def data_dir():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
        d = os.path.join(base, APP_DIR)
    elif sys.platform == "darwin":
        d = os.path.expanduser(f"~/Library/Application Support/{APP_DIR}")
    else:
        d = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "digonto-browser")
    os.makedirs(d, exist_ok=True)
    return d


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, data):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except OSError:
        pass


# ------------------------------------------------------------------------------------------------- settings --
DEFAULTS = {
    "engine": "duckduckgo",
    "startup": "restore",            # restore | newtab
    "ask_download": False,
    "download_dir": "",
    "block_third_party_cookies": True,
    "show_bookmarks_bar": True,
    "default_zoom": 1.0,
    "quick_links": [
        {"title": "Wikipedia", "url": "https://www.wikipedia.org"},
        {"title": "YouTube", "url": "https://www.youtube.com"},
        {"title": "GitHub", "url": "https://github.com"},
        {"title": "OpenStreetMap", "url": "https://www.openstreetmap.org"},
    ],
}


class Settings:
    def __init__(self):
        self.path = os.path.join(data_dir(), "settings.json")
        self.d = dict(DEFAULTS)
        self.d.update(_read(self.path, {}))

    def __getitem__(self, k):
        return self.d.get(k, DEFAULTS.get(k))

    def __setitem__(self, k, v):
        self.d[k] = v
        _write(self.path, self.d)

    def get(self, k, default=None):
        return self.d.get(k, DEFAULTS.get(k, default))


# ------------------------------------------------------------------------------------------------ bookmarks --
class Bookmarks:
    """a flat list with optional folder names: [{"title", "url", "folder", "time"}]; folder "" = bookmarks bar"""

    def __init__(self):
        self.path = os.path.join(data_dir(), "bookmarks.json")
        self.items = [b for b in _read(self.path, []) if isinstance(b, dict) and b.get("url")]
        self.listeners = []

    def save(self):
        _write(self.path, self.items)
        for fn in list(self.listeners):
            try:
                fn()
            except RuntimeError:            # a window that is gone
                self.listeners.remove(fn)

    def find(self, url):
        return next((b for b in self.items if b["url"] == url), None)

    def add(self, url, title, folder=""):
        if not self.find(url):
            self.items.append({"url": url, "title": title or url, "folder": folder, "time": time.time()})
            self.save()

    def remove(self, url):
        self.items = [b for b in self.items if b["url"] != url]
        self.save()

    def rename(self, url, title):
        b = self.find(url)
        if b:
            b["title"] = title
            self.save()

    def folders(self):
        return sorted({b.get("folder", "") for b in self.items} - {""})


# -------------------------------------------------------------------------------------------------- history --
class History:
    def __init__(self):
        self.path = os.path.join(data_dir(), "history.sqlite")
        self.lock = threading.Lock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS visits(url TEXT PRIMARY KEY, title TEXT, last REAL, count INTEGER)")
        self.db.execute("CREATE INDEX IF NOT EXISTS visits_last ON visits(last)")
        self.db.commit()

    def add(self, url, title):
        if not url or url.startswith(("digonto:", "about:", "data:", "view-source:", "devtools:", "chrome:")):
            return
        with self.lock:
            self.db.execute("INSERT INTO visits(url, title, last, count) VALUES(?,?,?,1) "
                            "ON CONFLICT(url) DO UPDATE SET title=CASE WHEN excluded.title<>'' THEN excluded.title ELSE title END, "
                            "last=excluded.last, count=count+1", (url, title or "", time.time()))
            self.db.commit()

    def set_title(self, url, title):
        if title:
            with self.lock:
                self.db.execute("UPDATE visits SET title=? WHERE url=?", (title, url))
                self.db.commit()

    def recent(self, limit=300, text=""):
        q = "SELECT url, title, last FROM visits"
        args = []
        if text:
            q += " WHERE url LIKE ? OR title LIKE ?"
            args = [f"%{text}%", f"%{text}%"]
        q += " ORDER BY last DESC LIMIT ?"
        args.append(limit)
        with self.lock:
            return self.db.execute(q, args).fetchall()

    def suggest(self, text, limit=8):
        """for the address bar: often-visited first, then recent"""
        if not text:
            return []
        with self.lock:
            return self.db.execute("SELECT url, title FROM visits WHERE url LIKE ? OR title LIKE ? "
                                   "ORDER BY count DESC, last DESC LIMIT ?", (f"%{text}%", f"%{text}%", limit)).fetchall()

    def top(self, limit=8):
        with self.lock:
            return self.db.execute("SELECT url, title FROM visits ORDER BY count DESC, last DESC LIMIT ?", (limit,)).fetchall()

    def delete(self, url):
        with self.lock:
            self.db.execute("DELETE FROM visits WHERE url=?", (url,))
            self.db.commit()

    def clear(self, since=0.0):
        with self.lock:
            self.db.execute("DELETE FROM visits WHERE last>=?", (since,))
            self.db.commit()


# ---------------------------------------------------------------------------------------- session and zoom --
def load_session():
    return _read(os.path.join(data_dir(), "session.json"), {})


def save_session(data):
    _write(os.path.join(data_dir(), "session.json"), data)


class Zoom:
    """zoom per site, like Chrome"""

    def __init__(self):
        self.path = os.path.join(data_dir(), "zoom.json")
        self.d = _read(self.path, {})

    def get(self, host, default=1.0):
        return float(self.d.get(host, default))

    def set(self, host, z):
        if not host:
            return
        if abs(z - 1.0) < 0.01:
            self.d.pop(host, None)
        else:
            self.d[host] = round(z, 2)
        _write(self.path, self.d)
