"""JASTG – Java AST Structural Graph.

Static structural dependency analysis for Java codebases, based on AST
parsing via *javalang*.  No type solving; no classpath required.

Quick start::

    from jastg.pipeline import run

    metadata = run(
        dominios=["myapp"],
        caminhos=["/path/to/src"],
    )

Or via the CLI::

    jastg analyze --domain myapp --path /path/to/src

See :func:`jastg.pipeline.run` for the full parameter reference.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__: str = version("jastg")
except PackageNotFoundError:
    __version__ = "0.0.0"

from jastg.config import AnalysisConfig, DomainSpec
from jastg.pipeline import run

__all__ = [
    "__version__",
    "run",
    "AnalysisConfig",
    "DomainSpec",
]
