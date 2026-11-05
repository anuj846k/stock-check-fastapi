def ids(response):
    return {p["productId"] for p in response.json()["products"]}


def test_sold_out_product_is_excluded(client):
    # 10482 oat milk: 0 on hand on 7 March 2025.
    response = client.get("/stores/10482/products")
    assert response.status_code == 200
    assert "oat_milk" not in ids(response)
    assert response.json()["totalCount"] == 9


def test_available_quantity_subtracts_reservations(client):
    # 11307 oat milk: 2 on hand, 1 reserved -> 1 available.
    products = client.get("/stores/11307/products").json()["products"]
    oat = next(p for p in products if p["productId"] == "oat_milk")
    assert oat["availableQuantity"] == 1


def test_response_shape_is_camel_case(client):
    body = client.get("/stores/10482/products").json()
    assert set(body) == {"storeId", "products", "totalCount"}
    assert body["storeId"] == "10482"
    assert set(body["products"][0]) == {"productId", "name", "type", "availableQuantity"}


def test_closed_store_returns_no_products(client):
    # 09815 has stock but store_open=false. The leading zero must be kept.
    body = client.get("/stores/09815/products").json()
    assert body == {"storeId": "09815", "products": [], "totalCount": 0}


def test_unknown_store_is_404(client):
    assert client.get("/stores/9815/products").status_code == 404
