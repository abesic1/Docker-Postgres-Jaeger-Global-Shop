# Documentation

## AI use
I used Claude (Anthropic's AI) during the whole exercise. It wrote the first version of the code and explained things step by step. I ran everything on my own machine, pasted the errors and logs back, fixed what broke, and checked the results myself. The screenshots below are from my own runs. This documentation was written with AI help too, I checked it against what actually happened.

## What we did

**Step 1: the two services.** Users (create, get, update, list) and Orders (create, get) with FastAPI and Postgres. The OpenAPI files were written by hand first and then checked against the code with `check_step1.py`. The first code was too complicated, so I asked to make it simpler and more student-like.

**Step 2: docker compose.** One Dockerfile per service, a database for each, healthchecks so the services wait for the database.

**Step 3: timeout and retries.** Orders asked Users for every new order, with a 2 second timeout and 3 tries. When I stopped Users, Orders took about 12.7 seconds and then answered 503 (`docs/step3-users-down.png`). I expected it to be much faster. The reason is that every try waits for the failed connection too, so retries make the wait longer when the other service is really dead. A circuit breaker would fix that.

**Step 4: local copy of the users.** Users sends a "user created/updated" event to RabbitMQ. Orders keeps its own `users_copy` table, fills it from a snapshot (`GET /users`) when it starts, and then updates it from events. Now with Users stopped, creating an order took about 43 ms and worked (`docs/step4-projection.png` shows the snapshot, an event and a 201). What changed: Orders doesn't need Users anymore, but its data can be a bit old (eventual consistency).

**Step 5: OpenTelemetry + Jaeger.** Both services send traces to Jaeger. The trace id travels in the RabbitMQ message headers, so one trace goes from `POST /users` through the database, the event, and Orders saving the user (`docs/step5-jaeger-trace.png`).

## Things that went wrong
- PowerShell doesn't like `&&`, I had to use separate commands.
- Ran commands in the wrong folder ("no configuration file provided") and `GET /` gives 404 on purpose, the docs are at `/docs`.
- Docker Desktop wasn't running.
- Step 3: I tested the old code twice because I forgot to rebuild the image.
- I guessed the stopped-Users time wrong (12.7 s, not ~1.5 s). With a paused container I got a fast error instead of a timeout and I still don't fully know why.
- `pika` was missing in `requirements.txt` and my first compose file had no RabbitMQ.
- Port 15672 was already used on my PC, so RabbitMQ's page is on 15673.
- Step 5: two lines got glued together in `requirements.txt` (`pikaopentelemetry-sdk`), so the build failed.
- I forgot the `OTLP_ENDPOINT` line for Orders, so it tried `localhost` and nothing was there. Also traces show up with a few seconds delay.

## Step 6: production
**Deployment.** Not compose. Build the images in CI, push them to a registry and run them on Kubernetes or a managed container service with rolling updates and health checks. Use managed Postgres and RabbitMQ, and keep passwords in a secrets manager, not in the compose file. Table creation should be a proper migration step, not something that runs when the app starts.

**Scaling.** Both services don't keep state, so I can run many copies behind a load balancer. Several Orders copies can share the same queue and database, that works because of the upsert. The database scales last: read replicas first, then splitting data. RabbitMQ would be a cluster with durable queues.

**What I'd fix first.** If publishing the event fails, Orders never hears about that user. The outbox pattern fixes it (save the event in the same database transaction, send it later). Also: a circuit breaker and retries with backoff, a dead-letter queue for bad messages, and a version number on users so an old update can't overwrite a newer one.

**Monitoring.** Traces in Jaeger but sampled, not 100%, and with real storage because it forgets everything on restart now. Metrics (Prometheus + Grafana): request rate, errors, latency, queue length, database connections. Logs in one place with the trace id inside. Alerts when the queue keeps growing, 5xx go up, or a health check fails. Also don't expose the RabbitMQ page or the databases to the internet.