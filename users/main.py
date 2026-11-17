import json
import os
import uuid

import pika
import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# the address of the database, docker compose sets this for us
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://users:users@localhost:5432/users")

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.propagate import inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# tracing: send spans to jaeger
OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "http://localhost:4318/v1/traces")
provider = TracerProvider(resource=Resource.create({"service.name": "users"}))
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("users")
PsycopgInstrumentor().instrument()  # every SQL query becomes a span


app = FastAPI(title="Users service")

FastAPIInstrumentor.instrument_app(app)  # every request becomes a span

class UserInput(BaseModel):
    name: str
    email: str
    country: str


class User(UserInput):
    id: str


def get_connection():
    return psycopg.connect(DATABASE_URL, autocommit=True)


# make the table when the service starts
with get_connection() as conn:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users (id text PRIMARY KEY, name text, email text, country text)"
    )


def send_event(event_type, user):
    # tell everyone who listens that a user was created or updated
    try:
        with tracer.start_as_current_span("publish user event"):
            headers = {}
            inject(headers)  # puts the trace id into the headers
            connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
            channel = connection.channel()
            channel.exchange_declare(exchange="users", exchange_type="fanout")
            message = json.dumps({"type": event_type, "user": user.model_dump()})
            channel.basic_publish(
                exchange="users",
                routing_key="",
                body=message,
                properties=pika.BasicProperties(headers=headers),
            )
            connection.close()
    except Exception as error:
        print("could not send event:", error, flush=True)


@app.get("/users", response_model=list[User])
def list_users():
    # the snapshot: orders asks for this when it starts
    with get_connection() as conn:
        rows = conn.execute("SELECT id, name, email, country FROM users").fetchall()
    return [User(id=r[0], name=r[1], email=r[2], country=r[3]) for r in rows]


@app.post("/users", response_model=User, status_code=201)
def create_user(user: UserInput):
    user_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users (id, name, email, country) VALUES (%s, %s, %s, %s)",
            (user_id, user.name, user.email, user.country),
        )
    created = User(id=user_id, name=user.name, email=user.email, country=user.country)
    send_event("user.created", created)
    return created


@app.get("/users/{user_id}", response_model=User)
def get_user(user_id: str):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, email, country FROM users WHERE id = %s", (user_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return User(id=row[0], name=row[1], email=row[2], country=row[3])


@app.put("/users/{user_id}", response_model=User)
def update_user(user_id: str, user: UserInput):
    with get_connection() as conn:
        result = conn.execute(
            "UPDATE users SET name = %s, email = %s, country = %s WHERE id = %s",
            (user.name, user.email, user.country, user_id),
        )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found")
    updated = User(id=user_id, name=user.name, email=user.email, country=user.country)
    send_event("user.updated", updated)
    return updated