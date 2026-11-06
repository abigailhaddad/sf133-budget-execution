"""The only code that talks to MAX.gov: polite, honest, and stops at the first sign of a block.

Rules, all of them on purpose:
  * An honest User-Agent that says who is asking and where to read about it.
  * One request at a time, with a pause (SF133_PAUSE seconds, default 6) between requests.
  * robots.txt is read first. MAX.gov's says `User-agent: * / Disallow: /`, which disallows every
    automated visit. This code therefore refuses to run unless the owner has decided to go ahead and
    says so with SF133_OVERRIDE_ROBOTS=yes. See HANDOFF.md.
  * 401, 403 and 429 stop the run. A challenge or login page where a file should be stops the run.
    Nothing here retries around a block, rotates addresses or changes the User-Agent.
"""
import os
import sys
import time
import urllib.error
import urllib.request
from urllib.robotparser import RobotFileParser

UA = "sf133-dataset (public data research; https://github.com/abigailhaddad/sf133-budget-execution)"
ROBOTS_URL = "https://portal.max.gov/robots.txt"
BLOCK_CODES = (401, 403, 429)


class Blocked(Exception):
    """The server said no, or showed a challenge. Do not try again today."""


class RobotsDisallow(Exception):
    """robots.txt disallows automated access and the owner has not overridden that."""


def pause():
    time.sleep(float(os.environ.get("SF133_PAUSE", "6")))


def get(url, accept_html=True, timeout=120, opener=urllib.request.urlopen):
    """GET one URL. Returns (status, headers, body bytes). Raises Blocked on 401/403/429."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with opener(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        if e.code in BLOCK_CODES:
            raise Blocked(f"{url} answered {e.code}") from e
        return e.code, dict(e.headers or {}), b""


def robots_allows(url, fetch=None):
    """True if robots.txt allows our User-Agent to fetch url.

    fetch(robots_url) -> text. Passed in by the tests; by default it makes one real request."""
    if fetch is None:
        status, _, body = get(ROBOTS_URL)
        text = body.decode("utf-8", "replace") if status == 200 else ""
    else:
        text = fetch(ROBOTS_URL)
    rp = RobotFileParser()
    rp.parse(text.splitlines())
    return rp.can_fetch(UA, url)


def require_permission(url, fetch=None):
    """Raise RobotsDisallow unless robots.txt allows url or the owner overrode it."""
    if os.environ.get("SF133_OVERRIDE_ROBOTS", "").lower() == "yes":
        print("NOTE: SF133_OVERRIDE_ROBOTS=yes. robots.txt is being set aside on the owner's say-so.", file=sys.stderr)
        return
    if not robots_allows(url, fetch):
        raise RobotsDisallow(
            "MAX.gov's robots.txt disallows automated access (User-agent: * / Disallow: /). "
            "Nothing was requested beyond robots.txt. To go ahead anyway, the owner sets "
            "SF133_OVERRIDE_ROBOTS=yes (the workflow reads the repo variable of that name). "
            "See HANDOFF.md, 'Automatic refresh'.")
