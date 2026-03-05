"""
Centralized logger factory for Agent Paperpal tools.

All tools obtain their logger via get_logger(__name__) instead of
configuring logging independently. This ensures a consistent format
across all tool output without duplicating handlers.
"""
import logging


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger for the given module name.

    Attaches a StreamHandler with the project-standard format only if the
    logger has no handlers yet, preventing duplicate log lines when modules
    are imported multiple times or when root-level basicConfig is already set.

    Args:
        name: Typically __name__ of the calling module.

    Returns:
        Configured logging.Logger instance.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False  # prevent double-logging if root is also configured

    return logger
