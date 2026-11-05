from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from stock_service import stock as stock_logic
from tests.conftest import TTL_SECONDS, available, stock_row


def reserve(client, store_id="10482", product_id="almond_milk", quantity=1):
    return client.post("/reservations", json={"storeId": store_id, "productId": product_id, "quantity": quantity})


def test_reserve_holds_stock(client):
    response = reserve(client, quantity=5)
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"reservationId", "storeId", "productId", "quantity", "status"}
    assert body["status"] == "pending"
    assert available(client, "10482", "almond_milk") == 32


@pytest.mark.parametrize(
    "store_id, product_id, quantity, status",
    [
        ("10482", "oat_milk", 1, 409),  # sold out
        ("11307", "oat_milk", 2, 409),  # 2 on hand but 1 already reserved
        ("09815", "oat_milk", 1, 409),  # store closed
        ("10482", "unknown", 1, 404),
        ("10482", "almond_milk", 0, 422),
    ],
)
def test_reserve_rejected(client, store_id, product_id, quantity, status):
    assert reserve(client, store_id, product_id, quantity).status_code == status


def test_concurrent_reservations_never_oversell(engine):
    # 10482 almond milk: 37 available. 60 customers try at the same time.
    def attempt(_):
        try:
            stock_logic.reserve(engine, "10482", "almond_milk", 1, TTL_SECONDS)
            return True
        except stock_logic.Conflict:
            return False

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(attempt, range(60)))

    assert sum(results) == 37
    row = stock_row(engine, "10482", "almond_milk")
    assert row.quantity_on_hand - row.reserved_quantity == 0


def test_confirm_deducts_stock_and_releases_reservation(client, engine):
    reservation_id = reserve(client, quantity=3).json()["reservationId"]
    response = client.post(f"/reservations/{reservation_id}/confirm")
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    row = stock_row(engine, "10482", "almond_milk")
    assert (row.quantity_on_hand, row.reserved_quantity) == (35, 1)


def test_release_makes_stock_available_again(client, engine):
    reservation_id = reserve(client, quantity=3).json()["reservationId"]
    response = client.post(f"/reservations/{reservation_id}/release")
    assert response.json()["status"] == "released"
    row = stock_row(engine, "10482", "almond_milk")
    assert (row.quantity_on_hand, row.reserved_quantity) == (38, 1)


def test_last_unit_released_returns_to_product_list(client):
    reservation_id = reserve(client, "11307", "oat_milk").json()["reservationId"]
    assert available(client, "11307", "oat_milk") == 0
    client.post(f"/reservations/{reservation_id}/release")
    assert available(client, "11307", "oat_milk") == 1


@pytest.mark.parametrize("first, second", [("confirm", "confirm"), ("confirm", "release"), ("release", "confirm")])
def test_reservation_closes_only_once(client, engine, first, second):
    reservation_id = reserve(client).json()["reservationId"]
    client.post(f"/reservations/{reservation_id}/{first}")
    response = client.post(f"/reservations/{reservation_id}/{second}")
    assert response.status_code == 409
    row = stock_row(engine, "10482", "almond_milk")
    assert row.reserved_quantity == 1


def test_unknown_reservation_is_404(client):
    assert client.post("/reservations/missing/confirm").status_code == 404


def test_expired_reservation_is_released(client, engine, monkeypatch):
    reservation_id = reserve(client, quantity=5).json()["reservationId"]
    later = stock_logic.utcnow() + timedelta(seconds=TTL_SECONDS + 1)
    monkeypatch.setattr(stock_logic, "utcnow", lambda: later)

    assert available(client, "10482", "almond_milk") == 37
    response = client.post(f"/reservations/{reservation_id}/confirm")
    assert response.status_code == 409
    assert response.json()["detail"] == "Reservation is expired"
    assert stock_row(engine, "10482", "almond_milk").reserved_quantity == 1
