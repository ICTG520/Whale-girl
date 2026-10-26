from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentIdentity:
    """The single identity shared by every platform connector."""

    agent_id: str = "whale-girl"
    name: str = "鲸鱼娘"
