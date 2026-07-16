"""Small, dependency-free credential scrubber for generator diagnostics.

The static generators intentionally fail soft when an internal HTTP dependency is
unavailable.  ``requests`` exception strings can contain the complete request URL,
so sanitize at the final print/log boundary rather than relying on every caller to
construct credential-free URLs.
"""

import re


_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_=-]+\.[A-Za-z0-9_=-]+\.?[A-Za-z0-9_=-]*")
_SECRET_QUERY_RE = re.compile(
    r"(?i)(?P<name>(?:access_|refresh_)?token|api_?key|key)=(?P<value>[^&\s'\"]+)"
)
_LEGACY_LOGIN_RE = re.compile(r"(?i)(/login/api/)[^/?#\s'\"]+")


def scrub_secret_text(value, service_key=None):
    """Return printable text with URL credentials and JWT-shaped values removed."""
    text = str(value)
    text = _SECRET_QUERY_RE.sub(lambda match: "%s=***" % match.group("name"), text)
    text = _LEGACY_LOGIN_RE.sub(r"\1***", text)
    text = _JWT_RE.sub("eyJ***", text)
    if service_key:
        text = text.replace(str(service_key), "***")
    return text
