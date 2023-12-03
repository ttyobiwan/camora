import asyncio
import inspect
from collections import defaultdict
from typing import Any, Callable, TypeAlias, TypeVar

from camora.errors import DispatchError
from camora.interfaces import Broker, Logger, SilentLogger
from camora.models import BaseTask, MetaDict, PayloadDict, TaskDict
from camora.utils import LifeWatcher

Dependencies: TypeAlias = dict[str, dict[str, Any]]
RetryDecorator: TypeAlias = Callable[[Callable], Callable]

T = TypeVar("T", bound=type[BaseTask])


class Camora:
    """Camora app."""

    def __init__(
        self,
        broker: Broker,
        dependencies: list[Callable] | None = None,
        retry_policy: RetryDecorator | None = None,
        logger: Logger | None = None,
    ) -> None:
        """Create a new Camora app.

        Args:
            broker: Broker instance.
            dependencies: List of functions returning dependencies.
            retry_policy: Retry policy decorator.
            logger: Logger instance.
        """
        self.tasks: dict[str, type[BaseTask]] = {}
        self.broker = broker

        if dependencies is None:
            dependencies = []
        self.dependencies = self.build_dependencies_dict(dependencies)

        self.retry_policy = retry_policy

        if logger is None:
            logger = SilentLogger()
        self.logger = logger

        self.watcher = LifeWatcher(logger=logger)

    def build_dependencies_dict(self, deps: list[Callable]) -> dict[type, Callable]:
        """Build a dictionary of dependencies.

        Returns:
            Dictionary with dependency type as key and dependency function as value.
        """
        return {inspect.signature(dep).return_annotation: dep for dep in deps}

    # TODO: def register[T: type[BaseTask]](self, task_cls: T) -> T:
    def register(self, task_cls: T) -> T:
        """Register a task class.

        Apply retry policy if one is set.
        """
        self.tasks[task_cls.__name__] = task_cls  # TODO: Support custom names
        if self.retry_policy is None:
            return task_cls
        task_cls.execute = self.retry_policy(task_cls.execute)  # type: ignore
        return task_cls

    async def dispatch(
        self,
        task: BaseTask | type[BaseTask] | str,
        **kwargs,
    ) -> None:
        """Dispatch a task.

        Args:
            task: Task instance, class or name.
            kwargs: Task arguments.
        """
        match task:
            case BaseTask():
                task_name = task.__class__.__name__
                validate = False
                data = task.model_dump()
            case type() as typ:
                # TODO: Maybe this could be handled a little better
                if typ is not BaseTask:
                    raise DispatchError("Incorrect class passed as 'task'")
                task_name = task.__name__
                validate = True
                data = kwargs
            case str():
                task_name = task
                validate = True
                data = kwargs
            case _:
                raise DispatchError("Incorrect value passed as 'task'")

        if task_name not in self.tasks.keys():
            raise DispatchError(f"Task '{task_name}' is not registered")

        payload = PayloadDict(
            data=data,
            meta=MetaDict(task_name=task_name, validate=validate),
        )

        await self.broker.publish(payload)

    async def start(self) -> None:
        """Start the app."""
        await self.broker.check_health()
        # TODO: Check pending tasks
        self.logger.info("Starting to read")
        while self.watcher.alive:
            try:
                task_dicts = await self.broker.read()
                if not task_dicts:
                    continue
                self.logger.info("Received tasks", ids=[t["id"] for t in task_dicts])
                await self._process_tasks(task_dicts)
            except Exception as err:
                self.logger.error("Uncaught exception", err=err)
                await asyncio.sleep(1)

    async def _process_tasks(self, task_dicts: list[TaskDict]) -> None:
        """Process a list of tasks."""
        tasks = [self._construct_task(task_dict) for task_dict in task_dicts]
        deps = self._get_dependencies(tasks)
        await asyncio.gather(
            *(self._process_task(task, deps[task._id]) for task in tasks)
        )

    def _construct_task(self, task_dict: TaskDict) -> BaseTask:
        """Construct a task from a task dict."""
        payload = task_dict["payload"]
        task_cls = self.tasks[payload["meta"]["task_name"]]
        if payload["meta"]["validate"] is True:
            task = task_cls(**payload["data"])
        else:
            task = task_cls.model_construct(**payload["data"])
        task._id = task_dict["id"]
        return task

    def _get_dependencies(self, tasks: list[BaseTask]) -> Dependencies:
        """Get dependencies for tasks.

        Returns:
            Dictionary with task id as key and dictionary of dependencies as value.
        """
        deps: dict[type, Any] = {}
        deps_per_task: Dependencies = defaultdict(dict)
        for task in tasks:
            sig = inspect.signature(task.execute)
            for param in sig.parameters.values():
                if param.annotation in deps:
                    dep = deps[param.annotation]
                else:
                    dep = self.dependencies[param.annotation]()
                    deps[param.annotation] = dep
                deps_per_task[task._id][param.name] = dep
        return deps_per_task

    async def _process_task(self, task: BaseTask, dependencies: Dependencies) -> None:
        """Process a single task."""
        try:
            await task.execute(**dependencies)
        except Exception as err:
            self.logger.error("Giving up on task", task=task, error=err)
            await self.broker.handle_giveup(task, err)
        else:
            self.logger.info("Task executed successfully", task=task)
            await self.broker.handle_success(task)
