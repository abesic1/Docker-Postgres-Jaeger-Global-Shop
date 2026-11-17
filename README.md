# Global shop: Users and Orders services

Homework for Distributed Software Systems, done by Alan. Two small services for a global shop that run in docker compose, talk to each other, and show up in Jaeger.

## What's in the repo

- users/ and orders/ have the two FastAPI services. Each has its own Postgres database and its own openapi.yaml
- compose.yaml starts everything (both services, both databases, RabbitMQ and Jaeger)
- check_step1.py checks that the openapi files match what the code really does
- docs/ has the screenshots
- DOCUMENTATION.md is the write-up: what I did in each step, the comparison of steps 3 and 4, and what went wrong

Stack: Python, FastAPI, Postgres 16, RabbitMQ, OpenTelemetry, Jaeger.

## What the teacher asked for, and where it is

| Deliverable | Where |
|---|---|
| Code | users/, orders/, compose.yaml |
| One-page comparison of steps 3 and 4 | DOCUMENTATION.md, section "Steps 3 and 4 side by side" |
| A trace | docs/step5-jaeger-trace.png and DOCUMENTATION.md, step 5 |

The six steps of the exercise are in DOCUMENTATION.md in order.

## How to run it

You need Docker Desktop. In the project folder:

    docker compose up -d --build

Then:

- Users API docs: http://localhost:8001/docs
- Orders API docs: http://localhost:8002/docs
- Jaeger: http://localhost:16686
- RabbitMQ page: http://localhost:15673 (I used 15673 because 15672 was taken on my pc)

To make a user (PowerShell):

    Invoke-RestMethod -Method Post -Uri http://localhost:8001/users -ContentType "application/json" -Body '{"name":"Ana","email":"ana@example.com","country":"IT"}'

The passwords in compose.yaml (users:users, orders:orders) and RabbitMQ's default login are only for testing on my own computer. Don't use them for anything real.
