import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_conn():
    # Containers use libpq's PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE variables.
    # Keep DATABASE_URL support for running the Flask app and scraper locally.
    return psycopg2.connect(os.environ.get("DATABASE_URL") or "")
