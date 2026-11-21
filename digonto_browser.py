"""Digonto Browser - a web browser on Chromium (Qt WebEngine), in the Digonto look. PySide6 only."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import (QAction, QColor, QDesktopServices, QIcon, QKeySequence, QPainter, QPixmap, QShortcut,
                           QStandardItem, QStandardItemModel)
from PySide6.QtWebEngineCore import (QWebEngineDownloadRequest, QWebEnginePage, QWebEnginePermission, QWebEngineProfile,
                                     QWebEngineSettings)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QCompleter, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton, QSizePolicy, QStackedWidget,
                               QTabBar, QToolButton, QVBoxLayout, QWidget)

import digonto_ui as ui
from browserkit import __version__ as VERSION
from browserkit import pages, store, urls

APP_NAME = "Digonto Browser"
SLUG = "digonto-browser"
INK, SUB, LINE, BG, PINK, AMBER = "#1B1040", "#6E6475", "#E4DCEE", "#F6F2FA", "#FF6F8E", "#FFB05A"
PRIVATE_BG = "#2A1846"

QSS = f"""
QMainWindow{{background:{BG};}}
QWidget#chrome{{background:#EDE6F4;}}
QWidget#chrome[private="true"]{{background:{PRIVATE_BG};}}
QTabBar{{background:transparent;}}
QTabBar::tab{{background:transparent; color:{INK}; padding:7px 10px; margin:6px 2px 0 2px; min-width:60px; max-width:220px;
             border-top-left-radius:9px; border-top-right-radius:9px;}}
QTabBar::tab:hover{{background:#E2D8EE;}}
QTabBar::tab:selected{{background:white;}}
QWidget#chrome[private="true"] QTabBar::tab{{color:#EDE6F4;}}
QWidget#chrome[private="true"] QTabBar::tab:hover{{background:#3A2660;}}
QWidget#chrome[private="true"] QTabBar::tab:selected{{background:#4A3275; color:white;}}
QWidget#toolbar{{background:white; border-bottom:1px solid {LINE};}}
QWidget#toolbar[private="true"]{{background:#4A3275; border-bottom:1px solid #2A1846;}}
QToolButton#nav{{border:0; border-radius:16px; padding:5px;}}
QToolButton#nav:hover{{background:#EDE6F4;}}
QToolButton#nav:disabled{{opacity:.4;}}
QLineEdit#url{{background:#F3EEF8; border:1px solid transparent; border-radius:17px; padding:6px 14px; font-size:14px; color:{INK};
              selection-background-color:#FBDCE5; selection-color:{INK};}}
QLineEdit#url:focus{{background:white; border:1px solid {PINK};}}
QWidget#bbar{{background:white; border-bottom:1px solid {LINE};}}
QToolButton#bm{{border:0; border-radius:6px; padding:3px 8px; color:{INK}; font-size:12px;}}
QToolButton#bm:hover{{background:#EDE6F4;}}
QWidget#panel{{background:white; border-right:1px solid {LINE};}}
QListWidget{{border:0; background:white; color:{INK};}}
QListWidget::item{{padding:6px 4px; border-bottom:1px solid #F1ECF6;}}
QListWidget::item:selected{{background:#FBDCE5; color:{INK};}}
QWidget#infobar{{background:#FFF4E5; border-bottom:1px solid #F3D9B1;}}
QWidget#findbar{{background:white; border-top:1px solid {LINE};}}
QLabel#status{{background:rgba(255,255,255,.96); border:1px solid {LINE}; border-radius:6px; padding:2px 8px; color:{SUB}; font-size:12px;}}
QPushButton{{background:white; border:1px solid #D0C4E1; border-radius:6px; padding:5px 12px; color:{INK};}}
QPushButton:hover{{background:#EDE6F4;}}
QPushButton#primary{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {PINK},stop:1 {AMBER}); color:#2A1241; border-color:{PINK}; font-weight:600;}}
QLineEdit,QComboBox{{background:white; border:1px solid #D0C4E1; border-radius:6px; padding:5px; color:{INK};}}
QMenu{{background:white; color:{INK}; border:1px solid {LINE};}} QMenu::item{{padding:6px 22px;}} QMenu::item:selected{{background:#FBDCE5;}}
QMenu::separator{{height:1px; background:{LINE}; margin:4px 8px;}}
"""

PERMISSION_TEXT = {
    "Geolocation": "know your location",
    "MediaAudioCapture": "use your microphone",
    "MediaVideoCapture": "use your camera",
    "MediaAudioVideoCapture": "use your camera and microphone",
    "DesktopVideoCapture": "share your screen",
    "DesktopAudioVideoCapture": "share your screen and audio",
    "Notifications": "show notifications",
    "MouseLock": "lock your mouse pointer",
    "ClipboardReadWrite": "read and write your clipboard",
    "LocalFontsAccess": "see the fonts on your computer",
}

# one store for every normal window; private windows only read the settings
SETTINGS = BOOKMARKS = HISTORY = ZOOM = None
PROFILES = {}
DOWNLOADS = []                    # QWebEngineDownloadRequest objects of this run
DOWNLOAD_LISTENERS = []
WINDOWS = []


def icon(kind, size=18, color=INK):
    return ui.line_icon(kind, size, color)


def nav_icon(kind, color=INK, size=18):
    """small extra icons that digonto_ui does not have"""
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    from PySide6.QtGui import QPen, QPainterPath
    pen = QPen(QColor(color), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    s = size
    if kind == "back":
        p.drawLine(int(s * .25), s // 2, int(s * .78), s // 2)
        path = QPainterPath()
        path.moveTo(s * .5, s * .22); path.lineTo(s * .22, s * .5); path.lineTo(s * .5, s * .78)
        p.drawPath(path)
    elif kind == "forward":
        p.drawLine(int(s * .22), s // 2, int(s * .75), s // 2)
        path = QPainterPath()
        path.moveTo(s * .5, s * .22); path.lineTo(s * .78, s * .5); path.lineTo(s * .5, s * .78)
        p.drawPath(path)
    elif kind == "reload":
        p.drawArc(int(s * .2), int(s * .2), int(s * .6), int(s * .6), 60 * 16, 290 * 16)
        path = QPainterPath()
        path.moveTo(s * .62, s * .14); path.lineTo(s * .66, s * .3); path.lineTo(s * .5, s * .33)
        p.drawPath(path)
    elif kind == "stop":
        p.drawLine(int(s * .27), int(s * .27), int(s * .73), int(s * .73))
        p.drawLine(int(s * .73), int(s * .27), int(s * .27), int(s * .73))
    elif kind == "home":
        path = QPainterPath()
        path.moveTo(s * .18, s * .5); path.lineTo(s * .5, s * .2); path.lineTo(s * .82, s * .5)
        path.moveTo(s * .28, s * .42); path.lineTo(s * .28, s * .8); path.lineTo(s * .72, s * .8); path.lineTo(s * .72, s * .42)
        p.drawPath(path)
    elif kind in ("star", "star_on"):
        import math
        path = QPainterPath()
        for i in range(10):
            r = s * (.38 if i % 2 == 0 else .16)
            a = math.radians(-90 + i * 36)
            pt = (s / 2 + r * math.cos(a), s * .53 + r * math.sin(a))
            path.moveTo(*pt) if i == 0 else path.lineTo(*pt)
        path.closeSubpath()
        if kind == "star_on":
            p.setBrush(QColor(PINK))
            p.setPen(QPen(QColor(PINK), 1.6))
        p.drawPath(path)
    elif kind == "menu":
        p.setBrush(QColor(color))
        for y in (.25, .5, .75):
            p.drawEllipse(int(s * .5 - 1.5), int(s * y - 1.5), 3, 3)
    elif kind == "lock":
        p.drawRoundedRect(int(s * .25), int(s * .45), int(s * .5), int(s * .38), 2, 2)
        p.drawArc(int(s * .33), int(s * .18), int(s * .34), int(s * .5), 0, 180 * 16)
    elif kind == "warn":
        path = QPainterPath()
        path.moveTo(s * .5, s * .15); path.lineTo(s * .88, s * .82); path.lineTo(s * .12, s * .82); path.closeSubpath()
        p.drawPath(path)
        p.drawLine(s // 2, int(s * .4), s // 2, int(s * .6))
        p.drawPoint(s // 2, int(s * .7))
    elif kind == "clock":
        p.drawEllipse(int(s * .16), int(s * .16), int(s * .68), int(s * .68))
        p.drawLine(s // 2, s // 2, s // 2, int(s * .3))
        p.drawLine(s // 2, s // 2, int(s * .66), int(s * .6))
    elif kind == "download":
        p.drawLine(s // 2, int(s * .15), s // 2, int(s * .62))
        path = QPainterPath()
        path.moveTo(s * .3, s * .44); path.lineTo(s * .5, s * .64); path.lineTo(s * .7, s * .44)
        path.moveTo(s * .18, s * .7); path.lineTo(s * .18, s * .84); path.lineTo(s * .82, s * .84); path.lineTo(s * .82, s * .7)
        p.drawPath(path)
    elif kind == "mask":                                  # private window
        path = QPainterPath()
        path.moveTo(s * .12, s * .38)
        path.cubicTo(s * .3, s * .3, s * .7, s * .3, s * .88, s * .38)
        path.cubicTo(s * .88, s * .62, s * .7, s * .7, s * .6, s * .6)
        path.cubicTo(s * .55, s * .55, s * .45, s * .55, s * .4, s * .6)
        path.cubicTo(s * .3, s * .7, s * .12, s * .62, s * .12, s * .38)
        p.drawPath(path)
        p.drawEllipse(int(s * .26), int(s * .4), int(s * .14), int(s * .1))
        p.drawEllipse(int(s * .6), int(s * .4), int(s * .14), int(s * .1))
    elif kind == "tab":
        p.drawRoundedRect(int(s * .14), int(s * .22), int(s * .72), int(s * .58), 3, 3)
        p.drawLine(int(s * .14), int(s * .38), int(s * .86), int(s * .38))
        p.drawLine(s // 2, int(s * .5), s // 2, int(s * .7))
        p.drawLine(int(s * .4), int(s * .6), int(s * .6), int(s * .6))
    elif kind == "close":
        p.setPen(QPen(QColor(color), 1.5, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(int(s * .32), int(s * .32), int(s * .68), int(s * .68))
        p.drawLine(int(s * .68), int(s * .32), int(s * .32), int(s * .68))
    elif kind == "plus":
        p.drawLine(s // 2, int(s * .25), s // 2, int(s * .75))
        p.drawLine(int(s * .25), s // 2, int(s * .75), s // 2)
    elif kind == "sound":
        path = QPainterPath()
        path.moveTo(s * .18, s * .4); path.lineTo(s * .32, s * .4); path.lineTo(s * .5, s * .24); path.lineTo(s * .5, s * .76)
        path.lineTo(s * .32, s * .6); path.lineTo(s * .18, s * .6); path.closeSubpath()
        p.drawPath(path)
        p.drawArc(int(s * .45), int(s * .3), int(s * .3), int(s * .4), -50 * 16, 100 * 16)
    elif kind == "mute":
        path = QPainterPath()
        path.moveTo(s * .18, s * .4); path.lineTo(s * .32, s * .4); path.lineTo(s * .5, s * .24); path.lineTo(s * .5, s * .76)
        path.lineTo(s * .32, s * .6); path.lineTo(s * .18, s * .6); path.closeSubpath()
        p.drawPath(path)
        p.drawLine(int(s * .6), int(s * .4), int(s * .8), int(s * .6))
        p.drawLine(int(s * .8), int(s * .4), int(s * .6), int(s * .6))
    p.end()
    return QIcon(pm)


def nav_button(kind, tip, fn, color=INK):
    b = QToolButton()
    b.setObjectName("nav")
    b.setIcon(nav_icon(kind, color))
    b.setIconSize(QSize(18, 18))
    b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    if fn:
        b.clicked.connect(fn)
    return b


def no_app_filters(app):
    """Digonto's shared setup watches every widget of the app with a Python event filter. With the web engine that
    filter is also called for the engine's own internal objects and recurses until the program crashes - so the
    browser switches it off and styles its few drop-down lists itself (combo())."""
    f = getattr(app, "_combofix", None)
    if f is not None:
        app.removeEventFilter(f)


def combo():
    from PySide6.QtWidgets import QStyledItemDelegate
    c = QComboBox()
    c.setItemDelegate(QStyledItemDelegate(c))
    return c


def host_of(url):
    return QUrl(url).host() if isinstance(url, str) else url.host()


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


# ------------------------------------------------------------------------------------------------- profiles --
def default_download_dir():
    d = SETTINGS["download_dir"] or QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or os.path.expanduser("~")
    return d


def clean_user_agent(ua):
    """Qt adds 'QtWebEngine/x.y.z' to the user agent; some sites (Google sign-in) refuse such browsers"""
    parts = [p for p in ua.split(" ") if not p.startswith("QtWebEngine/")]
    return " ".join(parts)


def get_profile(private):
    key = "private" if private else "normal"
    if key in PROFILES:
        return PROFILES[key]
    if private:
        prof = QWebEngineProfile(QApplication.instance())            # no name = nothing written to disk
    else:
        prof = QWebEngineProfile("digonto", QApplication.instance())
        base = os.path.join(store.data_dir(), "profile")
        prof.setPersistentStoragePath(base)
        prof.setCachePath(os.path.join(base, "cache"))
        prof.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
        try:
            prof.setPersistentPermissionsPolicy(QWebEngineProfile.PersistentPermissionsPolicy.StoreOnDisk)
        except AttributeError:
            pass
    prof.setHttpUserAgent(clean_user_agent(prof.httpUserAgent()))
    s = prof.settings()
    for attr in ("FullScreenSupportEnabled", "ScrollAnimatorEnabled", "PdfViewerEnabled", "PluginsEnabled",
                 "DnsPrefetchEnabled", "FocusOnNavigationEnabled", "ScreenCaptureEnabled"):
        a = getattr(QWebEngineSettings.WebAttribute, attr, None)
        if a is not None:
            s.setAttribute(a, True)
    handler = pages.Handler(SETTINGS, HISTORY, private, prof,
                            {"changed": settings_changed, "pick": pick_download_dir, "clear": clear_browsing_data,
                             "default_dir": default_download_dir})
    prof.installUrlSchemeHandler(pages.SCHEME, handler)
    prof._handler = handler
    apply_cookie_policy(prof)
    prof.downloadRequested.connect(on_download)
    PROFILES[key] = prof
    return prof


def settings_changed(key=None):
    for w in list(WINDOWS):
        try:
            w.fill_bbar()
            w.refresh_bar()
        except RuntimeError:
            pass
    for prof in PROFILES.values():
        apply_cookie_policy(prof)


def pick_download_dir(_q):
    d = QFileDialog.getExistingDirectory(QApplication.activeWindow(), "Downloads folder", default_download_dir())
    if d:
        SETTINGS["download_dir"] = d
        return {"folder": d}
    return {}


def clear_browsing_data(q):
    secs = int(q.get("since", "0") or 0)
    prof = get_profile(False)
    if q.get("hist") == "1":
        HISTORY.clear(time.time() - secs if secs else 0)
        prof.clearAllVisitedLinks()
    if q.get("cookies") == "1":
        prof.cookieStore().deleteAllCookies()
    if q.get("cache") == "1":
        prof.clearHttpCache()
    return {}


def apply_cookie_policy(prof):
    block = bool(SETTINGS["block_third_party_cookies"])
    try:
        prof.cookieStore().setCookieFilter((lambda req: not req.thirdParty) if block else None)
    except (TypeError, AttributeError):
        pass


def on_download(req):
    """a site starts a download: save it (or ask where) and show it in the downloads panel"""
    folder = default_download_dir()
    name = req.downloadFileName() or req.suggestedFileName() or "download"
    if SETTINGS["ask_download"]:
        win = QApplication.activeWindow()
        path, _ = QFileDialog.getSaveFileName(win, "Save download", os.path.join(folder, name))
        if not path:
            req.cancel()
            return
        folder, name = os.path.dirname(path), os.path.basename(path)
    else:                                                    # never overwrite: "file (1).pdf"
        stem, ext = os.path.splitext(name)
        k = 1
        while os.path.exists(os.path.join(folder, name)):
            name = f"{stem} ({k}){ext}"
            k += 1
    req.setDownloadDirectory(folder)
    req.setDownloadFileName(name)
    req.accept()
    DOWNLOADS.insert(0, req)
    for fn in list(DOWNLOAD_LISTENERS):
        try:
            fn(req)
        except RuntimeError:
            DOWNLOAD_LISTENERS.remove(fn)


# ---------------------------------------------------------------------------------------------- web views --
class WebView(QWebEngineView):
    def __init__(self, win, profile):
        super().__init__()
        self.win = win
        self.setPage(QWebEnginePage(profile, self))

    def createWindow(self, kind):
        T = QWebEnginePage.WebWindowType
        if kind == T.WebDialog:                              # pop-ups (sign-in windows, payment, ...)
            return self.win.open_popup()
        background = kind == T.WebBrowserBackgroundTab
        if kind == T.WebBrowserWindow:
            w = self.win.new_window()
            return w.add_tab(None).view
        return self.win.add_tab(None, background=background, after_current=True).view


class InfoBar(QWidget):
    """the yellow strip above a page: permissions, certificate problems, crashes"""

    def __init__(self, text, buttons, kind="warn"):
        super().__init__()
        self.setObjectName("infobar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 6, 8, 6)
        ic = QLabel()
        ic.setPixmap(nav_icon(kind, "#B26B00").pixmap(18, 18))
        h.addWidget(ic)
        lab = QLabel(text)
        lab.setWordWrap(True)
        lab.setStyleSheet(f"color:{INK};")
        h.addWidget(lab, 1)
        for label, fn, primary in buttons:
            b = QPushButton(label)
            if primary:
                b.setObjectName("primary")
            b.clicked.connect(lambda _=False, fn=fn: (fn(), self.close_bar()))
            h.addWidget(b)

    def close_bar(self):
        self.hide()
        self.deleteLater()


class TabPage(QWidget):
    def __init__(self, win, profile):
        super().__init__()
        self.win = win
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.bars = QVBoxLayout()
        self.bars.setSpacing(0)
        v.addLayout(self.bars)
        self.view = WebView(win, profile)
        v.addWidget(self.view, 1)
        self.status = QLabel(self)
        self.status.setObjectName("status")
        self.status.hide()
        self.audible = False
        pg = self.view.page()
        pg.linkHovered.connect(self.show_link)
        pg.permissionRequested.connect(self.ask_permission)
        pg.certificateError.connect(self.cert_error)
        pg.renderProcessTerminated.connect(self.crashed)
        pg.fullScreenRequested.connect(win.fullscreen_request)
        pg.recentlyAudibleChanged.connect(lambda a: (setattr(self, "audible", a), win.update_tab(self)))
        pg.audioMutedChanged.connect(lambda m: win.update_tab(self))

    def add_bar(self, text, buttons, kind="warn"):
        bar = InfoBar(text, buttons, kind)
        self.bars.addWidget(bar)
        return bar

    def show_link(self, url):
        if not url:
            self.status.hide()
            return
        self.status.setText(url if len(url) < 120 else url[:117] + "…")
        self.status.adjustSize()
        self.status.move(6, self.height() - self.status.height() - 6)
        self.status.show()
        self.status.raise_()

    def ask_permission(self, perm):
        kind = perm.permissionType().name if hasattr(perm.permissionType(), "name") else str(perm.permissionType())
        what = PERMISSION_TEXT.get(kind, "use a special feature")
        host = perm.origin().host() or perm.origin().toString()
        self.add_bar(f"<b>{host}</b> wants to {what}.",
                     [("Block", perm.deny, False), ("Allow", perm.grant, True)], "warn")

    def cert_error(self, err):
        if not err.isOverridable():
            err.rejectCertificate()
            return
        err.defer()
        self.add_bar(f"<b>The connection to {err.url().host()} is not private.</b> {err.description()} "
                     "Someone could be reading or changing what you send.",
                     [("Go back (safe)", err.rejectCertificate, True), ("Continue anyway", err.acceptCertificate, False)], "warn")

    def crashed(self, status, code):
        if status == QWebEnginePage.RenderProcessTerminationStatus.NormalTerminationStatus:
            return
        self.add_bar("This page stopped working (it crashed or ran out of memory).",
                     [("Reload", self.view.reload, True)], "warn")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.status.isVisible():
            self.status.move(6, self.height() - self.status.height() - 6)


# ------------------------------------------------------------------------------------------------- panels --
class Panel(QWidget):
    """the drawer next to the left icon bar: bookmarks, history or downloads"""

    def __init__(self, title):
        super().__init__()
        self.setObjectName("panel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(330)
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(12, 12, 12, 12)
        self.v.setSpacing(8)
        lab = QLabel(title)
        lab.setStyleSheet(f"font-size:16px; font-weight:700; color:{INK};")
        self.v.addWidget(lab)


class BookmarksPanel(Panel):
    def __init__(self, win):
        super().__init__("Bookmarks")
        self.win = win
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search bookmarks")
        self.search.textChanged.connect(self.fill)
        self.v.addWidget(self.search)
        self.list = QListWidget()
        self.list.itemActivated.connect(lambda it: win.open_url(it.data(Qt.UserRole)))
        self.list.itemClicked.connect(lambda it: win.open_url(it.data(Qt.UserRole)))
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self.menu)
        self.v.addWidget(self.list, 1)
        BOOKMARKS.listeners.append(self.fill)
        self.fill()

    def fill(self, *_):
        t = self.search.text().lower()
        self.list.clear()
        for b in sorted(BOOKMARKS.items, key=lambda b: (b.get("folder", ""), b["title"].lower())):
            if t and t not in b["title"].lower() and t not in b["url"].lower():
                continue
            folder = b.get("folder", "")
            it = QListWidgetItem(f"{b['title']}\n{b['url']}" + (f"   ·  {folder}" if folder else ""))
            it.setData(Qt.UserRole, b["url"])
            it.setToolTip(b["url"])
            self.list.addItem(it)
        if not self.list.count():
            it = QListWidgetItem("No bookmarks yet.\nPress the ☆ in the address bar (Ctrl+D).")
            it.setFlags(Qt.NoItemFlags)
            self.list.addItem(it)

    def menu(self, pos):
        it = self.list.itemAt(pos)
        if not it or not it.data(Qt.UserRole):
            return
        url = it.data(Qt.UserRole)
        m = QMenu(self)
        m.addAction("Open in new tab", lambda: self.win.add_tab(url))
        m.addAction("Rename …", lambda: self.rename(url))
        m.addAction("Delete", lambda: BOOKMARKS.remove(url))
        m.exec(self.list.mapToGlobal(pos))

    def rename(self, url):
        from PySide6.QtWidgets import QInputDialog
        b = BOOKMARKS.find(url)
        t, ok = QInputDialog.getText(self, "Rename bookmark", "Name:", text=b["title"] if b else "")
        if ok and t.strip():
            BOOKMARKS.rename(url, t.strip())


class HistoryPanel(Panel):
    def __init__(self, win):
        super().__init__("History")
        self.win = win
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search history")
        self.search.textChanged.connect(lambda: self.timer.start())
        self.v.addWidget(self.search)
        self.timer = QTimer(self, singleShot=True, interval=200, timeout=self.fill)
        self.list = QListWidget()
        self.list.itemClicked.connect(lambda it: it.data(Qt.UserRole) and win.open_url(it.data(Qt.UserRole)))
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self.menu)
        self.v.addWidget(self.list, 1)
        clear = QPushButton("Clear browsing data …")
        clear.clicked.connect(win.clear_data)
        self.v.addWidget(clear)

    def fill(self):
        self.list.clear()
        day = None
        for url, title, last in HISTORY.recent(400, self.search.text().strip()):
            d = time.strftime("%A, %d %B %Y", time.localtime(last))
            if d != day:
                day = d
                h = QListWidgetItem(d)
                h.setFlags(Qt.NoItemFlags)
                h.setForeground(QColor(SUB))
                f = h.font()
                f.setBold(True)
                h.setFont(f)
                self.list.addItem(h)
            it = QListWidgetItem(f"{time.strftime('%H:%M', time.localtime(last))}   {title or url}\n{url}")
            it.setData(Qt.UserRole, url)
            it.setToolTip(url)
            self.list.addItem(it)

    def menu(self, pos):
        it = self.list.itemAt(pos)
        if not it or not it.data(Qt.UserRole):
            return
        url = it.data(Qt.UserRole)
        m = QMenu(self)
        m.addAction("Open in new tab", lambda: self.win.add_tab(url))
        m.addAction("Remove from history", lambda: (HISTORY.delete(url), self.fill()))
        m.exec(self.list.mapToGlobal(pos))


class DownloadRow(QWidget):
    def __init__(self, req):
        super().__init__()
        self.req = req
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 6, 4, 6)
        v.setSpacing(3)
        self.name = QLabel(req.downloadFileName())
        self.name.setStyleSheet(f"color:{INK}; font-weight:600;")
        v.addWidget(self.name)
        self.bar = QProgressBar()
        self.bar.setFixedHeight(6)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet(f"QProgressBar{{background:#EDE6F4; border:0; border-radius:3px;}}"
                               f"QProgressBar::chunk{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {PINK},stop:1 {AMBER}); border-radius:3px;}}")
        v.addWidget(self.bar)
        h = QHBoxLayout()
        self.info = QLabel()
        self.info.setStyleSheet(f"color:{SUB}; font-size:11px;")
        h.addWidget(self.info, 1)
        self.btn_open = QPushButton("Open")
        self.btn_folder = QPushButton("Show in folder")
        self.btn_cancel = QPushButton("Cancel")
        for b in (self.btn_open, self.btn_folder, self.btn_cancel):
            b.setStyleSheet("padding:2px 8px; font-size:11px;")
            h.addWidget(b)
        v.addLayout(h)
        self.btn_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.path())))
        self.btn_folder.clicked.connect(lambda: ui.open_external(req.downloadDirectory()))
        self.btn_cancel.clicked.connect(req.cancel)
        req.receivedBytesChanged.connect(self.update)
        req.totalBytesChanged.connect(self.update)
        req.stateChanged.connect(self.update)
        self.update()

    def path(self):
        return os.path.join(self.req.downloadDirectory(), self.req.downloadFileName())

    def update(self, *_):
        try:
            st = self.req.state()
        except RuntimeError:
            return
        S = QWebEngineDownloadRequest.DownloadState
        got, total = self.req.receivedBytes(), self.req.totalBytes()
        done = st == S.DownloadCompleted
        if total > 0:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(got * 1000 / total))
        else:
            self.bar.setRange(0, 0 if st == S.DownloadInProgress else 1)
        if done:
            self.bar.setRange(0, 1)
            self.bar.setValue(1)
            self.info.setText(f"Done · {human_size(got)}")
        elif st == S.DownloadCancelled:
            self.info.setText("Cancelled")
        elif st == S.DownloadInterrupted:
            self.info.setText("Failed: " + self.req.interruptReasonString())
        else:
            self.info.setText(f"{human_size(got)}" + (f" of {human_size(total)}" if total > 0 else ""))
        self.btn_open.setVisible(done)
        self.btn_folder.setVisible(done)
        self.btn_cancel.setVisible(st == S.DownloadInProgress)
        self.bar.setVisible(not done)


class DownloadsPanel(Panel):
    def __init__(self, win):
        super().__init__("Downloads")
        self.win = win
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.NoSelection)
        self.v.addWidget(self.list, 1)
        h = QHBoxLayout()
        f = QPushButton("Open downloads folder")
        f.clicked.connect(lambda: ui.open_external(default_download_dir()))
        h.addWidget(f)
        c = QPushButton("Clear list")
        c.clicked.connect(self.clear)
        h.addWidget(c)
        self.v.addLayout(h)
        for req in reversed(DOWNLOADS):
            self.add(req)
        DOWNLOAD_LISTENERS.append(self.add)
        self.empty()

    def add(self, req):
        row = DownloadRow(req)
        it = QListWidgetItem()
        it.setSizeHint(row.sizeHint())
        self.list.insertItem(0, it)
        self.list.setItemWidget(it, row)
        self.empty()

    def empty(self):
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == "empty":
                if self.list.count() > 1:
                    self.list.takeItem(i)
                return
        if not self.list.count():
            it = QListWidgetItem("No downloads yet.")
            it.setData(Qt.UserRole, "empty")
            it.setFlags(Qt.NoItemFlags)
            self.list.addItem(it)

    def clear(self):
        S = QWebEngineDownloadRequest.DownloadState
        keep = [r for r in DOWNLOADS if r.state() == S.DownloadInProgress]
        DOWNLOADS[:] = keep
        self.list.clear()
        for r in reversed(keep):
            self.add(r)
        self.empty()


# ------------------------------------------------------------------------------------------- address bar --
class UrlBar(QLineEdit):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("url")
        self.setPlaceholderText("Search or type a web address")
        self.setClearButtonEnabled(False)
        self.lock = self.addAction(nav_icon("lock", SUB), QLineEdit.LeadingPosition)
        self.lock.setVisible(False)
        self.star = self.addAction(nav_icon("star", SUB), QLineEdit.TrailingPosition)
        self.star.setToolTip("Bookmark this page (Ctrl+D)")
        self.star.triggered.connect(win.toggle_bookmark)
        self.model = QStandardItemModel(self)
        self.comp = QCompleter(self.model, self)
        self.comp.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self.comp.setCompletionRole(Qt.UserRole)
        self.comp.setMaxVisibleItems(9)
        self.comp.popup().setStyleSheet(f"QListView{{background:white; color:{INK}; border:1px solid {LINE}; padding:4px;}}"
                                        f"QListView::item{{padding:6px;}} QListView::item:selected{{background:#FBDCE5; color:{INK};}}")
        self.setCompleter(self.comp)
        self.comp.activated[str].connect(lambda u: win.navigate(u))
        self.textEdited.connect(self.suggest)
        self.returnPressed.connect(lambda: win.navigate(self.text()))

    def suggest(self, text):
        self.model.clear()
        t = text.strip()
        if not t:
            return
        rows = []
        engine_name = urls.ENGINES.get(SETTINGS["engine"], urls.ENGINES["duckduckgo"])[0]
        rows.append((f"🔍  {t}  —  search with {engine_name}", t))
        seen = set()
        low = t.lower()
        for b in BOOKMARKS.items:
            if low in b["url"].lower() or low in b["title"].lower():
                rows.append((f"☆  {b['title']}  —  {b['url']}", b["url"]))
                seen.add(b["url"])
        if not self.win.private:
            for url, title in HISTORY.suggest(t, 8):
                if url not in seen:
                    rows.append((f"{title or url}  —  {url}", url))
                    seen.add(url)
        for label, val in rows[:10]:
            it = QStandardItem(label)
            it.setData(val, Qt.UserRole)
            self.model.appendRow(it)

    def show_url(self, url):
        if self.hasFocus():
            return
        self.setText(urls.pretty(url))
        self.setCursorPosition(0)
        secure = url.startswith(("https:", "digonto:"))
        self.lock.setVisible(url.startswith(("https:", "http:")))
        self.lock.setIcon(nav_icon("lock" if secure else "warn", SUB if secure else "#C2410C"))
        self.lock.setToolTip("Secure connection (HTTPS)" if secure else "Not secure: this page does not use HTTPS")

    def set_starred(self, on):
        self.star.setIcon(nav_icon("star_on" if on else "star", SUB))
        self.star.setToolTip("Remove bookmark" if on else "Bookmark this page (Ctrl+D)")

    def focusInEvent(self, e):
        super().focusInEvent(e)
        QTimer.singleShot(0, self.selectAll)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.clearFocus()
            self.win.refresh_bar()
            v = self.win.view()
            if v:
                v.setFocus()
            return
        super().keyPressEvent(e)


class FindBar(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("findbar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 5, 10, 5)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Find in page")
        self.edit.setFixedWidth(280)
        self.edit.textChanged.connect(lambda: self.find())
        self.edit.returnPressed.connect(lambda: self.find())
        h.addWidget(self.edit)
        self.count = QLabel("")
        self.count.setStyleSheet(f"color:{SUB};")
        h.addWidget(self.count)
        prev = QPushButton("↑")
        prev.setToolTip("Previous (Shift+Enter)")
        prev.clicked.connect(lambda: self.find(back=True))
        nxt = QPushButton("↓")
        nxt.setToolTip("Next (Enter)")
        nxt.clicked.connect(lambda: self.find())
        h.addWidget(prev)
        h.addWidget(nxt)
        h.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.close_bar)
        h.addWidget(close)
        self.hide()
        QShortcut(QKeySequence("Shift+Return"), self.edit, lambda: self.find(back=True))
        QShortcut(QKeySequence("Escape"), self, self.close_bar)

    def open_bar(self):
        self.show()
        self.edit.setFocus()
        self.edit.selectAll()
        if self.edit.text():
            self.find()

    def close_bar(self):
        self.hide()
        v = self.win.view()
        if v:
            v.page().findText("")
            v.setFocus()

    def find(self, back=False):
        v = self.win.view()
        if not v:
            return
        flags = QWebEnginePage.FindFlag.FindBackward if back else QWebEnginePage.FindFlag(0)
        v.page().findText(self.edit.text(), flags)

    def result(self, res):
        n = res.numberOfMatches()
        self.count.setText(f"{res.activeMatch()} of {n}" if n else ("No matches" if self.edit.text() else ""))


# -------------------------------------------------------------------------------------------- main window --
class Main(QMainWindow):
    def __init__(self, private=False, restore=False, start=None):
        super().__init__()
        self.private = private
        self.profile = get_profile(private)
        self.closed_tabs = []
        self.popups = []
        self.dev_windows = []
        self.setWindowIcon(ui.app_icon(HERE, SLUG))
        ui.fit_window(self, 1320, 860)
        self.setMinimumSize(640, 420)
        self.setStyleSheet(QSS)

        root = QWidget()
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.rail = ui.Rail(
            [("newtab", "new", "New tab (Ctrl+T)", lambda: self.add_tab(urls.NEWTAB)),
             ("private", "pen", "New private window (Ctrl+Shift+N)", lambda: self.new_window(private=True)),
             None,
             ("bookmarks", "pages", "Bookmarks (Ctrl+Shift+O)", lambda: self.toggle_panel("bookmarks")),
             ("history", "playlist", "History (Ctrl+H)", lambda: self.toggle_panel("history")),
             ("downloads", "export", "Downloads (Ctrl+J)", lambda: self.toggle_panel("downloads"))],
            [("settings", "settings", "Settings", self.open_settings)])
        for key, kind in (("newtab", "tab"), ("private", "mask"), ("bookmarks", "star"), ("history", "clock"),
                          ("downloads", "download")):
            b = self.rail.buttons.get(key)
            if b is not None:
                b.setIcon(nav_icon(kind, INK, 22))
                b.setIconSize(QSize(22, 22))
        outer.addWidget(self.rail, 0)
        self.panels = QStackedWidget()
        self.panel_of = {}
        self.panels.hide()
        outer.addWidget(self.panels, 0)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        self.chrome = QWidget()
        self.chrome.setObjectName("chrome")
        self.chrome.setProperty("private", private)
        self.chrome.setAttribute(Qt.WA_StyledBackground, True)
        ch = QHBoxLayout(self.chrome)
        ch.setContentsMargins(8, 0, 8, 0)
        ch.setSpacing(4)
        if private:
            tag = QLabel("  Private  ")
            tag.setStyleSheet(f"color:white; background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {PINK},stop:1 {AMBER});"
                              "border-radius:9px; font-weight:700; font-size:11px; padding:2px 4px;")
            ch.addWidget(tag)
        self.tabs = QTabBar()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(False)              # own small close buttons (close_button)
        self.tabs.setMovable(True)
        self.tabs.setExpanding(False)
        self.tabs.setElideMode(Qt.ElideRight)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setDrawBase(False)
        self.tabs.currentChanged.connect(self.tab_changed)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.tabMoved.connect(self.tab_moved)
        self.tabs.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self.tab_menu)
        self.tabs.installEventFilter(self)
        ch.addWidget(self.tabs, 0)
        plus = nav_button("plus", "New tab (Ctrl+T)", lambda: self.add_tab(urls.NEWTAB), "#EDE6F4" if private else INK)
        ch.addWidget(plus)
        ch.addStretch(1)
        col.addWidget(self.chrome)

        tb = QWidget()
        tb.setObjectName("toolbar")
        tb.setProperty("private", private)
        tb.setAttribute(Qt.WA_StyledBackground, True)
        th = QHBoxLayout(tb)
        th.setContentsMargins(8, 6, 8, 6)
        th.setSpacing(4)
        c = "#EDE6F4" if private else INK
        self.b_back = nav_button("back", "Back (Alt+Left)", lambda: self.view() and self.view().back(), c)
        self.b_fwd = nav_button("forward", "Forward (Alt+Right)", lambda: self.view() and self.view().forward(), c)
        self.b_reload = nav_button("reload", "Reload (Ctrl+R)", self.reload_or_stop, c)
        self.b_home = nav_button("home", "New tab page", lambda: self.navigate(urls.NEWTAB), c)
        for b in (self.b_back, self.b_fwd, self.b_reload, self.b_home):
            th.addWidget(b)
        self.url = UrlBar(self)
        th.addWidget(self.url, 1)
        self.b_zoom = QPushButton("100 %")
        self.b_zoom.setToolTip("Reset zoom (Ctrl+0)")
        self.b_zoom.clicked.connect(lambda: self.set_zoom(1.0))
        self.b_zoom.hide()
        th.addWidget(self.b_zoom)
        self.b_menu = nav_button("menu", "Menu", None, c)
        self.b_menu.setPopupMode(QToolButton.InstantPopup)
        self.b_menu.setMenu(self.build_menu())
        self.b_menu.setStyleSheet("QToolButton::menu-indicator{image:none;}")
        th.addWidget(self.b_menu)
        col.addWidget(tb)
        self.toolbar = tb

        self.bbar = QWidget()
        self.bbar.setObjectName("bbar")
        self.bbar.setAttribute(Qt.WA_StyledBackground, True)
        self.bbar_lay = QHBoxLayout(self.bbar)
        self.bbar_lay.setContentsMargins(8, 2, 8, 2)
        self.bbar_lay.setSpacing(2)
        col.addWidget(self.bbar)
        BOOKMARKS.listeners.append(self.fill_bbar)
        self.fill_bbar()

        self.stack = QStackedWidget()
        col.addWidget(self.stack, 1)
        self.find = FindBar(self)
        col.addWidget(self.find)
        outer.addLayout(col, 1)
        self.setCentralWidget(root)
        self.shortcuts()
        WINDOWS.append(self)

        if restore and not private and SETTINGS["startup"] == "restore":
            sess = store.load_session()
            tabs = [u for u in sess.get("tabs", []) if isinstance(u, str)]
            for u in tabs:
                self.add_tab(u, background=True)
            if tabs:
                self.tabs.setCurrentIndex(min(int(sess.get("current", 0)), len(tabs) - 1))
        for u in start or []:
            self.add_tab(u)
        if self.tabs.count() == 0:
            self.add_tab(urls.NEWTAB)
        self.update_title()

    # ---- tabs
    def page_at(self, i):
        return self.tabs.tabData(i)

    def current(self):
        i = self.tabs.currentIndex()
        return self.page_at(i) if i >= 0 else None

    def view(self):
        p = self.current()
        return p.view if p else None

    def index_of(self, page):
        for i in range(self.tabs.count()):
            if self.tabs.tabData(i) is page:
                return i
        return -1

    def add_tab(self, url=urls.NEWTAB, background=False, after_current=False):
        page = TabPage(self, self.profile)
        v = page.view
        v.titleChanged.connect(lambda t, p=page: self.update_tab(p))
        v.iconChanged.connect(lambda ic, p=page: self.update_tab(p))
        v.urlChanged.connect(lambda u, p=page: self.url_changed(p, u))
        v.loadStarted.connect(lambda p=page: self.load_state(p, True))
        v.loadFinished.connect(lambda ok, p=page: self.load_finished(p, ok))
        v.page().findTextFinished.connect(self.find.result)
        self.stack.addWidget(page)
        i = self.tabs.currentIndex() + 1 if after_current and self.tabs.count() else self.tabs.count()
        i = self.tabs.insertTab(i, "New tab")
        self.tabs.setTabData(i, page)
        self.tabs.setTabButton(i, QTabBar.RightSide, self.close_button(page))
        if url:
            v.setUrl(QUrl(url))
        if not background or self.tabs.count() == 1:
            self.tabs.setCurrentIndex(i)
            if url == urls.NEWTAB:
                QTimer.singleShot(50, lambda: (self.url.setFocus(), self.url.selectAll()))
        self.update_tab(page)
        return page

    def close_button(self, page):
        b = QToolButton()
        b.setIcon(nav_icon("close", "#EDE6F4" if self.private else SUB, 16))
        b.setIconSize(QSize(16, 16))
        b.setFixedSize(20, 20)
        b.setToolTip("Close tab (Ctrl+W)")
        b.setStyleSheet("QToolButton{border:0; border-radius:10px;} QToolButton:hover{background:rgba(127,90,170,.22);}")
        b.clicked.connect(lambda: self.close_tab(self.index_of(page)))
        return b

    def tab_changed(self, i):
        p = self.page_at(i) if i >= 0 else None
        if not p:
            return
        self.stack.setCurrentWidget(p)
        self.refresh_bar()
        self.update_title()
        if self.find.isVisible() and self.find.edit.text():
            self.find.find()

    def tab_moved(self, a, b):
        pass                                    # pages are found through tabData, so nothing to re-order

    def close_tab(self, i):
        p = self.page_at(i)
        if not p:
            return
        u = p.view.url().toString()
        if u and not self.private:
            self.closed_tabs.append(u)
        if self.tabs.count() == 1:
            if self.tabs.tabData(0).view.url().toString().startswith(urls.NEWTAB):
                self.close()
                return
            self.add_tab(urls.NEWTAB)
        self.tabs.removeTab(self.index_of(p))
        self.stack.removeWidget(p)
        p.deleteLater()

    def reopen_tab(self):
        if self.closed_tabs:
            self.add_tab(self.closed_tabs.pop())

    def update_tab(self, page):
        i = self.index_of(page)
        if i < 0:
            return
        v = page.view
        title = v.title() or ("New tab" if v.url().toString().startswith(urls.NEWTAB) else v.url().toString())
        if title.startswith("digonto://"):
            title = "New tab"
        self.tabs.setTabText(i, title)
        self.tabs.setTabToolTip(i, title + "\n" + urls.pretty(v.url().toString()))
        ic = v.icon()
        if v.page().isAudioMuted():
            ic = nav_icon("mute", SUB)
        elif page.audible:
            ic = nav_icon("sound", PINK)
        elif ic.isNull():
            ic = ui.app_icon(HERE, SLUG) if v.url().toString().startswith("digonto:") else QIcon()
        self.tabs.setTabIcon(i, ic)
        if page is self.current():
            self.update_title()

    def tab_menu(self, pos):
        i = self.tabs.tabAt(pos)
        if i < 0:
            return
        p = self.page_at(i)
        m = QMenu(self)
        m.addAction("New tab", lambda: self.add_tab(urls.NEWTAB))
        m.addAction("Reload", p.view.reload)
        m.addAction("Duplicate", lambda: self.add_tab(p.view.url().toString(), after_current=True))
        muted = p.view.page().isAudioMuted()
        m.addAction("Unmute tab" if muted else "Mute tab", lambda: p.view.page().setAudioMuted(not muted))
        m.addSeparator()
        m.addAction("Close tab", lambda: self.close_tab(self.index_of(p)))
        m.addAction("Close other tabs", lambda: self.close_others(p))
        m.addAction("Reopen closed tab", self.reopen_tab).setEnabled(bool(self.closed_tabs))
        m.exec(self.tabs.mapToGlobal(pos))

    def close_others(self, keep):
        for i in reversed(range(self.tabs.count())):
            if self.page_at(i) is not keep:
                self.close_tab(i)

    # ---- navigation
    def navigate(self, text):
        url = urls.fix(text, SETTINGS["engine"])
        v = self.view()
        if not v:
            self.add_tab(url)
            return
        v.setUrl(QUrl(url))
        self.url.clearFocus()
        v.setFocus()

    def open_url(self, url):
        """from a panel / bookmark: in this tab if it is a new tab page, else a new tab"""
        v = self.view()
        if v and v.url().toString().startswith(urls.NEWTAB):
            v.setUrl(QUrl(url))
        else:
            self.add_tab(url)

    def reload_or_stop(self):
        v = self.view()
        if not v:
            return
        if getattr(self.current(), "loading", False):
            v.stop()
        else:
            v.reload()

    def url_changed(self, page, u):
        if page is self.current():
            self.refresh_bar()
        z = ZOOM.get(u.host(), SETTINGS["default_zoom"]) if not self.private else SETTINGS["default_zoom"]
        if abs(page.view.zoomFactor() - z) > 0.001:
            page.view.setZoomFactor(z)
            if page is self.current():
                self.show_zoom()

    def load_state(self, page, loading):
        page.loading = loading
        if page is self.current():
            self.b_reload.setIcon(nav_icon("stop" if loading else "reload", "#EDE6F4" if self.private else INK))
            self.b_reload.setToolTip("Stop (Esc)" if loading else "Reload (Ctrl+R)")

    def load_finished(self, page, ok):
        self.load_state(page, False)
        u = page.view.url().toString()
        if ok and not self.private:
            HISTORY.add(u, page.view.title())
        self.update_tab(page)

    def refresh_bar(self):
        v = self.view()
        if not v:
            return
        u = v.url().toString()
        self.url.show_url(u)
        self.url.set_starred(bool(BOOKMARKS.find(u)))
        self.b_back.setEnabled(v.history().canGoBack())
        self.b_fwd.setEnabled(v.history().canGoForward())
        self.load_state(self.current(), getattr(self.current(), "loading", False))
        self.show_zoom()

    def update_title(self):
        v = self.view()
        t = v.title() if v else ""
        if not t or t.startswith("digonto://"):
            t = "New tab"
        self.setWindowTitle(f"{t} – {APP_NAME}" + (" (private)" if self.private else ""))

    # ---- bookmarks
    def toggle_bookmark(self):
        v = self.view()
        if not v:
            return
        u = v.url().toString()
        if not u or u.startswith(urls.NEWTAB):
            return
        if BOOKMARKS.find(u):
            BOOKMARKS.remove(u)
        else:
            BOOKMARKS.add(u, v.title())
        self.refresh_bar()

    def fill_bbar(self, *_):
        while self.bbar_lay.count():
            it = self.bbar_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        bar = [b for b in BOOKMARKS.items if not b.get("folder")]
        for b in bar[:40]:
            btn = QToolButton()
            btn.setObjectName("bm")
            t = b["title"]
            btn.setText(t if len(t) <= 24 else t[:22] + "…")
            btn.setToolTip(b["url"])
            btn.clicked.connect(lambda _=False, u=b["url"]: self.navigate(u))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, u=b["url"], w=btn: self.bm_menu(u, w, pos))
            self.bbar_lay.addWidget(btn)
        self.bbar_lay.addStretch(1)
        self.bbar.setVisible(bool(SETTINGS["show_bookmarks_bar"]) and bool(bar))

    def bm_menu(self, url, w, pos):
        m = QMenu(self)
        m.addAction("Open in new tab", lambda: self.add_tab(url))
        m.addAction("Delete", lambda: BOOKMARKS.remove(url))
        m.exec(w.mapToGlobal(pos))

    # ---- panels
    def toggle_panel(self, name):
        if self.panels.isVisible() and self.panels.currentWidget() is self.panel_of.get(name):
            self.panels.hide()
            return
        if name not in self.panel_of:
            cls = {"bookmarks": BookmarksPanel, "history": HistoryPanel, "downloads": DownloadsPanel}[name]
            p = cls(self)
            self.panel_of[name] = p
            self.panels.addWidget(p)
        p = self.panel_of[name]
        if name == "history":
            p.fill()
        self.panels.setCurrentWidget(p)
        self.panels.show()

    def show_downloads(self, req=None):
        if not (self.panels.isVisible() and self.panels.currentWidget() is self.panel_of.get("downloads")):
            self.toggle_panel("downloads")

    # ---- zoom
    def set_zoom(self, z):
        v = self.view()
        if not v:
            return
        z = max(0.25, min(5.0, z))
        v.setZoomFactor(z)
        if not self.private:
            ZOOM.set(v.url().host(), z)
        self.show_zoom()

    def zoom_step(self, d):
        steps = [0.25, 0.33, 0.5, 0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0, 5.0]
        v = self.view()
        if not v:
            return
        z = v.zoomFactor()
        if d > 0:
            nz = next((s for s in steps if s > z + 0.001), steps[-1])
        else:
            nz = next((s for s in reversed(steps) if s < z - 0.001), steps[0])
        self.set_zoom(nz)

    def show_zoom(self):
        v = self.view()
        z = v.zoomFactor() if v else 1.0
        self.b_zoom.setText(f"{round(z * 100)} %")
        self.b_zoom.setVisible(abs(z - 1.0) > 0.01)

    # ---- windows, pop-ups, full screen, dev tools
    def new_window(self, private=False):
        w = Main(private=private)
        w.show()
        return w

    def open_popup(self):
        win = QMainWindow(self)
        win.setAttribute(Qt.WA_DeleteOnClose)
        win.resize(560, 680)
        v = QWebEngineView(win)
        v.setPage(QWebEnginePage(self.profile, v))
        v.page().windowCloseRequested.connect(win.close)
        v.titleChanged.connect(win.setWindowTitle)
        win.setCentralWidget(v)
        win.show()
        self.popups.append(win)
        win.destroyed.connect(lambda *_: self.popups.remove(win) if win in self.popups else None)
        return v

    def fullscreen_request(self, req):
        req.accept()
        on = req.toggleOn()
        for w in (self.rail, self.chrome, self.toolbar):
            w.setVisible(not on)
        self.bbar.setVisible(not on and bool(SETTINGS["show_bookmarks_bar"]) and any(not b.get("folder") for b in BOOKMARKS.items))
        if on:
            self.panels.hide()
            self.find.hide()
            self._was_max = self.isMaximized()
            self.showFullScreen()
        else:
            self.showMaximized() if getattr(self, "_was_max", False) else self.showNormal()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            v = self.view()
            if v:
                v.triggerPageAction(QWebEnginePage.WebAction.ExitFullScreen)
            for w in (self.rail, self.chrome, self.toolbar):
                w.show()
            self.fill_bbar()
            self.showNormal()
        else:
            self.showFullScreen()

    def dev_tools(self):
        v = self.view()
        if not v:
            return
        w = QMainWindow()
        w.setAttribute(Qt.WA_DeleteOnClose)
        w.setWindowTitle(f"Developer tools – {v.title()}")
        w.resize(1000, 700)
        dv = QWebEngineView(w)
        dv.setPage(QWebEnginePage(self.profile, dv))
        v.page().setDevToolsPage(dv.page())
        w.setCentralWidget(dv)
        w.show()
        self.dev_windows.append(w)

    def view_source(self):
        v = self.view()
        if v:
            self.add_tab("view-source:" + v.url().toString(), after_current=True)

    def print_page(self):
        v = self.view()
        if not v:
            return
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        printer = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QDialog.Accepted:
            return
        self._printer = printer
        v.print(printer)

    def save_pdf(self):
        v = self.view()
        if not v:
            return
        name = "".join(c for c in (v.title() or "page") if c not in '\\/:*?"<>|')[:80] or "page"
        path, _ = QFileDialog.getSaveFileName(self, "Save page as PDF", os.path.join(default_download_dir(), name + ".pdf"),
                                              "PDF (*.pdf)")
        if path:
            v.page().printToPdf(path)

    # ---- menu, settings, data
    def build_menu(self):
        m = QMenu(self)
        m.addAction("New tab\tCtrl+T", lambda: self.add_tab(urls.NEWTAB))
        m.addAction("New window\tCtrl+N", self.new_window)
        m.addAction("New private window\tCtrl+Shift+N", lambda: self.new_window(private=True))
        m.addSeparator()
        m.addAction("Bookmarks\tCtrl+Shift+O", lambda: self.toggle_panel("bookmarks"))
        m.addAction("History\tCtrl+H", lambda: self.toggle_panel("history"))
        m.addAction("Downloads\tCtrl+J", lambda: self.toggle_panel("downloads"))
        m.addSeparator()
        zm = m.addMenu("Zoom")
        zm.addAction("Zoom in\tCtrl++", lambda: self.zoom_step(1))
        zm.addAction("Zoom out\tCtrl+-", lambda: self.zoom_step(-1))
        zm.addAction("Actual size\tCtrl+0", lambda: self.set_zoom(1.0))
        m.addAction("Find in page …\tCtrl+F", lambda: self.find.open_bar())
        m.addAction("Print …\tCtrl+P", self.print_page)
        m.addAction("Save page as PDF …", self.save_pdf)
        m.addAction("Full screen\tF11", self.toggle_fullscreen)
        more = m.addMenu("More tools")
        more.addAction("View page source\tCtrl+U", self.view_source)
        more.addAction("Developer tools\tF12", self.dev_tools)
        more.addAction("Clear browsing data …", self.clear_data)
        m.addSeparator()
        m.addAction("Settings", self.open_settings)
        m.addAction(f"About {APP_NAME}", self.about)
        return m

    def about(self):
        ui.about_dialog(self, APP_NAME,
                        f"<b>{APP_NAME}</b> {VERSION}<br>A web browser on Chromium (Qt WebEngine) in the Digonto family.<br><br>"
                        "Free and open source (AGPL-3.0). No account, no tracking by Digonto.",
                        ui.app_icon(HERE, SLUG))

    def open_settings(self, part=""):
        """Settings is a page in a tab (digonto://settings), like in Chrome; reuse it if it is already open"""
        target = "digonto://settings" + (f"#{part}" if part else "")
        for i in range(self.tabs.count()):
            if self.page_at(i).view.url().toString().startswith("digonto://settings"):
                self.tabs.setCurrentIndex(i)
                if part:
                    self.page_at(i).view.setUrl(QUrl(target))
                return
        self.add_tab(target, after_current=True)

    def clear_data(self):
        self.open_settings("privacy")

    def shortcuts(self):
        def sc(keys, fn):
            for k in (keys if isinstance(keys, (list, tuple)) else [keys]):
                s = QShortcut(QKeySequence(k), self)
                s.setContext(Qt.WindowShortcut)
                s.activated.connect(fn)
        sc("Ctrl+T", lambda: self.add_tab(urls.NEWTAB))
        sc(["Ctrl+W", "Ctrl+F4"], lambda: self.close_tab(self.tabs.currentIndex()))
        sc("Ctrl+Shift+T", self.reopen_tab)
        sc("Ctrl+N", self.new_window)
        sc("Ctrl+Shift+N", lambda: self.new_window(private=True))
        sc(["Ctrl+Tab", "Ctrl+PgDown"], lambda: self.tabs.setCurrentIndex((self.tabs.currentIndex() + 1) % self.tabs.count()))
        sc(["Ctrl+Shift+Tab", "Ctrl+PgUp"], lambda: self.tabs.setCurrentIndex((self.tabs.currentIndex() - 1) % self.tabs.count()))
        for n in range(1, 9):
            sc(f"Ctrl+{n}", lambda n=n: self.tabs.setCurrentIndex(min(n - 1, self.tabs.count() - 1)))
        sc("Ctrl+9", lambda: self.tabs.setCurrentIndex(self.tabs.count() - 1))
        sc(["Ctrl+L", "F6", "Alt+D"], lambda: (self.url.setFocus(), self.url.selectAll()))
        sc(["Ctrl+R", "F5"], lambda: self.view() and self.view().reload())
        sc(["Ctrl+Shift+R", "Shift+F5"], lambda: self.view() and self.view().triggerPageAction(QWebEnginePage.WebAction.ReloadAndBypassCache))
        sc("Alt+Left", lambda: self.view() and self.view().back())
        sc("Alt+Right", lambda: self.view() and self.view().forward())
        sc("Ctrl+D", self.toggle_bookmark)
        sc("Ctrl+H", lambda: self.toggle_panel("history"))
        sc("Ctrl+J", lambda: self.toggle_panel("downloads"))
        sc("Ctrl+Shift+O", lambda: self.toggle_panel("bookmarks"))
        sc(["Ctrl+F", "F3"], self.find.open_bar)
        sc("Ctrl+P", self.print_page)
        sc(["Ctrl++", "Ctrl+="], lambda: self.zoom_step(1))
        sc("Ctrl+-", lambda: self.zoom_step(-1))
        sc("Ctrl+0", lambda: self.set_zoom(1.0))
        sc("F11", self.toggle_fullscreen)
        sc(["F12", "Ctrl+Shift+I"], self.dev_tools)
        sc("Ctrl+U", self.view_source)
        sc("Ctrl+Shift+B", lambda: (SETTINGS.__setitem__("show_bookmarks_bar", not SETTINGS["show_bookmarks_bar"]), self.fill_bbar()))

    def eventFilter(self, obj, e):
        t = e.type()
        if obj is self.tabs and t == QEvent.MouseButtonRelease and e.button() == Qt.MiddleButton:
            i = self.tabs.tabAt(e.position().toPoint())
            if i >= 0:
                self.close_tab(i)
                return True
        return super().eventFilter(obj, e)

    def closeEvent(self, e):
        if not self.private:
            tabs = []
            for i in range(self.tabs.count()):
                u = self.page_at(i).view.url().toString()
                if u and not u.startswith(urls.NEWTAB):
                    tabs.append(u)
            store.save_session({"tabs": tabs, "current": max(0, self.tabs.currentIndex()), "time": time.time()})
        for w in self.popups + self.dev_windows:
            try:
                w.close()
            except RuntimeError:
                pass
        if self in WINDOWS:
            WINDOWS.remove(self)
        super().closeEvent(e)


# ---------------------------------------------------------------------------------------- single instance --
def _forward(args):
    """another copy is already open: hand it the addresses / files and exit"""
    from PySide6.QtNetwork import QLocalSocket
    s = QLocalSocket()
    s.connectToServer(ui._si_name(SLUG))
    if not s.waitForConnected(400):
        return False
    payload = [os.path.abspath(a) if os.path.exists(a) else a for a in args] or [""]
    s.write(json.dumps(payload).encode("utf-8"))
    ok = s.waitForBytesWritten(1500)
    s.waitForReadyRead(1500)
    s.disconnectFromServer()
    return bool(ok)


_SERVERS = []


def _serve(opener):
    """this copy receives the addresses / files of later launches (a link clicked in another program, ...)"""
    from PySide6.QtNetwork import QLocalServer
    name = ui._si_name(SLUG)
    QLocalServer.removeServer(name)
    srv = QLocalServer(QApplication.instance())
    if not srv.listen(name):
        return
    _SERVERS.append(srv)

    def got():
        while srv.hasPendingConnections():
            c = srv.nextPendingConnection()
            c.waitForReadyRead(800)
            try:
                items = json.loads(bytes(c.readAll()).decode("utf-8"))
            except ValueError:
                items = []
            for a in items if isinstance(items, list) else []:
                try:
                    opener(a)
                except Exception:
                    pass
            c.write(b"ok")
            c.flush()
            c.waitForBytesWritten(500)
            c.disconnectFromServer()
    srv.newConnection.connect(got)


def _target(a):
    if not a:
        return urls.NEWTAB
    if os.path.exists(a):
        return QUrl.fromLocalFile(os.path.abspath(a)).toString()
    return urls.fix(a, SETTINGS["engine"])


def main():
    if "--version" in sys.argv:
        print(VERSION)
        return
    ui.mac_app_name(APP_NAME)
    pages.register_scheme()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    app = QApplication(sys.argv)
    if _forward(args):
        os._exit(0)
    ui.setup_app(app, APP_NAME, SLUG, ui.app_icon(HERE, SLUG))
    no_app_filters(app)
    global SETTINGS, BOOKMARKS, HISTORY, ZOOM
    SETTINGS, BOOKMARKS, HISTORY, ZOOM = store.Settings(), store.Bookmarks(), store.History(), store.Zoom()
    DOWNLOAD_LISTENERS.append(lambda req: WINDOWS and WINDOWS[-1].show_downloads(req))
    w = Main(restore=not args, start=[_target(a) for a in args])
    w.show()

    def _open(a):
        win = next((x for x in reversed(WINDOWS) if not x.private), None) or Main()
        if a:
            win.add_tab(_target(a))
        win.show()
        win.raise_()
        win.activateWindow()
        return win
    _serve(_open)
    rc = app.exec()
    os._exit(rc)


if __name__ == "__main__":
    main()
