# Digonto Browser

A web browser on Chromium (Qt WebEngine) in the Digonto look: tabs, bookmarks, history, downloads, private windows, and soon Chrome extensions.

Part of the **Digonto** programs - [digonto.dev](https://digonto.dev). No account, no tracking by Digonto: your history, bookmarks and passwords stay on your computer.

## Download

Get the newest version from the **[Releases page](https://github.com/digontodev/digonto-browser/releases/latest)**:

- Windows 10/11: the `.exe` setup
- macOS 13 or newer: `…-macos-apple-chip.dmg` for M1 and newer, `…-macos-intel.dmg` for Intel Macs
- Ubuntu 24.04+ / Debian 13+: the `.deb`

## What it does

- Tabs: drag to reorder, middle-click to close, **Ctrl+Shift+T** reopens a closed tab, the last tabs come back on start
- Address bar: type an address or words to search; suggestions from your history and bookmarks
- Bookmarks (**Ctrl+D**) and a bookmarks bar, history (**Ctrl+H**), downloads (**Ctrl+J**)
- Private windows (**Ctrl+Shift+N**): no history, no cookies after closing
- Zoom remembered per site, find in page (**Ctrl+F**), print, save as PDF, full screen (**F11**), developer tools (**F12**)
- Asks before a site may use your camera, microphone, location or notifications
- Third-party cookies blocked by default; DuckDuckGo search by default (Startpage, Brave, Ecosia, Google, Bing, Qwant in Settings)

## Digonto Ad Blocker (built in)

On by default: blocks ads and trackers (EasyList + EasyPrivacy, about 52,000 rules, updated weekly) and hides empty ad boxes.
The shield in the top bar shows how many things were blocked on the page and turns blocking off for one site;
the **Extensions** page switches it off completely. Works in private windows too.

## Chrome extensions

The **Extensions** page (🧩 in the top bar) installs Manifest V3 extensions from a Chrome Web Store link, a `.crx` / `.zip` file
or a folder; on the Chrome Web Store an "Add to Digonto Browser" bar appears above the page. After installing, Digonto
shows whether the extension works. Their buttons and pop-ups go in the top bar. Chrome extensions don't run in private windows.

## Coming next

1. Saved passwords in the system keychain, importing bookmarks from Chrome / Firefox, default browser
2. Inside Digonto Studio

Not possible: videos with copy protection (Netflix, Disney+, Prime Video). They need Google's Widevine module, which the free Chromium engine does not have.

## Run from source

```
pip install --require-hashes --only-binary=:all: -r requirements.txt
python digonto_browser.py
```

## Licence

AGPL-3.0 - see [LICENSE](LICENSE).
