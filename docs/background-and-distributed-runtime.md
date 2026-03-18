# Background and Distributed Runtime

This guide covers Phase 3 runtime components:

- jobs/worker runtime
- event bus (local and distributed)
- RPC transport
- scheduler
- workflow orchestration
- reliability primitives (retry/idempotency)

## Reliability Building Blocks

Use these across runtimes:

```python
from pyferox.reliability import RetryPolicy, InMemoryIdempotencyStore

policy = RetryPolicy(
    max_attempts=3,
    base_delay_seconds=0.25,
    backoff_multiplier=2.0,
    max_delay_seconds=10.0,
    jitter_seconds=0.0,
)
store = InMemoryIdempotencyStore()
```

## Jobs and Workers

Define a job contract and handler:

```python
from pyferox.core import handle
from pyferox.jobs import StructJob


class SendEmail(StructJob):
    address: str


@handle(SendEmail)
async def send_email(job: SendEmail) -> None:
    ...
```

Create dispatcher and worker:

```python
from pyferox.core import App, Module
from pyferox.jobs import JobDispatcher, LocalJobWorker

app = App(modules=[Module(handlers=[send_email])])
dispatcher = JobDispatcher(app)
worker = LocalJobWorker(dispatcher)
```

Enqueue and process:

```python
await dispatcher.enqueue(
    SendEmail(address="a@example.com"),
    delay_seconds=0.0,
    max_retries=3,
    backoff_seconds=1.0,
    idempotency_key="send-email:a@example.com",
)
await worker.run_until_idle()
```

Lifecycle-friendly wrapper:

```python
from pyferox.jobs import create_worker_runtime

worker_runtime = create_worker_runtime(app)
await worker_runtime.startup()
await worker_runtime.run_forever(poll_interval=0.25)
```

## Events

### Local event bus

```python
from pyferox.events import LocalEventBus

bus = LocalEventBus(app)
await bus.publish(UserCreated(user_id=1))
```

### Distributed event bus

```python
from pyferox.events import DistributedEventBus, InMemoryEventBroker

broker = InMemoryEventBroker()
bus = DistributedEventBus(app, broker=broker, retry_policy=policy)
await bus.bind("user.created", UserCreated)
await bus.publish(UserCreated(user_id=1), topic="user.created")
await bus.run_once(timeout=0.5)
```

`EventEnvelope` supports retries with exponential backoff and republish.

## RPC

For a dedicated transport/adapter guide, see [RPC Adapter](rpc-adapter.md).

Server side:

```python
from pyferox.rpc import RPCServer, InMemoryRPCTransport

server = RPCServer(app, idempotency_store=store)
server.register("users.get", GetUser)

transport = InMemoryRPCTransport(default_timeout_seconds=5.0)
transport.register_service("users", server)
```

Client side:

```python
from pyferox.rpc import RPCClient

client = RPCClient(transport=transport, service="users", retry_policy=policy)
result = await client.call("users.get", {"user_id": 42}, timeout_seconds=1.0)
```

`RPCClient.call(...)` raises `RPCError` on non-OK responses.

## Scheduler

```python
from pyferox.scheduler import SchedulerRuntime

scheduler = SchedulerRuntime(retry_policy=policy)
scheduler.schedule_delayed("cleanup_once", delay_seconds=10.0, fn=cleanup_job, max_retries=1)
scheduler.schedule_interval("reconcile", interval_seconds=60.0, fn=reconcile_job, max_retries=2)
```

Run:

```python
await scheduler.run_once(timeout=0.1)
await scheduler.run_forever(poll_interval=0.25)
```

Stop loop:

```python
scheduler.stop()
```

## Workflows

Workflows orchestrate multi-step processes with optional compensation.

```python
from pyferox.workflow import Workflow, WorkflowStep

workflow = Workflow[dict[str, int]](
    "signup",
    steps=[
        WorkflowStep(name="reserve", run=reserve_account, compensate=release_account, retry_policy=policy),
        WorkflowStep(name="persist", run=persist_account, compensate=delete_account),
        WorkflowStep(name="notify", run=send_welcome_email),
    ],
)

result = await workflow.run({"user_id": 1})
```

Result includes:

- status (`success`, `failed`, `compensated`)
- completed step names
- compensated step names
- failed step and error (if any)

## CLI Runtime Entry Points

When you expose runtime objects/factories in modules, CLI can invoke them:

```bash
pyferox jobs-run --target app.jobs:worker --idle-rounds 2
pyferox worker-run --target app.jobs:worker --idle-timeout 0.25 --max-iterations 100
pyferox scheduler-run --target app.scheduler:runtime --ticks 5
```

`--target` format is always `<module_path>:<object_or_callable_name>`.
