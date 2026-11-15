"""
Pulls a brand out of the clean title with a known-brand list, so the
matching step can use it as an extra signal alongside the MinHash
similarity: two listings only match if their titles are similar AND their
brands agree.

A brand must match WHOLE WORDS, not pieces of words.
Multi-word brands ("Under Armour") are matched by joining up to 3 neighbouring words, which
is why the list stores them joined: "underarmour", "northface", "levis".
"""

from .famous_brands import KNOWN_BRANDS

_BRAND_SET = set(KNOWN_BRANDS)
_MAX_WORDS_IN_BRAND = 3


def extract_brand(clean_title):
    words = clean_title.split()
    for i in range(len(words)):
        for n in range(1, _MAX_WORDS_IN_BRAND + 1):
            candidate = "".join(words[i:i + n])
            if candidate in _BRAND_SET:
                return candidate
    return None


def extract_attributes(listing):
    # Returns a NEW dict with brand
    enriched = dict(listing)
    enriched["brand"] = extract_brand(listing["clean_title"])
    return enriched


def extract_all(listings):
    return [extract_attributes(l) for l in listings]
