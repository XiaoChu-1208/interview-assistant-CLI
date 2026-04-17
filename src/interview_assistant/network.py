"""Network: connectivity probe + system-proxy auto-detection.

The whole purpose: a user in mainland China (or behind any corporate firewall)
gets blocked from Groq / OpenAI on the first run, and we want to either
auto-detect their existing local proxy (Clash / Surge / V2Ray / Stash / etc.)
or hand-hold them into pasting one.
"""
from __future__ import annotations

import os
import socket
import subprocess
from dataclasses import dataclass

import httpx


COMMON_LOCAL_PROXY_PORTS = (
    7890,   # Clash / Clash Verge
    7891,   # Clash secondary
    7897,   # Clash Verge Rev
    6152,   # Surge HTTP
    6153,   # Surge HTTPS
    1087,   # Shadowsocks-NG (HTTP)
    1080,   # SOCKS5 (won't be HTTP, but worth noting)
    8118,   # Privoxy
    10809,  # V2RayN HTTP
    10810,  # V2RayN
    20171,  # Lantern
    8888,   # Charles
    7777,   # Stash
)


# A handful of probe URLs — we only need to confirm general internet works,
# and that the LLM endpoint specifically is reachable. Keep this list tiny
# and fast.
PROBE_URLS = {
    "groq":     "https://api.groq.com/openai/v1/models",
    "openai":   "https://api.openai.com/v1/models",
    "internet": "https://www.cloudflare.com/cdn-cgi/trace",
}


@dataclass
class ConnResult:
    ok: bool
    status: int = 0
    error: str = ""
    elapsed_ms: int = 0


def probe(url: str, proxy: str = "", timeout: float = 6.0) -> ConnResult:
    """Single GET; returns ConnResult."""
    import time
    kw = {"timeout": timeout, "follow_redirects": True}
    if proxy:
        kw["proxy"] = proxy
    t0 = time.time()
    try:
        with httpx.Client(**kw) as c:
            r = c.get(url)
        return ConnResult(
            ok=(r.status_code in (200, 401, 403, 404)),  # auth/notfound also = reachable
            status=r.status_code,
            elapsed_ms=int((time.time() - t0) * 1000),
        )
    except Exception as e:
        return ConnResult(ok=False, error=str(e)[:160], elapsed_ms=int((time.time() - t0) * 1000))


def detect_system_proxy() -> str:
    """Return the first proxy URL we can find on this machine, or ''.

    Order:
      1. HTTPS_PROXY / HTTP_PROXY / ALL_PROXY env vars
      2. macOS `scutil --proxy` (system network preferences)
      3. Windows registry (ProxyEnable / ProxyServer)
      4. None
    """
    for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        val = os.environ.get(var, "").strip()
        if val:
            return val

    sysname = ""
    try:
        import platform
        sysname = platform.system()
    except Exception:
        pass

    if sysname == "Darwin":
        url = _detect_macos_proxy()
        if url:
            return url
    elif sysname == "Windows":
        url = _detect_windows_proxy()
        if url:
            return url
    elif sysname == "Linux":
        url = _detect_gsettings_proxy()
        if url:
            return url

    return ""


def _detect_macos_proxy() -> str:
    """Parse `scutil --proxy` for HTTPEnable + HTTPProxy + HTTPPort."""
    try:
        out = subprocess.run(
            ["scutil", "--proxy"], capture_output=True, text=True, timeout=3,
        ).stdout
    except Exception:
        return ""

    parsed: dict[str, str] = {}
    for line in out.splitlines():
        s = line.strip()
        if ":" in s:
            k, _, v = s.partition(":")
            parsed[k.strip()] = v.strip()

    if parsed.get("HTTPSEnable") == "1":
        host = parsed.get("HTTPSProxy", "")
        port = parsed.get("HTTPSPort", "")
        if host and port:
            return f"http://{host}:{port}"
    if parsed.get("HTTPEnable") == "1":
        host = parsed.get("HTTPProxy", "")
        port = parsed.get("HTTPPort", "")
        if host and port:
            return f"http://{host}:{port}"
    return ""


def _detect_windows_proxy() -> str:
    try:
        import winreg  # type: ignore
    except ImportError:
        return ""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        )
        enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
        if not enabled:
            return ""
        server, _ = winreg.QueryValueEx(key, "ProxyServer")
    except Exception:
        return ""
    if not server:
        return ""
    if "=" in server:
        for part in server.split(";"):
            if part.startswith("https="):
                return f"http://{part[6:]}"
            if part.startswith("http="):
                return f"http://{part[5:]}"
    if not server.startswith("http"):
        server = f"http://{server}"
    return server


def _detect_gsettings_proxy() -> str:
    try:
        mode = subprocess.run(
            ["gsettings", "get", "org.gnome.system.proxy", "mode"],
            capture_output=True, text=True, timeout=2,
        ).stdout.strip().strip("'")
        if mode != "manual":
            return ""
        host = subprocess.run(
            ["gsettings", "get", "org.gnome.system.proxy.https", "host"],
            capture_output=True, text=True, timeout=2,
        ).stdout.strip().strip("'")
        port = subprocess.run(
            ["gsettings", "get", "org.gnome.system.proxy.https", "port"],
            capture_output=True, text=True, timeout=2,
        ).stdout.strip()
        if host and port:
            return f"http://{host}:{port}"
    except Exception:
        pass
    return ""


def scan_local_proxy_ports(host: str = "127.0.0.1") -> list[str]:
    """Quickly probe well-known local proxy ports; return reachable HTTP-ish URLs.

    A port that accepts a TCP connection might still not be an HTTP proxy, but
    we surface them in the wizard so the user can pick.
    """
    found: list[str] = []
    for port in COMMON_LOCAL_PROXY_PORTS:
        try:
            with socket.create_connection((host, port), timeout=0.25):
                found.append(f"http://{host}:{port}")
        except (socket.timeout, ConnectionRefusedError, OSError):
            continue
    return found


def is_proxy_alive(proxy: str, probe_url: str = PROBE_URLS["internet"]) -> ConnResult:
    """Confirm a proxy URL actually relays HTTP traffic."""
    return probe(probe_url, proxy=proxy, timeout=5.0)


def diagnose(target: str = "groq", proxy: str = "") -> dict:
    """Run the full triage: internet ok? target ok? what proxy does it take?

    Returns:
        {
          "internet": ConnResult,
          "target":   ConnResult,
          "system_proxy": str,
          "scanned_proxies": [str, ...],
          "needs_proxy": bool,
        }
    """
    target_url = PROBE_URLS.get(target, PROBE_URLS["groq"])
    inet = probe(PROBE_URLS["internet"], proxy=proxy)
    tgt = probe(target_url, proxy=proxy)
    out: dict = {
        "internet": inet,
        "target": tgt,
        "system_proxy": detect_system_proxy(),
        "scanned_proxies": [],
        "needs_proxy": (not tgt.ok),
    }
    if not tgt.ok and not proxy:
        out["scanned_proxies"] = scan_local_proxy_ports()
    return out
