# Camora

Camora is a lightweight task scheduler for Python. It uses Pydantic to validate the tasks' payload and is built with dependency injection in mind.

The main idea behind Camora, was to have something simpler than Celery, that is easy to use, supports async code and allows for customization of all the building blocks.

## Usage

First, you need create an app instance:

```python
import redis.asyncio as redis

from camora.app import Camora
from camora.redis.broker import RedisBroker

app = Camora(
    broker=RedisBroker(
        "test_stream",
        "test_group",
        "failure_stream",
        client = redis.StrictRedis(host="localhost", port=6379),
    )
)
```

The app requires some broken like Redis, but it can take anything that satisfies the `Broker` interface.

After that, you can define your tasks:

```python
@app.register
class SendEmail(BaseTask):
    recipient: str
    content: str

    async def execute(self) -> None:
        print("sending email to", self.recipient, "with content", self.content)
```

With that in place, you can dispatch the task in multiple ways:

```python
await app.dispatch(
    SendEmail(
        recipient="kappa",
        content="keppo",
    )
)
await app.dispatch(
    SendEmail,
    recipient="kappa",
    content="keppo",
)
await app.dispatch(
    "SendEmail",
    recipient="kappa",
    content="keppo",
)
```

Meaning you can either:

1. Pass a pre-constructed task instance
2. Pass a task class and kwargs, which will be used to construct the task on the worker side
3. Pass a task name and kwargs, which will lead to the same result as the previous option

Either way, tasks will be passed to the broker, which will then be consumed by the worker.

To start the worker, you need to simply call the `start` method:

```python
if __name__ == "__main__":
    asyncio.run(app.start())
```

### Retry policy

Camora supports passing a default retry policy that will be applied to all tasks:

```python
import backoff

app = Camora(
    broker=RedisBroker(
        "test_stream",
        "test_group",
        "failure_stream",
        client = redis.StrictRedis(host="localhost", port=6379),
    ),
    retry_policy=backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=5,
        max_time=30,
    )
)
```

Each task can also define its own retry policy:

```python
@app.register
class SendEmail(BaseTask):
    recipient: str
    content: str

    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=3,
    )
    async def execute(self) -> None:
        print("sending email to", self.recipient, "with content", self.content)
```

Default support was made with `backoff` in mind, but anything that satisfies the `RetryDecorator` type will work.

### Dependencies

Tasks often call some code that is not a part of the task itself, but is required for it to work. For example, a task that sends an email will need to call some email sending library. Camora supports passing dependencies directly to task `execute` method. First, you need to define what dependencies will be used in the app:

```python
class EmailClient:
    def send_email(self, recipient: str, content: str) -> None:
        print(f"Sending email to {recipient} with content {content}")


def get_email_client() -> EmailClient:
    return EmailClient()


app = Camora(
    broker=RedisBroker(
        "test_stream",
        "test_group",
        "failure_stream",
        client = redis.StrictRedis(host="localhost", port=6379),
    )
    dependencies=[get_email_client],
)
```

Now, when defining a task, you can specify what dependencies it requires:

```python
@app.register
class SendEmail(BaseTask):
    recipient: str
    content: str

    async def execute(self, email_client: EmailClient) -> None:
        email_client.send_email(self.recipient, self.content)
```

Camora will read the types of all the `execute` dependencies, and will pass them to the task when executing it. On top of that, if multiple tasks are being processed, and they require the same dependency, Camora will only call the dependency factory once, and will pass the same instance to all tasks.

## Work in progress

- [ ] Tests
- [ ] Docs
- [ ] Badges
- [ ] Sync code support
- [ ] Periodic tasks
