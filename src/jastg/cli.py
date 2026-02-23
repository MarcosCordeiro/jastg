"""CLI entrypoint for JASTG.

Subcommands
-----------
``jastg analyze``
    Run the analysis pipeline on one or more domain directories.
    Accepts ``--domain``/``--path`` pairs or a ``--config`` YAML file.

``jastg doctor``
    Print version information and check that all dependencies are available.

``jastg --version``
    Print the package version and exit.

Examples
--------
Single domain::

    jastg analyze --domain myapp --path /src/myapp

Multiple domains::

    jastg analyze \\
        --domain backend --path /src/backend \\
        --domain frontend --path /src/frontend

Undirected, unweighted::

    jastg analyze --domain myapp --path /src --undirected --unweighted

From YAML config::

    jastg analyze --config analysis.yaml
"""

from __future__ import annotations

import argparse
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jastg",
        description=(
            "JASTG – Java AST Structural Graph: static dependency analysis for Java codebases."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_get_version()}",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ── analyze ──────────────────────────────────────────────────────────────
    analyze = sub.add_parser(
        "analyze",
        help="Analyse one or more Java domain directories.",
        description="Run the two-pass static analysis and produce output files.",
    )
    analyze.add_argument(
        "--domain",
        metavar="NAME",
        action="append",
        dest="domains",
        default=[],
        help="Domain label (repeat for multiple domains).",
    )
    analyze.add_argument(
        "--path",
        metavar="PATH",
        action="append",
        dest="paths",
        default=[],
        help="Root path to scan for .java files (paired with --domain).",
    )
    analyze.add_argument(
        "--config",
        metavar="FILE",
        help="YAML configuration file (alternative to --domain/--path pairs).",
    )
    analyze.add_argument(
        "--weighted",
        dest="weighted",
        action="store_true",
        default=True,
        help="Export edge weights as a third column (default: on).",
    )
    analyze.add_argument(
        "--unweighted",
        dest="weighted",
        action="store_false",
        help="Omit edge weights (two-column output).",
    )
    analyze.add_argument(
        "--directed",
        dest="directed",
        action="store_true",
        default=True,
        help="Directed graph (default: on).",
    )
    analyze.add_argument(
        "--undirected",
        dest="directed",
        action="store_false",
        help="Symmetrize edges for undirected algorithms (e.g. Louvain).",
    )
    analyze.add_argument(
        "--out",
        metavar="DIR",
        default="output",
        help="Output directory (default: output).",
    )
    analyze.add_argument(
        "--qualifier-heuristic",
        choices=["upper", "off"],
        default="upper",
        dest="qualifier_heuristic",
        help=(
            '"upper" (default) resolves only MethodInvocation qualifiers '
            "starting with an uppercase letter (Java class-name convention). "
            '"off" disables the filter.'
        ),
    )
    analyze.add_argument(
        "--fail-fast",
        action="store_true",
        default=False,
        dest="fail_fast",
        help="Abort immediately on the first parse error.",
    )
    analyze.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable DEBUG-level logging.",
    )

    # ── doctor ───────────────────────────────────────────────────────────────
    sub.add_parser(
        "doctor",
        help="Check dependencies and print version information.",
    )

    return parser


def _get_version() -> str:
    from jastg import __version__

    return __version__


def _cmd_analyze(args: argparse.Namespace) -> int:
    from jastg.logging_config import setup_logging

    setup_logging(verbose=args.verbose)

    from jastg.pipeline import run

    # --- Build domain/path lists ---
    if args.config:
        try:
            import yaml  # type: ignore[import]
        except ImportError:
            print(
                "ERROR: PyYAML is required for --config. Install with: pip install pyyaml",
                file=sys.stderr,
            )
            return 1

        with open(args.config, encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)

        domains: list[str] = [d["name"] for d in cfg["domains"]]
        paths: list[str] = [d["path"] for d in cfg["domains"]]
        weighted: bool = bool(cfg.get("weighted", True))
        directed: bool = bool(cfg.get("directed", True))
        qualifier_heuristic: str = cfg.get("qualifier_heuristic", "upper")
        fail_fast: bool = bool(cfg.get("fail_fast", False))
        output_dir: str = cfg.get("output_dir", "output")
    else:
        if not args.domains or not args.paths:
            print(
                "ERROR: Provide at least one --domain NAME --path PATH pair, or use --config FILE.",
                file=sys.stderr,
            )
            return 1
        if len(args.domains) != len(args.paths):
            print(
                f"ERROR: {len(args.domains)} --domain(s) paired with "
                f"{len(args.paths)} --path(s). They must match.",
                file=sys.stderr,
            )
            return 1
        domains = args.domains
        paths = args.paths
        weighted = args.weighted
        directed = args.directed
        qualifier_heuristic = args.qualifier_heuristic
        fail_fast = args.fail_fast
        output_dir = args.out

    try:
        metadata = run(
            dominios=domains,
            caminhos=paths,
            ponderado=weighted,
            direcionado=directed,
            output_dir=output_dir,
            qualifier_heuristic=qualifier_heuristic,
            fail_fast=fail_fast,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"\n{'=' * 60}")
    print(f"JASTG {_get_version()}")
    print(f"  Java files:      {metadata['total_java_files']}")
    print(f"  Parse errors:    {metadata['parse_errors']}")
    print(f"  Classes:         {metadata['num_classes']}")
    print(f"  Edges:           {metadata['num_edges']}")
    print(f"  Directed:        {metadata['directed']}")
    print(f"  Weighted:        {metadata['weighted']}")
    print(f"  Run date:        {metadata['run_date']}")
    if metadata.get("commit_hash"):
        print(f"  Commit:          {metadata['commit_hash'][:12]}")
    if metadata.get("project_url"):
        print(f"  Project URL:     {metadata['project_url']}")
    print(f"{'=' * 60}")
    print(f"\nOutputs written to: {output_dir}/")
    return 0


def _cmd_doctor() -> int:
    import platform

    from jastg import __version__

    print(f"jastg        {__version__}")
    print(f"Python       {sys.version}")
    print(f"Platform     {platform.platform()}")

    def _check(pkg: str) -> None:
        try:
            from importlib.metadata import version

            print(f"{pkg:<12} {version(pkg)}")
        except Exception as exc:
            print(f"{pkg:<12} ERROR – {exc}")

    _check("javalang")
    _check("networkx")
    return 0


def main() -> None:
    """CLI entry point registered as ``jastg`` in ``pyproject.toml``."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "analyze":
        sys.exit(_cmd_analyze(args))
    elif args.command == "doctor":
        sys.exit(_cmd_doctor())
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
