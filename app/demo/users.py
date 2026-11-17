"""Demo only: a demo_user cookie picks Alice (premium, editor), Bob (basic, viewer) or Signed out ("none").

Real apps authenticate in get_current_user (app/auth.py) with their session or token; the examples only
take the CurrentUser dependency and call can() and can_read_file().

Pages that show user context or authorization offer a switch (PAGES). Every other page signs in as
Alice, so a choice made on one page never breaks another.
"""

from fastapi import Request, Response
from starlette.requests import HTTPConnection

USERS = ("alice", "bob")

LABELS = {"alice": "Alice (premium, editor)", "bob": "Bob (basic, viewer)", "none": "Signed out"}

PAGES: dict[str, list[str]] = {
    "load-definition-variables-data": ["alice", "bob"],   # compare premium and basic customer variables
    "resume-progress": ["alice", "bob"],                  # keep an independent draft for each respondent
    "creator-load-save": ["alice", "bob"],                # Bob's saves answer 403 (can(user, "edit-forms"))
}
"""Example slug => the users its switch offers. The first is the default."""

_YEAR = 365 * 24 * 3600


def for_page(slug: str) -> list[str]:
    """The users an example page offers; one means no switch."""
    return PAGES.get(slug, ["alice"])


def page_user(slug: str, conn: HTTPConnection) -> str:
    """The cookie's user if the page offers it, otherwise the page's default."""
    users = for_page(slug)
    cookie = conn.cookies.get("demo_user")
    return cookie if cookie in users else users[0]


def demo_user_key(conn: HTTPConnection) -> str | None:
    """The demo user a request runs as. A page that signed in (sign_in_for_page) wins over the cookie. /claim is
    Option A of load-definition-variables-data: it renders that example's page, so it signs in the same way."""
    if (key := conn.scope.get("state", {}).get("demo_user")) is not None:
        return key
    if conn.url.path == "/claim":
        return page_user("load-definition-variables-data", conn)
    key = conn.cookies.get("demo_user")
    return key if key in USERS else None


def sign_in_for_page(slug: str, request: Request, response: Response) -> None:
    """On an example page: keep the cookie's user if the page offers it, otherwise sign in as the page's default
    and set demo_user to it. host.js writes the cookie back on each tab's focus, so it isn't httponly."""
    key = page_user(slug, request)
    request.scope.setdefault("state", {})["demo_user"] = key
    if request.cookies.get("demo_user") != key:
        response.set_cookie("demo_user", key, max_age=_YEAR, path="/", samesite="lax", httponly=False,
                            secure=request.url.scheme == "https")


def user_key(conn: HTTPConnection) -> str:
    """The current demo user's key for the page config: alice, bob or none."""
    return demo_user_key(conn) or "none"
