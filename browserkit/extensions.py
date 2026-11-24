"""Chrome extensions (Manifest V3) through Qt WebEngine's extension manager (Qt 6.10+).

- install from a Chrome Web Store link (the .crx is downloaded and unpacked), a .crx / .zip file, or a folder
- switch on / off, remove; their buttons with pop-ups go in the top bar
Private windows can't run Chrome extensions (Qt does not load them into off-the-record profiles).
"""
import base64
import json
import os
import re
import struct
import tempfile
import zipfile

from PySide6.QtCore import QObject, Signal

from . import net, store

WEBSTORE_ID = re.compile(r"(?:chromewebstore\.google\.com|chrome\.google\.com/webstore)/detail/(?:[^/?#]+/)?([a-p]{32})")
CRX_URL = ("https://clients2.google.com/service/update2/crx?response=redirect&prodversion={ver}"
           "&acceptformat=crx2,crx3&x=id%3D{id}%26uc")

# popular Manifest V3 extensions to try; "tested" is set once they were tried in Digonto Browser
RECOMMENDED = [
    {"id": "eimadpbcbfnmbkopoojfekhnkhdbieeh", "name": "Dark Reader", "what": "Dark mode for every website"},
    {"id": "nngceckbapebfimnlniiiahkandclblb", "name": "Bitwarden", "what": "Free open-source password manager"},
    {"id": "aapbdbdomjkkjkaonfhkkikfgjllcleb", "name": "Google Translate", "what": "Translate words and pages"},
    {"id": "mnjggcdmjocbbbhaepdhchncahnbgone", "name": "SponsorBlock", "what": "Skip sponsor segments on YouTube"},
    {"id": "gebbhagfogifgggkldgodflihgfeippi", "name": "Return YouTube Dislike", "what": "Shows dislikes on YouTube again"},
    {"id": "ddkjiahejlhfcafbddmgiahcphecmpfh", "name": "uBlock Origin Lite", "what": "Another ad blocker (instead of the built-in one)"},
]


def webstore_id(text):
    m = WEBSTORE_ID.search(text or "")
    if m:
        return m.group(1)
    t = (text or "").strip()
    return t if re.fullmatch(r"[a-p]{32}", t) else None


def _varint(b, i):
    n = shift = 0
    while True:
        c = b[i]
        i += 1
        n |= (c & 0x7F) << shift
        shift += 7
        if c < 0x80:
            return n, i


def _fields(b):
    """a tiny protobuf reader: yields (field number, bytes) for the length-delimited fields"""
    i = 0
    while i < len(b):
        key, i = _varint(b, i)
        num, kind = key >> 3, key & 7
        if kind == 2:
            ln, i = _varint(b, i)
            yield num, b[i:i + ln]
            i += ln
        elif kind == 0:
            _, i = _varint(b, i)
        elif kind == 5:
            i += 4
        elif kind == 1:
            i += 8
        else:
            return


def id_from_key(pub):
    """Chrome's extension ID: the first 16 bytes of SHA-256 of the public key, written with the letters a-p"""
    import hashlib
    return "".join(chr(ord("a") + int(c, 16)) for c in hashlib.sha256(pub).hexdigest()[:32])


def crx_public_key(data, want_id=None):
    """the extension's own public key from a .crx (v3: protobuf header; v2: plain) - it fixes the extension's ID"""
    if data[:4] != b"Cr24":
        return None
    ver = struct.unpack("<I", data[4:8])[0]
    if ver == 2:
        pk = struct.unpack("<I", data[8:12])[0]
        return data[16:16 + pk]
    hlen = struct.unpack("<I", data[8:12])[0]
    header = data[12:12 + hlen]
    keys = [k for num, proof in _fields(header) if num in (2, 3) for n2, k in _fields(proof) if n2 == 1]
    for k in keys:
        if want_id is None or id_from_key(k) == want_id:
            return k
    return keys[0] if keys and want_id is None else None


def add_key(zip_path, pub):
    """put "key" into manifest.json, so Chromium gives the extension its real Web Store ID"""
    tmp = zip_path + ".tmp"
    with zipfile.ZipFile(zip_path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "manifest.json":
                m = json.loads(data.decode("utf-8-sig"))
                m.setdefault("key", base64.b64encode(pub).decode())
                data = json.dumps(m, ensure_ascii=False, indent=1).encode("utf-8")
            zout.writestr(item, data)
    os.replace(tmp, zip_path)


def crx_to_zip(crx_path, zip_path):
    """a .crx is a zip with a signed header in front; drop the header"""
    with open(crx_path, "rb") as f:
        data = f.read()
    if data[:4] == b"Cr24":
        ver = struct.unpack("<I", data[4:8])[0]
        if ver == 3:
            hlen = struct.unpack("<I", data[8:12])[0]
            body = data[12 + hlen:]
        elif ver == 2:
            pk, sig = struct.unpack("<II", data[8:16])
            body = data[16 + pk + sig:]
        else:
            raise ValueError(f"unknown .crx version {ver}")
    elif data[:2] == b"PK":
        body = data
    else:
        raise ValueError("this file is not a Chrome extension (.crx / .zip)")
    with open(zip_path, "wb") as f:
        f.write(body)
    zipfile.ZipFile(zip_path).testzip()
    try:
        pub = crx_public_key(data)
        if pub:
            with zipfile.ZipFile(zip_path) as z:
                has_key = "key" in json.loads(z.read("manifest.json").decode("utf-8-sig"))
            if not has_key:
                add_key(zip_path, pub)
    except Exception:                                   # noqa: BLE001 - without the key it still installs
        pass
    return zip_path


def manifest_of(folder):
    try:
        with open(os.path.join(folder, "manifest.json"), encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def check_zip(zip_path):
    """read the manifest before installing: Qt only takes Manifest V3"""
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        if "manifest.json" not in names:
            raise ValueError("no manifest.json in the extension")
        m = json.loads(z.read("manifest.json").decode("utf-8-sig"))
    if int(m.get("manifest_version", 0)) != 3:
        raise ValueError(f"this extension uses Manifest V{m.get('manifest_version', '?')}; only V3 extensions work "
                         "(Chrome itself also stopped running V2 extensions)")
    return m


def icon_uri(folder, manifest, want=48):
    """the best icon of an extension as a data: URI (for the extensions page and the top bar)"""
    icons = dict(manifest.get("icons") or {})
    act = manifest.get("action") or {}
    di = act.get("default_icon")
    if isinstance(di, dict):
        icons = {**di, **icons}
    elif isinstance(di, str):
        icons.setdefault("32", di)
    if not icons:
        return ""
    sizes = sorted(icons, key=lambda k: (abs(int(k) - want) if str(k).isdigit() else 999))
    rel = icons[sizes[0]]
    p = os.path.join(folder, rel.lstrip("/"))
    try:
        with open(p, "rb") as f:
            data = f.read()
    except OSError:
        return ""
    mime = "image/svg+xml" if p.endswith(".svg") else "image/png"
    return f"data:{mime};base64," + base64.b64encode(data).decode()


def webstore_id_of(manifest):
    """the Web Store ID an installed extension belongs to (from its key), if any"""
    k = manifest.get("key")
    if not k:
        return ""
    try:
        return id_from_key(base64.b64decode(k))
    except ValueError:
        return ""


class Extensions(QObject):
    changed = Signal()                     # list changed (installed, removed, switched)
    message = Signal(str)                  # a short message for the user ("Installed Dark Reader", "Could not ...")
    _install_zip = Signal(str, str)        # (zip path, name) -> install on the main thread

    def __init__(self, profile, chromium_version="140.0.0.0", settings=None):
        super().__init__()
        self.settings = settings
        self.marker = os.path.join(store.data_dir(), "extension-switching.txt")
        if os.path.exists(self.marker):                 # the last switch on/off crashed the browser
            try:
                os.remove(self.marker)
            except OSError:
                pass
            if settings is not None:
                settings["extensions_broken"] = True
        elif settings is not None and settings.get("extensions_broken") and not settings.get("extensions_fix_v2"):
            settings["extensions_broken"] = False       # the old crash came from how the profile was made: fixed in 0.2.2
        if settings is not None:
            settings["extensions_fix_v2"] = True
        self.mgr = profile.extensionManager()
        self.ver = chromium_version
        self.busy = set()
        self.mgr.installFinished.connect(self._installed)
        self.mgr.uninstallFinished.connect(lambda info: (self.changed.emit(), self.message.emit(f"Removed {info.name()}")))
        self.mgr.loadFinished.connect(lambda info: self.changed.emit())
        self._install_zip.connect(self._do_install)
        self.mgr.loadFinished.connect(self._restore)          # Qt loads every extension switched off: switch ours on again
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, self._restore_all)

    def _wanted(self):
        return set((self.settings.get("enabled_extensions", []) if self.settings is not None else []) or [])

    def _remember(self, ext_id, on):
        if self.settings is None:
            return
        w = self._wanted()
        (w.add if on else w.discard)(ext_id)
        self.settings["enabled_extensions"] = sorted(w)

    def _restore(self, info):
        if info.isInstalled() and info.id() in self._wanted() and not info.isEnabled() and info.isLoaded():
            from PySide6.QtCore import QTimer
            ext_id = info.id()
            QTimer.singleShot(0, lambda: self._enable_id(ext_id))

    def _restore_all(self):
        self.remove_duplicates()
        for info in self.mgr.extensions():
            self._restore(info)

    def remove_duplicates(self):
        """earlier versions could install the same extension more than once (no fixed ID): keep one of each"""
        groups = {}
        for info in self.mgr.extensions():
            if info.isInstalled():
                m = manifest_of(info.path()) if info.path() else {}
                groups.setdefault((info.name(), m.get("version", "")), []).append(info)
        wanted = self._wanted()
        removed = 0
        for infos in groups.values():
            if len(infos) < 2:
                continue
            infos.sort(key=lambda i: (not i.isEnabled(), i.id() not in wanted))      # keep the one that is on
            for extra in infos[1:]:
                self._remember(extra.id(), False)
                self.mgr.uninstallExtension(extra)
                removed += 1
        return removed

    def _enable_id(self, ext_id):
        fresh = self.find(ext_id)
        if fresh is not None and not fresh.isEnabled() and self._switch(fresh, True):
            self.changed.emit()

    # ---- list
    def items(self):
        out = []
        for info in self.mgr.extensions():
            if not info.isInstalled():           # Qt's own internal ones (PDF viewer, Hangouts) - not the user's
                continue
            path = info.path()
            m = manifest_of(path) if path else {}
            out.append({"id": info.id(), "store_id": webstore_id_of(m), "name": info.name() or m.get("name", "?"), "description": info.description(),
                        "enabled": info.isEnabled(), "loaded": info.isLoaded(), "installed": info.isInstalled(),
                        "error": info.error(), "popup": info.actionPopupUrl().toString(), "version": m.get("version", ""),
                        "icon": icon_uri(path, m) if path else "", "path": path})
        return out

    def find(self, ext_id):
        return next((i for i in self.mgr.extensions() if i.id() == ext_id), None)

    @property
    def broken(self):
        return bool(self.settings and self.settings.get("extensions_broken"))

    def _switch(self, info, on):
        """switching an extension on / off crashes inside some Qt WebEngine builds: leave a note first, so a crash is
        noticed at the next start and not repeated"""
        if self.broken:
            self.message.emit("Extensions can't be switched on here (the Qt engine crashed doing it). See the Extensions page.")
            return False
        try:
            with open(self.marker, "w") as f:
                f.write(info.id())
        except OSError:
            pass
        self.mgr.setExtensionEnabled(info, bool(on))
        try:
            os.remove(self.marker)
        except OSError:
            pass
        return True

    def retry(self):
        if self.settings is not None:
            self.settings["extensions_broken"] = False

    def set_enabled(self, ext_id, on):
        info = self.find(ext_id)
        if info and self._switch(info, on):
            self._remember(ext_id, on)
            self.changed.emit()

    def remove(self, ext_id):
        self._remember(ext_id, False)
        info = self.find(ext_id)
        if info:
            if info.isInstalled():
                self.mgr.uninstallExtension(info)
            else:
                self.mgr.unloadExtension(info)
                self.changed.emit()

    # ---- install
    def install_path(self, path):
        """a .crx / .zip file or an unpacked folder"""
        try:
            if os.path.isdir(path):
                m = manifest_of(path)
                if int(m.get("manifest_version", 0)) != 3:
                    raise ValueError("this folder has no Manifest V3 extension (manifest.json)")
                self.message.emit(f"Installing {m.get('name', 'extension')} …")
                self.mgr.installExtension(path)
                return
            tmp = tempfile.mkdtemp(prefix="digonto-ext-")
            z = crx_to_zip(path, os.path.join(tmp, "extension.zip"))
            m = check_zip(z)
            if m.get("key"):
                try:
                    if self.find(id_from_key(base64.b64decode(m["key"]))):
                        self.message.emit(f"{m.get('name', 'This extension')} is already installed")
                        return
                except ValueError:
                    pass
            self.message.emit(f"Installing {m.get('name', 'extension')} …")
            self.mgr.installExtension(z)
        except Exception as e:                     # noqa: BLE001 - shown to the user
            self.message.emit(f"Could not install: {e}")

    def install_webstore(self, text, name=""):
        ext_id = webstore_id(text)
        if not ext_id:
            self.message.emit("That is not a Chrome Web Store link (it should contain /detail/…)")
            return False
        if self.find(ext_id):
            self.message.emit(f"{name or 'This extension'} is already installed")
            return True
        if ext_id in self.busy:
            return True
        self.busy.add(ext_id)
        self.message.emit(f"Downloading {name or 'the extension'} from the Chrome Web Store …")

        def got(data, err):
            self.busy.discard(ext_id)
            if data is None:
                self.message.emit(f"Could not download {name or ext_id}: {err}")
                return
            try:
                tmp = tempfile.mkdtemp(prefix="digonto-ext-")
                crx = os.path.join(tmp, f"{ext_id}.crx")
                with open(crx, "wb") as f:
                    f.write(data)
                z = crx_to_zip(crx, os.path.join(tmp, "extension.zip"))
                m = check_zip(z)
                if self.find(ext_id):
                    self.message.emit(f"{m.get('name', name)} is already installed")
                    self.changed.emit()
                    return
                self._do_install(z, m.get("name", name))
            except Exception as e:                 # noqa: BLE001
                self.message.emit(f"Could not install {name or ext_id}: {e}")
        net.get(CRX_URL.format(ver=self.ver, id=ext_id), got, 120000, f"Mozilla/5.0 Chrome/{self.ver}")
        return True

    def _do_install(self, zip_path, name):
        self.message.emit(f"Installing {name} …")
        self.mgr.installExtension(zip_path)

    def _installed(self, info):
        name, err, ok, ext_id = info.name(), info.error(), info.isLoaded(), info.id()
        if err or not ok:
            self.message.emit(f"Could not install {name or 'the extension'}: {err or 'it did not load'}")
            self.changed.emit()
            return
        from PySide6.QtCore import QTimer

        def enable():                                         # Qt installs extensions switched off; switching on inside
            fresh = self.find(ext_id)                         # its own signal crashes, so do it a moment later
            if fresh is not None and not fresh.isEnabled():
                if not self._switch(fresh, True):
                    self.changed.emit()
                    return
            self._remember(ext_id, True)
            self.message.emit(f"Installed {name}")
            self.changed.emit()
        QTimer.singleShot(50, enable)
