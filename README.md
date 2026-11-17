# Global Shop: Users + Orders services

Class exercise: two small services for a "global shop", containerised, talking to each other, and traced with OpenTelemetry.

**What's in it**
- `users/` and `orders/`: two FastAPI services, each with its own Postgres database and its own `openapi.yaml`
- `compose.yaml`: runs everything (2 services, 2 databases, RabbitMQ, Jaeger)
- `check_step1.py`: small script that checks the OpenAPI files match the code
- `docs/`: screenshots used as proof
- `DOCUMENTATION.md`: what I did step by step, the mistakes, and the step 6 discussion

**Stack:** Python, FastAPI, Postgres 16, RabbitMQ, OpenTelemetry, Jaeger

**The exercise**
1. Users and Orders REST services described with OpenAPI
2. Containerise both and run them with a database using docker compose
3. Orders calls Users with a timeout and retries, then stop Users and see what happens
4. Replace the call with a local copy of the users in Orders, fed by "user created/updated" events (starting from a snapshot)
5. Add OpenTelemetry and look at a trace in Jaeger
6. Discuss deployment, scaling and monitoring in production

**Run it** (needs Docker Desktop)

    docker compose up -d --build

| What | Where |
|---|---|
| Users API docs | http://localhost:8001/docs |
| Orders API docs | http://localhost:8002/docs |
| Jaeger UI | http://localhost:16686 |
| RabbitMQ UI | http://localhost:15673 |

Create a user (PowerShell):

    Invoke-RestMethod -Method Post -Uri http://localhost:8001/users -ContentType "application/json" -Body '{"name":"Ana","email":"ana@example.com","country":"IT"}'

**Note:** the passwords in `compose.yaml` (`users:users`, `orders:orders`) and RabbitMQ's default login are for local testing only. Don't use them anywhere real.

Full write-up: [DOCUMENTATION.md](DOCUMENTATION.md)