import logging


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced application logger."""
    return logging.getLogger(f"whale_girl.{name}")
