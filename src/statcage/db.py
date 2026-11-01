"""Connect to the StatCage Postgres database.

Settings come from environment variables, with the password read from .env,
so no secret is ever written in the code.
"""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5433"),
        dbname=os.environ.get("POSTGRES_DB", "statcage"),
        user=os.environ.get("POSTGRES_USER", "statcage"),
        password=os.environ["POSTGRES_PASSWORD"],
    )
