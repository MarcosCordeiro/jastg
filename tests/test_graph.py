"""Tests for graph utilities (jastg.graph.export)."""

from __future__ import annotations

from collections import Counter

from jastg.graph.export import gerar_grafo_nao_direcionado


def test_undirected_graph_symmetrization():
    """Reciprocal directed edges must have their weights summed."""
    arestas_dir: Counter = Counter()
    arestas_dir[(1, 2)] = 3  # A→B weight 3
    arestas_dir[(2, 1)] = 1  # B→A weight 1
    arestas_dir[(1, 3)] = 2  # A→C weight 2 (no reciprocal)

    nd = gerar_grafo_nao_direcionado(arestas_dir)

    assert nd[(1, 2)] == 4, f"Expected 4 (3+1), got {nd[(1, 2)]}"
    assert nd[(1, 3)] == 2, f"Expected 2 (no reciprocal), got {nd[(1, 3)]}"
    # Directed key (2,1) must not appear separately in the undirected result
    assert (2, 1) not in nd, "Directed (2,1) key must not appear in undirected result"


def test_undirected_canonical_key_ordering():
    """The canonical key must always be (min, max)."""
    nd = gerar_grafo_nao_direcionado(Counter({(5, 3): 7}))
    assert (3, 5) in nd
    assert nd[(3, 5)] == 7


def test_undirected_self_loops_preserved():
    """Self-loops (same source and destination) should map to (x, x) and sum."""
    nd = gerar_grafo_nao_direcionado(Counter({(2, 2): 3}))
    assert nd[(2, 2)] == 3
