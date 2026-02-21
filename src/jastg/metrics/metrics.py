"""OO metrics calculations: LCOM4, CBO, RFC, NOM, NOA.

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
"""

from __future__ import annotations

import networkx as nx


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
