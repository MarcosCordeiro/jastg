"""Type resolution rules for JASTG (rules 1–6, no type solving).

Resolution is purely syntactic: imports and package context are used to map
simple or partially-qualified names to fully-qualified internal class names.
No type inference, no classpath lookup.
"""

from __future__ import annotations

import javalang


def _construir_nome_aninhado(path_ast, decl) -> str:
    """Build the simple name of a declaration including ancestor inner classes.

    For a top-level class: returns ``decl.name``.
    For an inner class: returns ``Outer$Inner`` or ``Outer$Inner$Deep``
    (multilevel, using ``$`` as separator).

    Args:
        path_ast: The AST path tuple yielded by ``javalang.tree.filter()``.
        decl: The class or interface declaration node.

    Returns:
        Simple name string with ``$`` separators for inner-class nesting.
    """
    outer_classes = [
        n
        for n in path_ast
        if isinstance(n, (javalang.tree.ClassDeclaration, javalang.tree.InterfaceDeclaration))
    ]
    if outer_classes:
        cadeia = "$".join(n.name for n in outer_classes)
        return f"{cadeia}${decl.name}"
    return decl.name


def _extrair_imports(tree) -> tuple[set[str], set[str]]:
    """Extract explicit and wildcard imports from a CompilationUnit.

    Static imports are excluded: they refer to members (methods/constants),
    not to classes, and must not participate in type resolution.

    Args:
        tree: A parsed javalang ``CompilationUnit``.

    Returns:
        Tuple ``(explicit_imports, wildcard_prefixes)`` as sets of strings.
        Explicit entries are full paths (e.g. ``"com.example.Foo"``).
        Wildcard entries are package prefixes (e.g. ``"com.example"``).
    """
    explicitos: set[str] = set()
    wildcards: set[str] = set()
    for _, node in tree:
        if isinstance(node, javalang.tree.Import):
            if node.path and not node.static:
                if node.wildcard:
                    wildcards.add(node.path)
                else:
                    explicitos.add(node.path)
    return explicitos, wildcards


def resolver_tipo(
    nome_tipo: str,
    package: str,
    imports_explicitos: set[str],
    imports_wildcard: set[str],
    classes_internas: set[str],
    index_nome_simples: dict[str, list[str]],
) -> str | None:
    """Resolve a type name to a fully qualified internal class name.

    Applies six ordered rules (no type solving):

    1.  Already fully-qualified and present in ``classes_internas``.
    1b. Inner class via ``"."``:

        - 2 parts (``Outer.Inner``) → ``Outer$Inner``, resolve recursively
          through all remaining rules.
        - 3+ parts (``pkg.Outer.Inner``) → ``pkg.Outer$Inner``, direct lookup
          in ``classes_internas``.
        - Multilevel via ``"."`` (``pkg.A.B.C``) is **not** resolved here —
          only the two last parts are converted. This is a documented
          limitation.

    2.  Explicit non-static import ending with the simple name, if the
        resolved path is in ``classes_internas``.
    3.  Single wildcard non-static import prefix + name, if the result is
        unique in ``classes_internas``.
    4.  Current package + simple name, if the result is in
        ``classes_internas``.
    5.  Unique match by simple name in the global index.
    6.  ``None`` (discarded — ambiguous or unknown).

    Args:
        nome_tipo: Type name to resolve (simple or partially/fully qualified).
        package: Current file's declared package (empty string if default pkg).
        imports_explicitos: Set of explicit non-static import paths.
        imports_wildcard: Set of wildcard import prefixes (without ``.*``).
        classes_internas: Set of all known fully-qualified class names.
        index_nome_simples: Mapping ``simple_name → [qualified_names]``.

    Returns:
        Fully-qualified class name string if resolved, otherwise ``None``.
    """
    nome_tipo = nome_tipo.replace("[]", "").strip()
    if not nome_tipo:
        return None

    # Rule 1 – already fully qualified
    if nome_tipo in classes_internas:
        return nome_tipo

    # Rule 1b – inner class via "."
    if "." in nome_tipo:
        partes = nome_tipo.split(".")
        if len(partes) == 2:
            # e.g. "Outer.Inner" → "Outer$Inner", then re-resolve
            candidato_inner = f"{partes[0]}${partes[1]}"
            resultado = resolver_tipo(
                candidato_inner,
                package,
                imports_explicitos,
                imports_wildcard,
                classes_internas,
                index_nome_simples,
            )
            if resultado:
                return resultado
        elif len(partes) >= 3:
            # e.g. "com.example.Foo.Inner" → "com.example.Foo$Inner"
            prefixo = ".".join(partes[:-2])
            candidato_inner = f"{prefixo}.{partes[-2]}${partes[-1]}"
            if candidato_inner in classes_internas:
                return candidato_inner
        return None

    # Rule 2 – explicit import
    for imp in imports_explicitos:
        if imp.endswith(f".{nome_tipo}") and imp in classes_internas:
            return imp

    # Rule 3 – wildcard import (unique match only)
    candidatos_wildcard = []
    for prefix in imports_wildcard:
        candidato = f"{prefix}.{nome_tipo}"
        if candidato in classes_internas:
            candidatos_wildcard.append(candidato)
    if len(candidatos_wildcard) == 1:
        return candidatos_wildcard[0]

    # Rule 4 – current package
    if package:
        candidato = f"{package}.{nome_tipo}"
        if candidato in classes_internas:
            return candidato

    # Rule 5 – unique global match by simple name
    candidatos = index_nome_simples.get(nome_tipo, [])
    if len(candidatos) == 1:
        return candidatos[0]

    # Rule 6 – discard
    return None
