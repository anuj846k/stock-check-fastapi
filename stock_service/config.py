import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./stock.db")
RESERVATION_TTL_SECONDS = int(os.environ.get("RESERVATION_TTL_SECONDS", "600"))
