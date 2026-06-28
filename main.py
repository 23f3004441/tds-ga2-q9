import time
import uuid
import math
from fastapi import FastAPI, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

TOTAL_ORDERS = 40
RATE_LIMIT = 20
WINDOW_SECONDS = 10

idempotency_store = {}
rate_buckets = {}


@app.middleware("http")
async def rate_limiter(request: Request, call_next):
    client_id = request.headers.get("X-Client-Id")
    if client_id is None:
        return await call_next(request)

    now = time.time()
    bucket = rate_buckets.get(client_id)
    if bucket is None or now - bucket[0] >= WINDOW_SECONDS:
        rate_buckets[client_id] = [now, 1]
    else:
        bucket[1] += 1
        if bucket[1] > RATE_LIMIT:
            retry_after = max(1, math.ceil(WINDOW_SECONDS - (now - bucket[0])))
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={
                    "Retry-After": str(retry_after),
                    "Access-Control-Allow-Origin": "*",
                },
            )
    return await call_next(request)


@app.post("/orders", status_code=201)
async def create_order(request: Request, idempotency_key: str = Header(None, alias="Idempotency-Key")):
    if idempotency_key and idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    order_id = str(uuid.uuid4())
    order = {"id": order_id, "status": "created"}
    for k, v in body.items():
        if k != "id":
            order[k] = v

    if idempotency_key:
        idempotency_store[idempotency_key] = order

    return order


@app.get("/orders")
async def list_orders(limit: int = 10, cursor: str = None):
    try:
        start = int(cursor) if cursor else 1
    except ValueError:
        start = 1
    start = max(start, 1)

    end = min(start + limit - 1, TOTAL_ORDERS)
    items = [{"id": i, "item": f"Order {i}"} for i in range(start, end + 1)]
    next_cursor = str(end + 1) if end < TOTAL_ORDERS else None

    return {"items": items, "next_cursor": next_cursor}
