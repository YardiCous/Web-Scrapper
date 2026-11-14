"""Supported dummy storefronts and URL validation shared by the site and collectors."""

import re
from urllib.parse import parse_qs, urlsplit, urlunsplit

PLATFORMS = {
    "cartlane": {"path": "/dummysite/", "port": 8101},
    "tao": {"path": "/dummysite2/", "port": 8102},
    "lazora": {"path": "/dummysite3/", "port": 8103},
}


def resolve_url(value):
    """Return (platform, canonical URL), accepting only the dummy site pages."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Enter a product URL from one of the supported dummy sites.")
    try:
        parts = urlsplit(value.strip())
        if (parts.scheme not in {"http", "https"}
                or parts.hostname != "paegnium.github.io"
                or parts.username is not None or parts.password is not None
                or parts.port not in {None, 80, 443}):
            raise ValueError
    except ValueError:
        raise ValueError("Use a URL from one of the supported dummy sites.") from None

    for platform, config in PLATFORMS.items():
        base = config["path"]
        if (parts.path in {base.rstrip("/"), base, base + "index.html"}
                or (platform == "tao" and parts.path == base + "products/index.html")):
            path = base
        elif platform == "tao" and re.fullmatch(re.escape(base) + r"products/\d+\.html", parts.path):
            path = parts.path
        else:
            continue
        query = parse_qs(parts.query, keep_blank_values=True)
        if query and (platform != "cartlane" or set(query) != {"product"}
                      or len(query["product"]) != 1
                      or not re.fullmatch(r"\d+", query["product"][0])):
            break
        if parts.fragment and (platform != "lazora"
                               or not re.fullmatch(r"product-\d+", parts.fragment)):
            break
        return platform, urlunsplit(("https", "paegnium.github.io", path, parts.query, parts.fragment))
    raise ValueError("Use a product or storefront URL from one of the three supported dummy sites.")
