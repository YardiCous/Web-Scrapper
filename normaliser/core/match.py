"""
Flow:
  Shingling    -> turn each clean_title into a set of character n-grams
  MinHash      -> compress each shingle set into a compact signature
  LSH          -> use the signatures to find CANDIDATE pairs,
                  instead of comparing all listings to all others

  Verification -> for each candidate pair, check real title similarity
                     + brand agreement before accepting it as a match

Output of this file: a list of verified (id_a, id_b, similarity) pairs.
"""
from datasketch import MinHash, MinHashLSH
from rapidfuzz import fuzz

NUM_PERM = 128          # more permutations = more accurate MinHash, slower
LSH_THRESHOLD = 0.15    # generous on purpose; verification step filters harder
TITLE_SIM_THRESHOLD = 55     # 0-100 scale, used when brand is known and agrees
FALLBACK_SIM_THRESHOLD = 75  # stricter bar used when brand is unknown/missing
SHINGLE_K = 3


def to_shingles(clean_title, k=SHINGLE_K):
    # Character k-grams, spaces removed so shingles span word boundaries
    text = clean_title.replace(" ", "")
    if len(text) < k:
        return {text}
    return {text[i:i + k] for i in range(len(text) - k + 1)}


def build_minhash(shingle_set, num_perm=NUM_PERM):
    m = MinHash(num_perm=num_perm)
    for shingle in shingle_set:
        m.update(shingle.encode("utf8"))
    return m


def listing_id(listing):
    return f"{listing['source_platform']}:{listing['source_listing_id']}"


def build_lsh_index(listings, threshold=LSH_THRESHOLD, num_perm=NUM_PERM):
    """
    Returns (lsh, minhashes) where minhashes maps listing_id -> MinHash,
    and every listing has already been inserted into the LSH index.
    """
    lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
    minhashes = {}
    for listing in listings:
        shingles = to_shingles(listing["clean_title"])
        mh = build_minhash(shingles, num_perm)
        lid = listing_id(listing)
        minhashes[lid] = mh
        lsh.insert(lid, mh)
    return lsh, minhashes


def get_candidate_pairs(lsh, minhashes):
    """
    Query the LSH index with every listing's signature. This is the
    step that avoids comparing all N listings to all other N.
    LSH only returns the ones that are likely similar.
    """
    seen = set()
    pairs = []
    for lid, mh in minhashes.items():
        for other_id in lsh.query(mh):
            if other_id == lid:
                continue
            pair_key = tuple(sorted((lid, other_id)))
            if pair_key in seen:
                continue
            seen.add(pair_key)
            pairs.append(pair_key)
    return pairs


# Product-line modifier words. If one title has one of these and the
# other doesn't, they're treated as DIFFERENT products even if title
# similarity is high -- e.g. "Apple AirPods" vs "Apple AirPods Max" are
# different products
DISTINGUISHING_WORDS = {
    "mini", "max", "pro", "plus", "ultra", "se", "lite", "air",
    "classic", "premium", "essential",
}


def _has_distinguishing_conflict(clean_title_a, clean_title_b):
    tokens_a = set(clean_title_a.split())
    tokens_b = set(clean_title_b.split())
    asymmetric_tokens = (tokens_a - tokens_b) | (tokens_b - tokens_a)
    return bool(asymmetric_tokens & DISTINGUISHING_WORDS)


def verify_pair(listing_a, listing_b,
                 title_sim_threshold=TITLE_SIM_THRESHOLD,
                 fallback_threshold=FALLBACK_SIM_THRESHOLD):
    """
    Decide whether a CANDIDATE pair is actually a match.

    - If both have a recognised brand: require the brands to agree AND
      title similarity above the (lower) threshold.
    - If either brand is unknown: fall back to a stricter title-only bar,
      since we have one less signal to lean on.
    """

    if _has_distinguishing_conflict(listing_a["clean_title"], listing_b["clean_title"]):
        return False

    sim = fuzz.ratio(listing_a["clean_title"], listing_b["clean_title"])
    if listing_a["brand"] and listing_b["brand"]:
        return listing_a["brand"] == listing_b["brand"] and sim >= title_sim_threshold
    return sim >= fallback_threshold


def find_matches(listings):
    lsh, minhashes = build_lsh_index(listings)
    candidates = get_candidate_pairs(lsh, minhashes)

    by_id = {listing_id(l): l for l in listings}
    verified = []
    for id_a, id_b in candidates:
        a, b = by_id[id_a], by_id[id_b]
        if verify_pair(a, b):
            sim = fuzz.ratio(a["clean_title"], b["clean_title"])
            verified.append((id_a, id_b, round(sim, 1)))

    return verified


if __name__ == "__main__":
    from core.loader import load_real_listings
    from core.paths import REAL_DATA_PATHS as DATA_PATHS
    from core.clean import clean_all
    from core.extract import extract_all

    listings = extract_all(clean_all(load_real_listings(DATA_PATHS)))
    by_id = {listing_id(l): l for l in listings}

    matches = find_matches(listings)
    print(f"Verified {len(matches)} matching pairs\n")
    for id_a, id_b, sim in sorted(matches, key=lambda m: -m[2]):
        print(f"{sim:5.1f}  {id_a:20} <-> {id_b:20}")
        print(f"        '{by_id[id_a]['title']}'")
        print(f"        '{by_id[id_b]['title']}'")
