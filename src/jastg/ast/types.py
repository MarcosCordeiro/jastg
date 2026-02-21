"""Type name extraction from javalang AST nodes.

Traverses ReferenceType nodes recursively, handling sub-types and generic
arguments. BasicType (int, boolean, etc.) nodes are silently ignored.
"""

from __future__ import annotations

import javalang


def extrair_nomes_de_tipo(type_node) -> set[str]:
    """Extract type names (including generics) from a javalang type node.

    Recursively traverses ReferenceType, sub_types and generic arguments.
    BasicType (int, boolean, etc.) is ignored.

    Args:
        type_node: A javalang type node (ReferenceType, BasicType, str, or None).

    Returns:
        Set of raw type name strings (e.g. ``{"List", "String"}``).
    """
    nomes: set[str] = set()
    if type_node is None:
        return nomes

    if isinstance(type_node, javalang.tree.ReferenceType):
        nome = type_node.name
        sub = type_node.sub_type
        while sub is not None:
            nome = f"{nome}.{sub.name}"
            if hasattr(sub, "arguments") and sub.arguments:
                for arg in sub.arguments:
                    if hasattr(arg, "type") and arg.type is not None:
                        nomes.update(extrair_nomes_de_tipo(arg.type))
            sub = getattr(sub, "sub_type", None)
        nomes.add(nome)

        if type_node.arguments:
            for arg in type_node.arguments:
                if hasattr(arg, "type") and arg.type is not None:
                    nomes.update(extrair_nomes_de_tipo(arg.type))

    elif isinstance(type_node, javalang.tree.BasicType):
        pass  # primitives carry no structural dependency

    elif isinstance(type_node, str):
        nomes.add(type_node)

    return nomes
