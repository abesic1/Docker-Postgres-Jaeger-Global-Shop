# Documentation

Two services for the global shop (Users and Orders), run with docker compose. Stack: Python, FastAPI, Postgres, RabbitMQ, Jaeger.

AI use: I used Claude for first drafts of the code and for explanations. I picked the stack, asked for simpler code when I couldn't follow it, ran every step on my own machine, did all the tests, and fixed my own files from the logs (requirements, compose, ports). The numbers and screenshots are from my runs.

## Steps 1 and 2: services and compose

Users has create, list, get and update. Orders has create and get. Each service has its own Postgres database and its own openapi.yaml, which I wrote first and checked against the code with check_step1.py. compose.yaml starts both services and both databases, with healthchecks so the services wait for their database. RabbitMQ and Jaeger were added later.

## Step 3: call Users with timeout and retries

Orders asked Users about the user on every order (2 s timeout, 3 tries). I stopped Users and made an order. The log shows 3 failed tries, then a 503. It took about 12.7 s. I expected much less. Each failed try seems to take around 3.7 s, probably docker's name lookup for a stopped container (my guess, the log only says ConnectError).

![Orders retrying 3 times and then answering 503](docs/step3-users-down.png)

## Step 4: local copy of the users

Users now sends "user created/updated" events to RabbitMQ. Orders keeps its own users_copy table, fills it from a snapshot (GET /users) when it starts, and then updates it from the events. It makes its queue before loading the snapshot so no event gets lost. With Users stopped, an order took about 43 ms and answered 201 (measured with Measure-Command, so only the screenshot of the log is shown).

![Orders loads the snapshot, gets an event and creates an order](docs/step4-projection.png)

The red PUT error in the screenshot is a call I sent to Users while it was still starting. It isn't part of the test.

## Steps 3 and 4 compared

| | Step 3: call Users | Step 4: local copy |
|---|---|---|
| Users is down | 503 after about 12.7 s | order works, 201 in about 43 ms |
| User data | always current | can be old for a moment |
| Orders depends on | Users | RabbitMQ (Users only for the snapshot) |
| Main risk | slow retries | stale or missing data |

I gained availability and speed and lost freshness. A gap I know about: if Users can't publish an event, Orders never hears about that user. For a shop I think the local copy is better, since an order shouldn't fail just because Users is down.

## Step 5: OpenTelemetry and Jaeger

Both services send traces to Jaeger. HTTP and SQL are traced automatically, and for RabbitMQ I pass the trace id in the message headers by hand. One trace has 8 spans across 2 services: POST /users, the INSERT, "publish user event", then Orders' "process user event" and its INSERT.

![One trace from users to orders in Jaeger](docs/step5-jaeger-trace.png)

## Step 6: production

Deployment: build images in CI and run them on Kubernetes or a managed container service with rolling updates and health checks. Use managed Postgres and RabbitMQ, keep passwords in a secrets manager, and run table creation as a migration.

Scaling: both services keep no state, so I can run several copies behind a load balancer. Several Orders copies can share the queue and the database. The database is the hard part (read replicas first). RabbitMQ would be a cluster with durable queues.

Fixes I'd make first: the outbox pattern for the event gap, a circuit breaker with growing retry delays, a dead-letter queue, and a version number on each user so an old update can't overwrite a newer one.

Monitoring: sampled traces in Jaeger with real storage, metrics in Prometheus and Grafana (errors, latency, queue length), logs with the trace id, and alerts for a growing queue or rising 5xx errors. The RabbitMQ page and the databases shouldn't be open to the internet.

## What went wrong

PowerShell doesn't accept &&. I once ran compose in the wrong folder, and I tested the old code in step 3 because I forgot to rebuild. pika was missing from requirements.txt, port 15672 was taken so I used 15673, and two lines got glued together in requirements.txt in step 5 (pikaopentelemetry-sdk). I also forgot the OTLP_ENDPOINT line for Orders at first.