"""Configuration dataclasses for a JASTG analysis run.

Use :class:`AnalysisConfig` to capture and validate all parameters before
invoking :func:`jastg.pipeline.run`.  The :meth:`AnalysisConfig.config_hash`
method returns a stable SHA-256 digest of the effective configuration, which
is embedded in ``grafo_metadata.json`` to support reproducibility checks.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class DomainSpec:
    """A single analysis domain: a name label paired with a root path.

    Args:
        name: Human-readable domain label (used as a prefix in class IDs).
        path: Root directory to scan recursively for ``.java`` files.
    """

    name: str
    path: Path

    def __post_init__(self) -> None:
        self.path = Path(self.path)


@dataclass
class AnalysisConfig:
    """Complete configuration for one JASTG analysis run.

    Args:
        domains: One or more :class:`DomainSpec` instances.
        output_dir: Directory to write output files into.  Defaults to
            ``Path("output")``.
        weighted: If ``True`` (default), write edge weights.
        directed: If ``True`` (default), produce a directed graph.
        qualifier_heuristic: ``"upper"`` (default) or ``"off"``.
        fail_fast: If ``True``, abort on the first parse error.
    """

    domains: list[DomainSpec]
    output_dir: Path = field(default_factory=lambda: Path("output"))
    weighted: bool = True
    directed: bool = True
    qualifier_heuristic: Literal["upper", "off"] = "upper"
    fail_fast: bool = False

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)

    def config_hash(self) -> str:
        """Return a SHA-256 hex digest of the effective configuration.

        Only fields that affect analysis results are included (domain names,
        paths, graph mode, and qualifier heuristic).  ``output_dir`` and
        ``fail_fast`` are excluded because they do not affect the graph
        content.

        Returns:
            64-character lowercase hex string.
        """
        d = {
            "domains": [
                {"name": ds.name, "path": str(ds.path)}
                for ds in self.domains
            ],
            "weighted": self.weighted,
            "directed": self.directed,
            "qualifier_heuristic": self.qualifier_heuristic,
        }
        payload = json.dumps(d, sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()
