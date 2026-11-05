from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy import Engine

from . import config, stock
from .db import make_engine, metadata


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Product(CamelModel):
    product_id: str
    name: str
    type: str
    available_quantity: int


class ProductList(CamelModel):
    store_id: str
    products: list[Product]
    total_count: int


class ReservationRequest(CamelModel):
    store_id: str
    product_id: str
    quantity: int = Field(gt=0)


class Reservation(CamelModel):
    reservation_id: str
    store_id: str
    product_id: str
    quantity: int
    status: Literal["pending", "confirmed", "released", "expired"]


def create_app(engine: Engine | None = None, ttl_seconds: int = config.RESERVATION_TTL_SECONDS) -> FastAPI:
    engine = engine or make_engine(config.DATABASE_URL)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        metadata.create_all(engine)
        yield

    app = FastAPI(title="Stock Service", lifespan=lifespan)

    def call(fn, *args):
        try:
            return fn(engine, *args)
        except stock.NotFound as e:
            raise HTTPException(404, str(e))
        except stock.Conflict as e:
            raise HTTPException(409, str(e))

    @app.get("/stores/{store_id}/products", response_model=ProductList)
    def get_products(store_id: str):
        products = call(stock.list_available, store_id)
        return ProductList(store_id=store_id, products=products, total_count=len(products))

    @app.post("/reservations", response_model=Reservation, status_code=201)
    def create_reservation(body: ReservationRequest):
        return call(stock.reserve, body.store_id, body.product_id, body.quantity, ttl_seconds)

    @app.post("/reservations/{reservation_id}/confirm", response_model=Reservation)
    def confirm_reservation(reservation_id: str):
        return call(stock.confirm, reservation_id)

    @app.post("/reservations/{reservation_id}/release", response_model=Reservation)
    def release_reservation(reservation_id: str):
        return call(stock.release, reservation_id)

    return app


app = create_app()
