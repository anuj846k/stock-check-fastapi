from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Engine,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
)

metadata = MetaData()

stores = Table(
    "stores",
    metadata,
    Column("store_id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("is_open", Boolean, nullable=False),
)

stock = Table(
    "stock",
    metadata,
    Column("store_id", String, ForeignKey("stores.store_id"), primary_key=True),
    Column("product_id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("type", String, nullable=False),
    Column("quantity_on_hand", Integer, nullable=False),
    Column("reserved_quantity", Integer, nullable=False, default=0),
)

reservations = Table(
    "reservations",
    metadata,
    Column("reservation_id", String, primary_key=True),
    Column("store_id", String, nullable=False),
    Column("product_id", String, nullable=False),
    Column("quantity", Integer, nullable=False),
    # pending -> confirmed | released | expired
    Column("status", String, nullable=False, index=True),
    Column("expires_at", DateTime, nullable=False, index=True),
)


def make_engine(url: str) -> Engine:
    # SQLite: wait for the write lock instead of failing under concurrent checkouts.
    connect_args = {"timeout": 30, "check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)
