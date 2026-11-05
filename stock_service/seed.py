"""Load a store stock snapshot CSV into an empty database.

Usage: python -m stock_service.seed "Store Stock Snapshot, 7 March 2025 06:45.csv"
"""
import csv
import sys

from sqlalchemy import Engine

from . import config
from .db import make_engine, metadata, stock, stores


def load_snapshot(engine: Engine, path: str) -> None:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))  # store_id stays a string, so "09815" keeps its leading zero
    store_rows = {
        r["store_id"]: {"store_id": r["store_id"], "name": r["store_name"], "is_open": r["store_open"] == "true"}
        for r in rows
    }
    stock_rows = [
        {
            "store_id": r["store_id"],
            "product_id": r["component_id"],
            "name": r["component_name"],
            "type": r["component_type"],
            "quantity_on_hand": int(r["quantity_on_hand"]),
            "reserved_quantity": int(r["reserved_quantity"]),
        }
        for r in rows
    ]
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(stores.insert(), list(store_rows.values()))
        conn.execute(stock.insert(), stock_rows)


if __name__ == "__main__":
    load_snapshot(make_engine(config.DATABASE_URL), sys.argv[1])
