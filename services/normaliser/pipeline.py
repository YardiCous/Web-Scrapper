"""Standardise raw listings and extract their brand and common attributes."""
from .core.loader import adapt_record
from .core.clean import clean_listing
from .core.extract import extract_attributes
from shared.listings import listing_id


def normalise_record(raw):
    record = extract_attributes(clean_listing(adapt_record(raw)))
    record["listing_id"] = listing_id(record)
    return record
