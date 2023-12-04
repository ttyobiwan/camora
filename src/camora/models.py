from typing import TypedDict

from pydantic import BaseModel


class MetaDict(TypedDict):
    """Task metadata."""

    task_name: str
    validate: bool


class PayloadDict(TypedDict):
    """Task payload.

    Represents task structure inside a broker.
    """

    data: dict
    meta: MetaDict


class TaskDict(TypedDict):
    """Task data.

    Represents task object after reading from broker.
    """

    id: str
    payload: PayloadDict


class BaseTask(BaseModel):
    """Base task model.

    Holds the data expected by the task and the logic to execute it.

    Attributes:
        _id: Task ID, set after reading from broker.
    """

    # Defaults are set to close mypy mouth
    # I'm not super happy about this design tbh
    _id: str = ""

    async def execute(self, *args, **kwargs) -> None:
        """Task execution logic.

        Arguments can be any dependencies defined in the app.
        """
        raise NotImplementedError("Task class needs to implement 'execute' method")
