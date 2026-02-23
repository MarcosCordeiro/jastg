"""Graph export: symmetrization, ID mapping, and output file generation.

Produces two deterministic output files (both named with the domain label):

* ``metadata_{domain}.json`` – run provenance and configuration
* ``graph_{domain}.graphml`` – GraphML graph with node metrics and edge weights (Gephi-ready)

IDs are assigned by alphabetical sort of the ``domain/class`` keys, so the
mapping is deterministic for the same input regardless of traversal order.
"""

from __future__ import annotations

import json
import logging
import platform
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

logger = logging.getLogger(__name__)


def _obter_url_remoto(path: Path | None = None) -> str | None:
    """Attempt to retrieve the git remote origin URL for the repository at *path*.

    Returns ``None`` silently on any failure (not a git repo, no remote, etc.).
    """
    try:
        kwargs: dict = {"capture_output": True, "text": True, "timeout": 5}
        if path is not None:
            kwargs["cwd"] = path
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            **kwargs,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


def _obter_commit_hash() -> str | None:
    """Attempt to retrieve the current git commit hash.

    Returns ``None`` silently on any failure (not a git repo, git not
    installed, timeout, etc.).
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _pkg_version(pkg: str) -> str:
    """Return the installed version of *pkg*, or ``"unknown"``."""
    try:
        from importlib.metadata import version

        return version(pkg)
    except Exception:
        return "unknown"


def gerar_grafo_nao_direcionado(arestas_ponderadas: Counter) -> Counter:
    """Convert directed weighted edges to undirected by summing reciprocal pairs.

    Each directed edge ``(orig, dest)`` is mapped to the canonical key
    ``(min(orig, dest), max(orig, dest))`` and its weight is added to any
    existing weight for that pair.  Reciprocal pairs ``A→B`` and ``B→A``
    therefore have their weights summed; non-reciprocal edges retain their
    original weight.

    Args:
        arestas_ponderadas: :class:`~collections.Counter` mapping
            ``(orig_id, dest_id)`` to integer weight.

    Returns:
        New :class:`~collections.Counter` mapping ``(min_id, max_id)`` to
        summed weight.
    """
    grafo_nd: Counter = Counter()
    for (orig, dest), peso in arestas_ponderadas.items():
        chave = (min(orig, dest), max(orig, dest))
        grafo_nd[chave] += peso
    return grafo_nd


def exportar_saidas(
    resultados: dict,
    arestas_globais: Counter,
    classes_internas: set[str],
    total_arquivos: int,
    erros: int,
    output_dir: Path,
    domain: str,
    ponderado: bool = True,
    direcionado: bool = True,
    config_hash: str | None = None,
    source_path: Path | None = None,
) -> tuple[int, dict]:
    """Generate all output files for a completed analysis run.

    Args:
        resultados: Mapping ``domain/qualified_name → metrics_dict``.
        arestas_globais: :class:`~collections.Counter` mapping
            ``(qual_orig, qual_dest)`` to occurrence weight.
        classes_internas: Set of all known qualified class names
            (used for future extensions; currently informational).
        total_arquivos: Total ``.java`` files scanned.
        erros: Number of files that failed to parse.
        output_dir: :class:`~pathlib.Path` to write output files into.
            Created (with parents) if it does not exist.
        domain: Domain label used as a suffix in output file names.
        ponderado: If ``True``, include edge weights in the graph.
        direcionado: If ``True``, emit directed edges; if ``False``,
            symmetrize with :func:`gerar_grafo_nao_direcionado`.
        config_hash: Optional SHA-256 hex digest of the run configuration
            (for reproducibility).
        source_path: Root path of the analysed project, used to resolve
            its git remote URL.  When ``None`` the URL is not included.

    Returns:
        Tuple ``(edges_written, metadata_dict)`` where *edges_written* is
        the number of edges in the graph and *metadata_dict* is the object
        written to ``metadata_{domain}.json``.

    Output files
    ------------
    * ``metadata_{domain}.json`` – run provenance and configuration.
    * ``graph_{domain}.graphml`` – GraphML file with node labels, OO metrics as
      node attributes, and optional edge weights.  Ready for direct import
      into Gephi or any other GraphML-compatible tool.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- ID mapping: sorted for determinism ---
    nome_para_id: dict[str, int] = {
        nome: idx + 1 for idx, nome in enumerate(sorted(resultados.keys()))
    }

    # --- Map qual_name → domain/qual key ---
    qual_para_chave: dict[str, str] = {}
    for chave in resultados:
        pos = chave.index("/")
        nome_qual = chave[pos + 1 :]
        qual_para_chave[nome_qual] = chave

    # --- Convert edges to numeric IDs with weights ---
    arestas_ids: Counter = Counter()
    for (origem, destino), peso in arestas_globais.items():
        chave_orig = qual_para_chave.get(origem)
        chave_dest = qual_para_chave.get(destino)
        if chave_orig and chave_dest:
            id_orig = nome_para_id.get(chave_orig)
            id_dest = nome_para_id.get(chave_dest)
            if id_orig and id_dest and id_orig != id_dest:
                arestas_ids[(id_orig, id_dest)] += peso

    # --- Symmetrize if undirected ---
    if not direcionado:
        arestas_ids = gerar_grafo_nao_direcionado(arestas_ids)

    arestas_escritas = len(arestas_ids)

    # --- grafo_metadata.json ---
    from jastg import __version__ as jastg_version  # avoid circular at module level

    commit_hash = _obter_commit_hash()
    project_url = _obter_url_remoto(source_path)
    metadata = {
        "project_url": project_url,
        "jastg_version": jastg_version,
        "python_version": sys.version,
        "platform": platform.platform(),
        "javalang_version": _pkg_version("javalang"),
        "networkx_version": _pkg_version("networkx"),
        "config_hash": config_hash,
        "run_date": datetime.now(timezone.utc).isoformat(),
        "commit_hash": commit_hash,
        "num_classes": len(resultados),
        "num_edges": arestas_escritas,
        "total_java_files": total_arquivos,
        "parse_errors": erros,
        "directed": direcionado,
        "weighted": ponderado,
    }
    with open(output_dir / f"metadata_{domain}.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # --- graph_{domain}.graphml ---
    G: nx.DiGraph | nx.Graph = nx.DiGraph() if direcionado else nx.Graph()
    for nome, metricas in resultados.items():
        G.add_node(str(nome_para_id[nome]), label=nome, **metricas)
    for (id_a, id_b), peso in sorted(arestas_ids.items()):
        if ponderado:
            G.add_edge(str(id_a), str(id_b), weight=peso)
        else:
            G.add_edge(str(id_a), str(id_b))
    G.graph.update({k: v for k, v in metadata.items() if v is not None})
    nx.write_graphml(G, output_dir / f"graph_{domain}.graphml")

    logger.info(
        "Outputs written to %s  (classes=%d, edges=%d)",
        output_dir,
        len(resultados),
        arestas_escritas,
    )
    return arestas_escritas, metadata
