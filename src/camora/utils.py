import signal

from camora.interfaces import Logger


class LifeWatcher:
    """Life watcher for the app."""

    def __init__(self, logger: Logger) -> None:
        self.alive = True
        self.logger = logger
        signal.signal(signal.SIGINT, self.terminate)
        signal.signal(signal.SIGTERM, self.terminate)

    def terminate(self, *args):
        """Terminate the app."""
        self.logger.info("Terminating the app...")
        self.alive = False
