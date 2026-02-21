"""Second pass: extract dependencies and OO metrics from Java source files.

For each class/interface found in a parsed AST this module collects:

* Typed structural dependencies (edges) with occurrence counts.
* OO metrics: LCOM4, CBO, RFC, NOM, NOA.

Dependencies are counted per typed occurrence in the source, keeping
signature and body separate to avoid double-counting (a parameter type
declared in the signature is counted once there; if the same type also
appears in the body as a local variable it counts again as a separate
occurrence — this is intentional and matches the baseline semantics).
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict

import javalang

from jastg.ast.resolve import (
    _construir_nome_aninhado,
    _extrair_imports,
    resolver_tipo,
)
from jastg.ast.types import extrair_nomes_de_tipo
from jastg.metrics.metrics import calcular_lcom4

logger = logging.getLogger(__name__)


def _coletar_tipos_no_corpo(
    class_decl,
    nome_qual: str,
    package: str,
    imports_explicitos: set[str],
    imports_wildcard: set[str],
    classes_internas: set[str],
    index_nome_simples: dict[str, list[str]],
    qualifier_heuristic: str = "upper",
) -> tuple[Counter, set[str]]:
    """Collect typed dependencies and invoked method names within a class.

    Covers:

    * ``extends`` / ``implements`` clauses.
    * Field types.
    * Method parameter types and return types (signature).
    * Constructor parameter types (signature).
    * ``ClassCreator`` (``new T(...)``).
    * ``MethodInvocation`` qualifier (when heuristic allows).
    * ``LocalVariableDeclaration`` types (body).
    * ``Cast`` types (body).

    Body traversal uses ``try/except TypeError`` for robustness against
    non-iterable AST nodes that may appear in certain javalang versions.

    Args:
        class_decl: The javalang class/interface declaration node.
        nome_qual: Fully-qualified name of the class being analysed
            (used to exclude self-references).
        package: Current file's declared package.
        imports_explicitos: Explicit non-static import paths.
        imports_wildcard: Wildcard import prefixes.
        classes_internas: Set of all known qualified class names.
        index_nome_simples: Simple-name → qualified-names index.
        qualifier_heuristic: ``"upper"`` (default) filters
            ``MethodInvocation`` qualifiers that start with a lowercase
            letter (Java convention for variables).  ``"off"`` disables
            the filter.

    Returns:
        Tuple ``(dep_counter, rfc_metodos)`` where:

        * ``dep_counter`` – :class:`~collections.Counter` mapping
          qualified destination name to occurrence count.
        * ``rfc_metodos`` – :class:`set` of distinct method names invoked
          (used for RFC calculation).
    """
    dep_counter: Counter = Counter()
    rfc_metodos: set[str] = set()

    def _resolver(nome_tipo: str) -> str | None:
        return resolver_tipo(
            nome_tipo,
            package,
            imports_explicitos,
            imports_wildcard,
            classes_internas,
            index_nome_simples,
        )

    def _add_tipo(nome_tipo: str) -> None:
        resolvido = _resolver(nome_tipo)
        if resolvido and resolvido != nome_qual:
            dep_counter[resolvido] += 1

    def _add_tipos_de_type_node(type_node) -> None:
        for nome in extrair_nomes_de_tipo(type_node):
            _add_tipo(nome)

    # --- extends ---
    if class_decl.extends:
        if isinstance(class_decl.extends, list):
            for ext in class_decl.extends:
                _add_tipos_de_type_node(ext)
        else:
            _add_tipos_de_type_node(class_decl.extends)

    # --- implements (ClassDeclaration) ---
    if hasattr(class_decl, "implements") and class_decl.implements:
        for impl in class_decl.implements:
            _add_tipos_de_type_node(impl)

    # --- fields ---
    if class_decl.fields:
        for field in class_decl.fields:
            _add_tipos_de_type_node(field.type)

    def _processar_no(node) -> None:
        """Process a single AST node for type extraction and RFC."""
        if isinstance(node, javalang.tree.ClassCreator):
            if node.type:
                _add_tipos_de_type_node(node.type)
        elif isinstance(node, javalang.tree.MethodInvocation):
            rfc_metodos.add(node.member)
            if node.qualifier and isinstance(node.qualifier, str):
                qual = node.qualifier.strip()
                if qual:
                    should_resolve = qualifier_heuristic == "off" or (
                        qualifier_heuristic == "upper" and qual[0].isupper()
                    )
                    if should_resolve:
                        resolvido = _resolver(qual)
                        if resolvido and resolvido != nome_qual:
                            dep_counter[resolvido] += 1
        elif isinstance(node, javalang.tree.LocalVariableDeclaration):
            _add_tipos_de_type_node(node.type)
        elif isinstance(node, javalang.tree.Cast):
            _add_tipos_de_type_node(node.type)

    def _percorrer_corpo(statements) -> None:
        """Traverse a statement list (body) extracting types and RFC names.

        Receives ``method.body`` or ``ctor.body`` — the list of statements,
        **not** the method/constructor node itself — to avoid double-counting
        types already tallied in the signature.

        ``try/except TypeError`` guards against non-iterable AST nodes that
        may appear depending on the javalang version.
        """
        if not statements:
            return
        for stmt in statements:
            if stmt is None:
                continue
            try:
                for _, node in stmt:
                    _processar_no(node)
            except TypeError:
                continue

    # --- methods: signature (return type + params) then body ---
    for metodo in class_decl.methods or []:
        if metodo.return_type:
            _add_tipos_de_type_node(metodo.return_type)
        for param in metodo.parameters or []:
            _add_tipos_de_type_node(param.type)
        _percorrer_corpo(metodo.body)

    # --- constructors: signature (params) then body ---
    for ctor in class_decl.constructors or []:
        for param in ctor.parameters or []:
            _add_tipos_de_type_node(param.type)
        _percorrer_corpo(ctor.body)

    return dep_counter, rfc_metodos


def extrair_dependencias_e_metricas(
    tree,
    nome_arquivo: str,
    classes_internas: set[str],
    index_nome_simples: dict[str, list[str]],
    dominio: str,
    qualifier_heuristic: str = "upper",
) -> list[dict]:
    """Extract metrics and dependencies from all classes in a parsed file.

    Iterates over every class and interface declaration in the AST (including
    inner classes at all nesting levels) and produces one result record per
    declaration.

    Args:
        tree: Parsed javalang ``CompilationUnit``.
        nome_arquivo: File name string (stored in metadata only).
        classes_internas: Set of all known qualified class names.
        index_nome_simples: Simple-name → qualified-names index.
        dominio: Domain label assigned to this file's classes.
        qualifier_heuristic: ``"upper"`` or ``"off"`` — see
            :func:`_coletar_tipos_no_corpo`.

    Returns:
        List of :class:`dict` records, one per class/interface found.
        Each record contains:

        * ``"classe"`` – fully-qualified class name.
        * ``"chave"`` – ``"<domain>/<qualified>"`` key.
        * ``"arquivo"`` – *nome_arquivo* string.
        * ``"metricas"`` – dict with keys ``LCOM4``, ``CBO``, ``RFC``,
          ``NOM``, ``NOA``.
        * ``"arestas_counter"`` – :class:`~collections.Counter` mapping
          qualified destination name to occurrence weight.
    """
    package = ""
    for _, node in tree:
        if isinstance(node, javalang.tree.PackageDeclaration):
            package = node.name
            break

    imports_explicitos, imports_wildcard = _extrair_imports(tree)
    resultados: list[dict] = []

    for tipo_decl in (javalang.tree.ClassDeclaration, javalang.tree.InterfaceDeclaration):
        for path_ast, class_decl in tree.filter(tipo_decl):
            nome_simples = _construir_nome_aninhado(path_ast, class_decl)
            nome_qual = f"{package}.{nome_simples}" if package else nome_simples

            # --- Attributes and LCOM4 ---
            atributos: set[str] = set()
            metodo_para_atributos: dict[str, set[str]] = defaultdict(set)
            if class_decl.fields:
                for field in class_decl.fields:
                    for decl in field.declarators:
                        atributos.add(decl.name)

            metodos = class_decl.methods or []
            for metodo in metodos:
                for _, node in metodo:
                    if isinstance(node, javalang.tree.MemberReference):
                        if node.member in atributos:
                            metodo_para_atributos[metodo.name].add(node.member)

            lcom4_valor = calcular_lcom4(metodo_para_atributos)

            # --- Dependencies (with count) and RFC ---
            dep_counter, rfc_metodos = _coletar_tipos_no_corpo(
                class_decl,
                nome_qual,
                package,
                imports_explicitos,
                imports_wildcard,
                classes_internas,
                index_nome_simples,
                qualifier_heuristic=qualifier_heuristic,
            )

            cbo = len(dep_counter)
            nom = len(metodos)
            rfc = nom + len(rfc_metodos)
            noa = len(atributos)
            chave_com_dominio = f"{dominio}/{nome_qual}"

            resultados.append(
                {
                    "classe": nome_qual,
                    "chave": chave_com_dominio,
                    "arquivo": str(nome_arquivo),
                    "metricas": {
                        "LCOM4": lcom4_valor,
                        "CBO": cbo,
                        "RFC": rfc,
                        "NOM": nom,
                        "NOA": noa,
                    },
                    "arestas_counter": dep_counter,
                }
            )

    return resultados
