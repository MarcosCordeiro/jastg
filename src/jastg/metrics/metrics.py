"""OO metrics calculations: LCOM4, CBO, RFC, NOM, NOA, WMC.

All functions are pure (no I/O). They operate on pre-extracted data
structures produced by the extraction pass.

Metric definitions used by JASTG
---------------------------------
* **LCOM4** – Lack of Cohesion of Methods (version 4).  Number of connected
  components in the undirected graph where methods are nodes and two methods
  are connected if they share at least one attribute reference.  Minimum
  value is 1.
* **CBO** – Coupling Between Objects.  Number of distinct *internal* classes
  this class depends on (auto-references excluded).
* **RFC** – Response For a Class.  ``NOM + |distinct invoked method names|``.
  Without type solving the class target of each invocation is unknown;
  RFC is therefore an approximation.
* **NOM** – Number of Methods.
* **NOA** – Number of Attributes (field declarators).
* **WMC** – Weighted Methods per Class (Chidamber & Kemerer, 1994), with
  McCabe's cyclomatic complexity as the method weight: the sum, over the
  methods counted by NOM, of ``1 + number of decision points`` in each
  method body.  Decision points are ``if``, ``for``/``for-each``, ``while``,
  ``do``, each non-default ``case`` label, ``catch`` clauses, the ternary
  operator and the short-circuit operators ``&&`` and ``||``.  A method
  without body (abstract or interface method) has complexity 1, so
  ``WMC >= NOM`` always holds.  Constructors are excluded, for consistency
  with NOM.
"""

from __future__ import annotations

import javalang.tree
import networkx as nx

# AST node types that add one to McCabe's cyclomatic complexity.
_NOS_DE_DECISAO = (
    javalang.tree.IfStatement,
    javalang.tree.ForStatement,  # also covers enhanced for
    javalang.tree.WhileStatement,
    javalang.tree.DoStatement,
    javalang.tree.CatchClause,
    javalang.tree.TernaryExpression,
)
_OPERADORES_CURTO_CIRCUITO = frozenset({"&&", "||"})


def calcular_complexidade_ciclomatica(metodo) -> int:
    """McCabe's cyclomatic complexity of a single method declaration.

    Counts ``1 + decision points`` over the whole subtree of *metodo*
    (including bodies of lambdas and anonymous classes declared inside it).
    ``switch`` statements contribute one per non-default ``case`` label;
    ``default`` does not count.

    Args:
        metodo: A javalang ``MethodDeclaration`` (or ``ConstructorDeclaration``).

    Returns:
        Complexity ``>= 1``.  Methods without a body return 1.
    """
    if metodo.body is None:
        return 1
    complexidade = 1
    for _, node in metodo:
        if isinstance(node, _NOS_DE_DECISAO):
            complexidade += 1
        elif isinstance(node, javalang.tree.SwitchStatementCase):
            if node.case:  # ``default`` has an empty ``case`` list
                complexidade += 1
        elif isinstance(node, javalang.tree.BinaryOperation):
            if node.operator in _OPERADORES_CURTO_CIRCUITO:
                complexidade += 1
    return complexidade


def calcular_wmc(metodos) -> int:
    """Weighted Methods per Class: sum of cyclomatic complexities.

    Args:
        metodos: Iterable of javalang ``MethodDeclaration`` nodes (the same
            collection NOM counts).

    Returns:
        ``sum(cc(m) for m in metodos)``; 0 for a class without methods.
    """
    return sum(calcular_complexidade_ciclomatica(m) for m in metodos)


def calcular_lcom4(metodo_para_atributos: dict[str, set[str]]) -> int:
    """Calculate LCOM4 via connected components in the method-attribute graph.

    Each method is a node.  Two methods are connected by an edge if they
    reference at least one common attribute.  LCOM4 is the number of
    connected components (minimum 1, even for classes with no methods).

    Args:
        metodo_para_atributos: Mapping ``method_name → set[attribute_name]``
            for each method that references at least one attribute.

    Returns:
        Number of connected components (≥ 1).
    """
    G: nx.Graph = nx.Graph()
    metodos = list(metodo_para_atributos.keys())
    for i, m1 in enumerate(metodos):
        G.add_node(m1)
        for j in range(i + 1, len(metodos)):
            m2 = metodos[j]
            if metodo_para_atributos[m1] & metodo_para_atributos[m2]:
                G.add_edge(m1, m2)

    if len(G.nodes) == 0:
        return 1
    return max(nx.number_connected_components(G), 1)
