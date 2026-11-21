# Digonto Browser

A web browser on Chromium (Qt WebEngine) in the Digonto look: tabs, bookmarks, history, downloads, private windows, and soon Chrome extensions.

Part of the **Digonto** programs - [digonto.dev](https://digonto.dev). No account, no tracking by Digonto: your history, bookmarks and passwords stay on your computer.

## Download

Get the newest version from the **[Releases page](https://github.com/digontodev/digonto-browser/releases/latest)**:

- Windows 10/11: the `.exe` setup
- macOS 13 or newer: the `.dmg`
- Ubuntu 24.04+ / Debian 13+: the `.deb`

## What it does

- Tabs: drag to reorder, middle-click to close, **Ctrl+Shift+T** reopens a closed tab, the last tabs come back on start
- Address bar: type an address or words to search; suggestions from your history and bookmarks
- Bookmarks (**Ctrl+D**) and a bookmarks bar, history (**Ctrl+H**), downloads (**Ctrl+J**)
- Private windows (**Ctrl+Shift+N**): no history, no cookies after closing
- Zoom remembered per site, find in page (**Ctrl+F**), print, save as PDF, full screen (**F11**), developer tools (**F12**)
- Asks before a site may use your camera, microphone, location or notifications
- Third-party cookies blocked by default; DuckDuckGo search by default (Startpage, Brave, Ecosia, Google, Bing, Qwant in Settings)

## Coming next

1. Chrome extensions (Manifest V3) from the Chrome Web Store, a `.zip` or a folder
2. Ad and tracker blocking, saved passwords in the system keychain, importing bookmarks from Chrome / Firefox, default browser
3. Inside Digonto Studio

Not possible: videos with copy protection (Netflix, Disney+, Prime Video). They need Google's Widevine module, which the free Chromium engine does not have.

## Run from source

```
pip install --require-hashes --only-binary=:all: -r requirements.txt
python digonto_browser.py
```

## Licence

AGPL-3.0 - see [LICENSE](LICENSE).
