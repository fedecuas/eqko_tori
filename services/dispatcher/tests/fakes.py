from dispatcher.outputs import LeadOutput
from tori_shared_types import LeadApprovedEvent


class StubOutput(LeadOutput):
    def __init__(self, name: str = "stub", error: Exception | None = None):
        self.name = name
        self._error = error
        self.calls: list[LeadApprovedEvent] = []

    def upsert(self, event: LeadApprovedEvent) -> None:
        self.calls.append(event)
        if self._error:
            raise self._error


class FakeClock:
    """Reloj controlado a mano para no depender de time.sleep real en los tests del rate
    limiter — sleep() avanza el reloj en vez de bloquear de verdad."""

    def __init__(self, start: float = 0.0):
        self.now = start
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
