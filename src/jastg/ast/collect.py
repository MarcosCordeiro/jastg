"""First pass: collect all internal classes from Java source files.

Scans all ``.java`` files under the given root paths and builds:

* A set of fully-qualified class names (including inner classes).
* A simple-name index for quick lookup during type resolution.
* A mapping from qualified name to domain label.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

import javalang

from jastg.ast.resolve import _construir_nome_aninhado

logger = logging.getLogger(__name__)


def coletar_classes_internas(
    dominios: list[str],
    caminhos: list[Path],
) -> tuple[set[str], dict[str, list[str]], dict[str, str], int]:
    """Scan all ``.java`` files and build the internal class set.

    Inner classes are registered as independent nodes using the ``$``
    separator (e.g. ``com.example.Outer$Inner``). Multilevel nesting is
    supported (e.g. ``com.example.Outer$Inner$Deep``).

    Parse errors in individual files are logged as warnings and skipped;
    they do **not** abort the collection pass.

    Args:
        dominios: List of domain labels, one per entry in *caminhos*.
        caminhos: List of root :class:`~pathlib.Path` objects to scan for
            ``.java`` files recursively.

    Returns:
        A 4-tuple:

        * ``classes_internas`` – :class:`set` of fully-qualified class names.
        * ``index_nome_simples`` – :class:`dict` mapping simple name to list
          of qualified names (used for rule-5 resolution).
        * ``dominio_por_classe`` – :class:`dict` mapping qualified name to its
          domain label.
        * ``total_arquivos`` – total number of ``.java`` files found.
    """
    classes_internas: set[str] = set()
    dominio_por_classe: dict[str, str] = {}
    total_arquivos = 0

    for dominio, caminho in zip(dominios, caminhos, strict=False):
        arquivos = list(Path(caminho).rglob("*.java"))
        total_arquivos += len(arquivos)
        for arquivo in arquivos:
            try:
                source = arquivo.read_text(encoding="utf-8")
                tree = javalang.parse.parse(source)
            except Exception as exc:
                logger.warning("Pass 1 – skipping %s: %s", arquivo, exc)
                continue

            package = ""
            for _, node in tree:
                if isinstance(node, javalang.tree.PackageDeclaration):
                    package = node.name
                    break

            for tipo_decl in (javalang.tree.ClassDeclaration,
                              javalang.tree.InterfaceDeclaration):
                for path_ast, decl in tree.filter(tipo_decl):
                    nome_simples = _construir_nome_aninhado(path_ast, decl)
                    nome_qual = (f"{package}.{nome_simples}"
                                 if package else nome_simples)
                    classes_internas.add(nome_qual)
                    dominio_por_classe[nome_qual] = dominio

    # Build simple-name → qualified-names index
    index_nome_simples: dict[str, list[str]] = defaultdict(list)
    for qual in classes_internas:
        partes = qual.rsplit(".", 1)
        nome_s = partes[-1] if len(partes) > 1 else qual
        index_nome_simples[nome_s].append(qual)
        # Also register each segment after "$" for inner-class simple-name match
        if "$" in nome_s:
            for segmento in nome_s.split("$")[1:]:
                index_nome_simples[segmento].append(qual)

    return (
        classes_internas,
        dict(index_nome_simples),
        dominio_por_classe,
        total_arquivos,
    )
