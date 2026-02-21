"""Logging configuration helper for JASTG.

Sets up a :class:`logging.StreamHandler` on ``sys.stderr`` for the
``"jastg"`` logger hierarchy.  Call :func:`setup_logging` once at
process startup (typically from the CLI entrypoint).
"""

from __future__ import annotations

import logging
import sys


def setup_logging(verbose: bool = False, quiet: bool = False) -> None:
    """Configure the ``jastg`` logger.

    Args:
        verbose: If ``True``, set level to ``DEBUG``.
        quiet: If ``True``, set level to ``WARNING`` (overridden by *verbose*).

    When neither flag is set the level is ``INFO``.
    """
    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING
    else:
        level = logging.INFO

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    root = logging.getLogger("jastg")
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False
