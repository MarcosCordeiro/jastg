"""Main analysis pipeline.

Orchestrates the two-pass analysis:

1. **Pass 1** – collect all internal class names across all domains.
2. **Pass 2** – parse each file again to extract metrics and dependencies.

Then exports all output files via :mod:`jastg.graph.export`.

This module is the single public entry point for programmatic use::

    from jastg.pipeline import run

    metadata = run(
        dominios=["myapp"],
        caminhos=["/path/to/src"],
        ponderado=True,
        direcionado=True,
        output_dir="output",
    )
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

import javalang

from jastg.ast.collect import coletar_classes_internas
from jastg.config import AnalysisConfig, DomainSpec
from jastg.extract import extrair_dependencias_e_metricas
from jastg.graph.export import exportar_saidas

logger = logging.getLogger(__name__)


def run(
    dominios: list[str],
    caminhos: list[str | Path],
    ponderado: bool = True,
    direcionado: bool = True,
    output_dir: str | Path = "output",
    qualifier_heuristic: str = "upper",
    fail_fast: bool = False,
) -> dict:
    """Run the full JASTG two-pass analysis pipeline.

    Args:
        dominios: List of domain labels, one per entry in *caminhos*.
        caminhos: List of root paths to scan for ``.java`` files.
        ponderado: If ``True`` (default), write edge weights as the third
            column of the graph edge set.
        direcionado: If ``True`` (default), produce a directed graph.
            If ``False``, symmetrize by summing reciprocal edge weights.
        output_dir: Directory to write the output files into
            (created if absent).  Defaults to ``"output"``.
        qualifier_heuristic: ``"upper"`` (default) – only ``MethodInvocation``
            qualifiers starting with an uppercase letter are resolved
            (Java convention: classes start uppercase, variables lowercase).
            ``"off"`` – disable the filter.
        fail_fast: If ``True``, raise the first parse exception encountered
            in Pass 2 instead of logging and continuing.

    Returns:
        The metadata :class:`dict` written to ``grafo_metadata.json`` and
        embedded in ``graph.graphml``.

    Raises:
        ValueError: If *dominios* and *caminhos* have different lengths.
        Exception: Re-raised from javalang if *fail_fast* is ``True`` and a
            parse error occurs.
    """
    if len(dominios) != len(caminhos):
        raise ValueError(
            f"dominios ({len(dominios)}) and caminhos ({len(caminhos)}) must have the same length."
        )

    caminhos_path = [Path(c) for c in caminhos]

    # Build config object for reproducibility hash
    config = AnalysisConfig(
        domains=[DomainSpec(name=d, path=p) for d, p in zip(dominios, caminhos_path, strict=False)],
        output_dir=Path(output_dir),
        weighted=ponderado,
        directed=direcionado,
        qualifier_heuristic=qualifier_heuristic,
        fail_fast=fail_fast,
    )

    # ── Pass 1: collect internal classes ──────────────────────────────────────
    logger.info("Pass 1: collecting internal classes...")
    (classes_internas, index_nome_simples, _dominio_por_classe, total_arquivos) = (
        coletar_classes_internas(dominios, caminhos_path)
    )
    logger.info("Java files found: %d", total_arquivos)
    logger.info("Internal classes found: %d", len(classes_internas))

    # ── Pass 2: extract metrics and dependencies ──────────────────────────────
    logger.info("Pass 2: extracting metrics and dependencies...")
    resultados: dict = {}
    arestas_globais: Counter = Counter()
    erros = 0

    for dominio, caminho in zip(dominios, caminhos_path, strict=False):
        logger.info("Analysing domain: %s", dominio)
        # Sort for deterministic traversal order
        arquivos = sorted(Path(caminho).rglob("*.java"))
        for arquivo in arquivos:
            try:
                source = arquivo.read_text(encoding="utf-8")
                tree = javalang.parse.parse(source)
            except Exception as exc:
                logger.error("Failed to process %s: %s", arquivo, exc)
                erros += 1
                if fail_fast:
                    raise
                continue

            resultados_arquivo = extrair_dependencias_e_metricas(
                tree,
                arquivo.name,
                classes_internas,
                index_nome_simples,
                dominio,
                qualifier_heuristic=qualifier_heuristic,
            )
            for resultado in resultados_arquivo:
                chave = resultado["chave"]
                if chave not in resultados:
                    resultados[chave] = resultado["metricas"]
                for destino, peso in resultado["arestas_counter"].items():
                    origem = resultado["classe"]
                    if origem != destino:
                        arestas_globais[(origem, destino)] += peso

    # ── Export ────────────────────────────────────────────────────────────────
    domain_label = "_".join(dominios)
    domain_subdir = Path(output_dir) / domain_label
    logger.info("Generating output files...")
    _arestas_escritas, metadata = exportar_saidas(
        resultados,
        arestas_globais,
        classes_internas,
        total_arquivos,
        erros,
        domain_subdir,
        domain_label,
        ponderado=ponderado,
        direcionado=direcionado,
        config_hash=config.config_hash(),
    )

    logger.info(
        "Done. classes=%d  edges=%d  errors=%d",
        metadata["num_classes"],
        metadata["num_edges"],
        erros,
    )

    if logger.isEnabledFor(logging.DEBUG):
        top_cbo = sorted(resultados.items(), key=lambda x: x[1]["CBO"], reverse=True)[:10]
        if top_cbo:
            logger.debug("Top 10 classes by CBO:")
            for nome, metricas in top_cbo:
                logger.debug("  CBO=%3d  %s", metricas["CBO"], nome)

    return metadata
