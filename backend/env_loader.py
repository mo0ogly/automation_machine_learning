"""
env_loader.py — Single source for backend secrets/config.

Loads ``backend/.env`` (gitignored) into the process environment without
overriding values already present, mirroring the convention used elsewhere in
the project. Import this at the top of any standalone script.
"""

import os
from pathlib import Path


def load_backend_env():
    here = Path(__file__).resolve().parent
    for base in (here, here.parent):
        env_file = base / ".env"
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())
        break


def get(key: str, default=None):
    return os.environ.get(key, default)


def _mitmproxy_listen_addr():
    """Derive mitmproxy's (host, port) from proxy env, default 127.0.0.1:8080."""
    proxy = (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
             or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or "")
    host, port = "127.0.0.1", 8080
    if "://" in proxy:
        proxy = proxy.split("://", 1)[1]
    if "@" in proxy:
        proxy = proxy.split("@", 1)[1]
    if proxy:
        hp = proxy.rstrip("/").split(":")
        host = hp[0] or host
        if len(hp) > 1 and hp[1].isdigit():
            port = int(hp[1])
    return host, port


def ensure_tls_ca():
    """Stop a stale mitmproxy CA pin from breaking direct HTTPS (e.g. Groq).

    If SSL_CERT_FILE/REQUESTS_CA_BUNDLE is pinned to the mitmproxy CA but
    mitmproxy is not listening, public endpoints present their real chain which
    that CA cannot verify -> CERTIFICATE_VERIFY_FAILED. In that case, fall back
    to the certifi bundle. No-op when there is no mitmproxy pin or mitmproxy is
    actually up (interception stays intact).
    """
    import socket

    pin = os.environ.get("SSL_CERT_FILE", "") or os.environ.get("REQUESTS_CA_BUNDLE", "")
    if "mitmproxy" not in pin.lower():
        return
    host, port = _mitmproxy_listen_addr()
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return  # mitmproxy up -> keep the pin
    except OSError:
        pass
    try:
        import certifi
    except ImportError:
        return
    ca = certifi.where()
    os.environ["SSL_CERT_FILE"] = ca
    os.environ["REQUESTS_CA_BUNDLE"] = ca


# Load eagerly on import.
load_backend_env()
ensure_tls_ca()
