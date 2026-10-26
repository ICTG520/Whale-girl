from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlatformAccount:
    """A single account on one platform.

    The application enforces one account per platform; this model only stores the
    account data and does not implement the uniqueness rule itself.
    """

    platform: str
    account_id: str
    display_name: str
    enabled: bool = True
