from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PersonaVersion:
    """A versioned persona; only one version should be active at a time."""

    version: int
    name: str
    system_prompt: str
    active: bool = False
