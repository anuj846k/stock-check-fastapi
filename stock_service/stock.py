import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Connection, Engine, select, update

from .db import reservations, stock, stores

available = stock.c.quantity_on_hand - stock.c.reserved_quantity


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def list_available(engine: Engine, store_id: str) -> list[dict]:
    """Products with available stock > 0. A closed store returns no products."""
    with engine.begin() as conn:
        release_expired(conn, utcnow())
        store = conn.execute(select(stores).where(stores.c.store_id == store_id)).first()
        if store is None:
            raise NotFound(f"Store {store_id} not found")
        if not store.is_open:
            return []
        rows = conn.execute(
            select(stock.c.product_id, stock.c.name, stock.c.type, available.label("available_quantity"))
            .where(stock.c.store_id == store_id, available > 0)
            .order_by(stock.c.product_id)
        )
        return [dict(row._mapping) for row in rows]


def reserve(engine: Engine, store_id: str, product_id: str, quantity: int, ttl_seconds: int) -> dict:
    now = utcnow()
    with engine.begin() as conn:
        release_expired(conn, now)
        # One conditional UPDATE: the check and the reservation are atomic.
        result = conn.execute(
            update(stock)
            .where(
                stock.c.store_id == store_id,
                stock.c.product_id == product_id,
                available >= quantity,
                stock.c.store_id.in_(select(stores.c.store_id).where(stores.c.is_open)),
            )
            .values(reserved_quantity=stock.c.reserved_quantity + quantity)
        )
        if result.rowcount != 1:
            _raise_reserve_failure(conn, store_id, product_id)
        reservation = {
            "reservation_id": str(uuid.uuid4()),
            "store_id": store_id,
            "product_id": product_id,
            "quantity": quantity,
            "status": "pending",
            "expires_at": now + timedelta(seconds=ttl_seconds),
        }
        conn.execute(reservations.insert().values(**reservation))
        return reservation


def confirm(engine: Engine, reservation_id: str) -> dict:
    """Payment succeeded: deduct physical stock and release the reservation."""
    with engine.begin() as conn:
        res = _close_pending(conn, reservation_id, "confirmed")
        conn.execute(
            update(stock)
            .where(stock.c.store_id == res.store_id, stock.c.product_id == res.product_id)
            .values(
                quantity_on_hand=stock.c.quantity_on_hand - res.quantity,
                reserved_quantity=stock.c.reserved_quantity - res.quantity,
            )
        )
        return _get(conn, reservation_id)


def release(engine: Engine, reservation_id: str) -> dict:
    """Payment failed: release the reservation and make the stock available again."""
    with engine.begin() as conn:
        res = _close_pending(conn, reservation_id, "released")
        _unreserve(conn, res)
        return _get(conn, reservation_id)


def release_expired(conn: Connection, now: datetime) -> None:
    expired = conn.execute(
        select(reservations).where(reservations.c.status == "pending", reservations.c.expires_at <= now)
    ).all()
    for res in expired:
        if _transition(conn, res.reservation_id, "expired"):
            _unreserve(conn, res)


def _close_pending(conn: Connection, reservation_id: str, status: str):
    release_expired(conn, utcnow())
    res = _get_row(conn, reservation_id)
    if res is None:
        raise NotFound(f"Reservation {reservation_id} not found")
    if not _transition(conn, reservation_id, status):
        raise Conflict(f"Reservation is {_get_row(conn, reservation_id).status}")
    return res


def _transition(conn: Connection, reservation_id: str, status: str) -> bool:
    # Only a pending reservation can change status, so each one closes exactly once.
    result = conn.execute(
        update(reservations)
        .where(reservations.c.reservation_id == reservation_id, reservations.c.status == "pending")
        .values(status=status)
    )
    return result.rowcount == 1


def _unreserve(conn: Connection, res) -> None:
    conn.execute(
        update(stock)
        .where(stock.c.store_id == res.store_id, stock.c.product_id == res.product_id)
        .values(reserved_quantity=stock.c.reserved_quantity - res.quantity)
    )


def _raise_reserve_failure(conn: Connection, store_id: str, product_id: str) -> None:
    store = conn.execute(select(stores).where(stores.c.store_id == store_id)).first()
    item = conn.execute(
        select(stock).where(stock.c.store_id == store_id, stock.c.product_id == product_id)
    ).first()
    if store is None or item is None:
        raise NotFound(f"Product {product_id} not found in store {store_id}")
    if not store.is_open:
        raise Conflict(f"Store {store_id} is closed")
    raise Conflict(f"Not enough stock for {product_id}")


def _get_row(conn: Connection, reservation_id: str):
    return conn.execute(select(reservations).where(reservations.c.reservation_id == reservation_id)).first()


def _get(conn: Connection, reservation_id: str) -> dict:
    return dict(_get_row(conn, reservation_id)._mapping)
