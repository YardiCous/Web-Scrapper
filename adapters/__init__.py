"""Kafka adapters that run the team's code (web/scraper.py, normaliser/core) as pipeline services on
the cdc platform (infra/). They only move messages; the scraping, cleaning and matching logic is the
teammates' code, unchanged."""
