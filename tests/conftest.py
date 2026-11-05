from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from stock_service.api import create_app
from stock_service.db import make_engine, stock
from stock_service.seed import load_snapshot

SNAPSHOT = Path(__file__).parent.parent / "Store Stock Snapshot, 7 March 2025 06:45.csv"
TTL_SECONDS = 600


@pytest.fixture
def engine(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    load_snapshot(engine, str(SNAPSHOT))
    yield engine
    engine.dispose()


@pytest.fixture
def client(engine):
    with TestClient(create_app(engine, ttl_seconds=TTL_SECONDS)) as client:
        yield client


def stock_row(engine, store_id, product_id):
    with engine.connect() as conn:
        return conn.execute(
            select(stock).where(stock.c.store_id == store_id, stock.c.product_id == product_id)
        ).one()


def available(client, store_id, product_id):
    products = client.get(f"/stores/{store_id}/products").json()["products"]
    return next((p["availableQuantity"] for p in products if p["productId"] == product_id), 0)
