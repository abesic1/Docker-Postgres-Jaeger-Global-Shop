import json
import os
import threading
import time
import uuid

import httpx
import pika
import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.propagate import extract
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
# addresses, docker compose sets these
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://orders:orders@localhost:5432/orders")
USERS_URL = os.getenv("USERS_URL", "http://localhost:8001")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")

# tracing: send spans to jaeger
OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "http://localhost:4318/v1/traces")
provider = TracerProvider(resource=Resource.create({"service.name": "orders"}))
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("orders")
PsycopgInstrumentor().instrument()
HTTPXClientInstrumentor().instrument()  # the snapshot call becomes a span too

app = FastAPI(title="Orders service")

FastAPIInstrumentor.instrument_app(app)

class Item(BaseModel):
    sku: str
    quantity: int = Field(ge=1)


class OrderInput(BaseModel):
    userId: str
    items: list[Item] = Field(min_length=1)


class Order(OrderInput):
    id: str
    status: str


def get_connection():
    return psycopg.connect(DATABASE_URL, autocommit=True)


# make the tables when the service starts
# users_copy is our own copy of the users, we never ask the users service again
with get_connection() as conn:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS orders (id text PRIMARY KEY, user_id text, items text, status text)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users_copy (id text PRIMARY KEY, name text, email text, country text)"
    )


def save_user(user):
    # insert the user, or update it if we already have it
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO users_copy (id, name, email, country) VALUES (%s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET name = %s, email = %s, country = %s""",
            (user["id"], user["name"], user["email"], user["country"],
             user["name"], user["email"], user["country"]),
        )


def load_snapshot():
    # ask the users service for all users, one time, at the start
    response = httpx.get(f"{USERS_URL}/users", timeout=5)
    for user in response.json():
        save_user(user)
    print(f"snapshot loaded: {len(response.json())} users", flush=True)


def on_message(channel, method, properties, body):
    # called for every "user created/updated" event
    event = json.loads(body)
    # continue the trace that users started
    context = extract(properties.headers or {})
    with tracer.start_as_current_span("process user event", context=context):
        save_user(event["user"])
        channel.basic_ack(method.delivery_tag)
    print(f"event received: {event['type']}", flush=True)


def open_rabbitmq():
    return pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))


def listen_for_events():
    # 1. make our queue first, so no event is lost while we load the snapshot
    while True:
        try:
            connection = open_rabbitmq()
            channel = connection.channel()
            channel.exchange_declare(exchange="users", exchange_type="fanout")
            channel.queue_declare(queue="orders-users")
            channel.queue_bind(queue="orders-users", exchange="users")
            connection.close()
            break
        except pika.exceptions.AMQPConnectionError:
            print("rabbitmq not ready, trying again", flush=True)
            time.sleep(3)

    # 2. load the snapshot (keep trying if users is down)
    while True:
        try:
            load_snapshot()
            break
        except httpx.HTTPError:
            print("users not ready for the snapshot, trying again", flush=True)
            time.sleep(3)

    # 3. listen for new events, forever
    while True:
        try:
            connection = open_rabbitmq()
            channel = connection.channel()
            channel.basic_consume(queue="orders-users", on_message_callback=on_message)
            channel.start_consuming()
        except pika.exceptions.AMQPConnectionError:
            print("lost rabbitmq, trying again", flush=True)
            time.sleep(3)


threading.Thread(target=listen_for_events, daemon=True).start()


@app.post("/orders", response_model=Order, status_code=201)
def create_order(order: OrderInput):
    # check the user in our own copy, no call to the users service
    with get_connection() as conn:
        user = conn.execute("SELECT id FROM users_copy WHERE id = %s", (order.userId,)).fetchone()
    if user is None:
        raise HTTPException(status_code=404, detail="Unknown user")

    order_id = str(uuid.uuid4())
    items = [item.model_dump() for item in order.items]
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO orders (id, user_id, items, status) VALUES (%s, %s, %s, %s)",
            (order_id, order.userId, json.dumps(items), "created"),
        )
    return Order(id=order_id, userId=order.userId, items=order.items, status="created")


@app.get("/orders/{order_id}", response_model=Order)
def get_order(order_id: str):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, user_id, items, status FROM orders WHERE id = %s", (order_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return Order(id=row[0], userId=row[1], items=json.loads(row[2]), status=row[3])