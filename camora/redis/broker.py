import json

import redis.asyncio as redis

from camora.models import BaseTask, PayloadDict, TaskDict

SAFE_TYPES = (bytes, str, int, float)


def encode(payload: dict) -> dict:
    """Encode payload values to JSON if needed."""
    for k, v in payload.items():
        if type(v) not in SAFE_TYPES:
            payload[k] = json.dumps(v)
    return payload


def decode(payload: dict) -> dict:
    """Decode payload values from JSON if needed."""
    for k, v in payload.items():
        try:
            payload[k] = json.loads(v)
        except json.JSONDecodeError:
            pass
    return payload


class RedisBroker:
    """Redis broker implementation."""

    def __init__(
        self,
        stream: str,
        consumer_group: str,
        failure_stream: str,
        client: redis.Redis | None = None,
        client_settings: dict | None = None,
        consumer_name: str = "camora",
        block_time: int = 30,
    ) -> None:
        """Create a new Redis broker.

        Args:
            stream: Stream name.
            consumer_group: Consumer group name.
            failure_stream: Failure stream name.
            client: Redis client instance.
            client_settings: Redis client settings.
            consumer_name: Consumer name.
            block_time: Block time in seconds.
        """
        self.stream = stream
        self.consumer_group = consumer_group
        self.failure_stream = failure_stream

        if client is None:
            # This will fail if client settings are not provided
            # but user should be aware that client should either be
            # passed or configured
            client = redis.StrictRedis(**client_settings or {})
        self.redis = client

        self.consumer_name = consumer_name
        self.block_time = block_time * 1000  # To miliseconds

    async def check_health(self) -> None:
        """Check broker health."""
        await self.redis.ping()
        await self._create_consumer_group(self.stream, self.consumer_group)

    async def read(self) -> list[TaskDict]:
        """Read tasks from broker."""
        response = await self.redis.xreadgroup(
            self.consumer_group,
            self.consumer_name,
            {self.stream: ">"},
            block=self.block_time,
        )
        if not response:
            return []
        return [
            TaskDict(id=tid, payload=PayloadDict(**decode(payload)))  # type: ignore
            for tid, payload in response[0][1]
        ]

    async def publish(self, payload: PayloadDict) -> None:
        """Publish task to broker."""
        await self.redis.xadd(self.stream, encode(dict(payload)))

    async def handle_success(self, task: BaseTask) -> None:
        """Handle successful task execution."""
        await self.redis.xack(self.stream, self.consumer_group, task._id)

    async def handle_giveup(self, task: BaseTask, error: Exception) -> None:
        """Handle task execution failure, after using all retries."""
        await self.redis.xadd(self.failure_stream, encode(dict(task)))
        await self.redis.xack(self.stream, self.consumer_group, task._id)

    async def _create_consumer_group(self, stream: str, consumer_group: str) -> None:
        """Create consumer group if it doesn't exist."""
        try:
            await self.redis.xgroup_create(stream, consumer_group)
        except redis.ResponseError:
            pass
