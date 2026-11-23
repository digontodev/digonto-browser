"""Downloads through Qt's network stack: it trusts the same certificates as the operating system (macOS keychain,
Windows store, Linux CA bundle). Python's urllib in the packed app often finds no certificates on macOS
('CERTIFICATE_VERIFY_FAILED'), so the browser never uses it."""
from PySide6.QtCore import QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkProxyFactory, QNetworkReply, QNetworkRequest

_NAM = None
_LIVE = set()                      # replies in flight (kept alive until finished)


def get(url, done, timeout_ms=60000, user_agent=None):
    """download url; done(data: bytes | None, error: str) is called on the main thread"""
    global _NAM
    if _NAM is None:
        QNetworkProxyFactory.setUseSystemConfiguration(True)          # the system's proxy, like the web pages use
        _NAM = QNetworkAccessManager()
    req = QNetworkRequest(QUrl(url))
    req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                     QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
    req.setTransferTimeout(timeout_ms)
    if user_agent:
        req.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, user_agent)
    reply = _NAM.get(req)
    _LIVE.add(reply)

    def finished():
        _LIVE.discard(reply)
        if reply.error() == QNetworkReply.NetworkError.NoError:
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 200
            data = bytes(reply.readAll())
            if int(status) >= 400:
                done(None, f"the server answered {status}")
            else:
                done(data, "")
        else:
            done(None, reply.errorString())
        reply.deleteLater()
    reply.finished.connect(finished)
    return reply
