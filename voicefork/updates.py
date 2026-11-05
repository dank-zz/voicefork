"""Tell the user when a newer Voicefork release is out.

One anonymous request to GitHub's public API, at most once a day. Nothing about the
user or their audio is sent. Turn it off with the environment variable
VOICEFORK_NO_UPDATE_CHECK=1.

In-app note: put one line like this anywhere in the GitHub release description,
    <!-- voicefork: Fixes GTX 1060 support and adds a desktop shortcut. -->
and the update bar shows it. It's an HTML comment, so it's hidden on the release page.
Leave it out and the bar only says a new version is out.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

from . import __version__

REPO = "Dank-zz/voicefork"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES = f"https://github.com/{REPO}/releases/latest"


def parse(v: str) -> tuple[int, ...]:
    """'v0.1.10' -> (0, 1, 10). Anything after the numbers (-beta, +build) is ignored."""
    m = re.match(r"\s*v?(\d+(?:\.\d+)*)", v or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def is_newer(latest: str, current: str = __version__) -> bool:
    a, b = parse(latest), parse(current)
    if not a or not b:
        return False
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


NOTE_MAX = 160
_NOTE = re.compile(r"<!--\s*voicefork\s*:(.*?)-->", re.IGNORECASE | re.DOTALL)


def note_from(body: str | None) -> str:
    """The in-app note from a release description: plain text, one line, at most NOTE_MAX chars."""
    m = _NOTE.search(body or "")
    if not m:
        return ""
    text = re.sub(r"<[^>]*>", "", m.group(1))          # no markup in the app
    text = " ".join(text.split())
    return text if len(text) <= NOTE_MAX else text[:NOTE_MAX - 1].rstrip() + "\u2026"


def disabled() -> bool:
    from . import net
    return (os.environ.get("VOICEFORK_NO_UPDATE_CHECK", "").strip() not in ("", "0")
            or net.is_offline() or net.from_env())


def latest_release(timeout: float = 4.0) -> tuple[str, str, str] | None:
    """(tag, page url, in-app note) of the newest published release, or None if unreachable."""
    req = urllib.request.Request(API, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"Voicefork/{__version__}",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
    except Exception:  # noqa: BLE001 - offline, rate-limited, GitHub down: just skip quietly
        return None
    if data.get("draft") or data.get("prerelease"):
        return None
    tag = data.get("tag_name") or ""
    return (tag, data.get("html_url") or RELEASES, note_from(data.get("body"))) if tag else None


def check(timeout: float = 4.0) -> tuple[str, str, str] | None:
    """The newer release, if there is one."""
    if disabled():
        return None
    rel = latest_release(timeout)
    return rel if rel and is_newer(rel[0]) else None
