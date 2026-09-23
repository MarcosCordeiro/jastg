"""Tests for OO metrics calculations (jastg.metrics.metrics)."""

from __future__ import annotations

import javalang

from jastg.metrics.metrics import (
    calcular_complexidade_ciclomatica,
    calcular_lcom4,
    calcular_wmc,
)


def test_lcom4_no_methods():
    """A class with no methods must return LCOM4=1."""
    assert calcular_lcom4({}) == 1


def test_lcom4_single_method_no_attrs():
    """A single method that references no attributes must return LCOM4=1."""
    assert calcular_lcom4({"m1": set()}) == 1


def test_lcom4_two_unconnected_methods():
    """Two methods sharing no attributes must return LCOM4=2."""
    result = calcular_lcom4({"m1": {"a"}, "m2": {"b"}})
    assert result == 2


def test_lcom4_two_connected_methods():
    """Two methods sharing an attribute must return LCOM4=1."""
    result = calcular_lcom4({"m1": {"a"}, "m2": {"a"}})
    assert result == 1


def test_lcom4_three_methods_two_components():
    """Three methods: m1-m2 share 'a', m3 shares nothing → LCOM4=2."""
    result = calcular_lcom4({"m1": {"a"}, "m2": {"a"}, "m3": {"b"}})
    assert result == 2


def test_lcom4_all_connected():
    """All methods sharing at least one attribute transitively → LCOM4=1."""
    result = calcular_lcom4({"m1": {"a"}, "m2": {"a", "b"}, "m3": {"b"}})
    assert result == 1


# ── WMC / cyclomatic complexity ──────────────────────────────────────────────


def _metodos(src: str):
    tree = javalang.parse.parse(src)
    return list(tree.types[0].methods)


def test_cc_trivial_method_is_one():
    """A method with no decision points has complexity 1."""
    (m,) = _metodos("class A { int f() { return 1; } }")
    assert calcular_complexidade_ciclomatica(m) == 1


def test_cc_abstract_method_is_one():
    """A method without body (abstract/interface) has complexity 1."""
    (m,) = _metodos("abstract class A { abstract void f(); }")
    assert calcular_complexidade_ciclomatica(m) == 1


def test_cc_counts_all_decision_points():
    """if + && + || + for + while + do + 2 case (default excluded) + catch + ternary = 1 + 10."""
    src = """
    class A {
        int f(int x) {
            if (x > 0 && x < 9 || x == 3) {
                for (int i = 0; i < x; i++) { while (true) { do {} while (false); } }
            }
            switch (x) { case 1: break; case 2: break; default: break; }
            try { } catch (Exception e) { }
            return x > 0 ? 1 : 2;
        }
    }
    """
    (m,) = _metodos(src)
    assert calcular_complexidade_ciclomatica(m) == 11


def test_cc_enhanced_for_and_nested_lambda():
    """for-each counts once; decision points inside lambdas count too."""
    src = """
    class A {
        void f(java.util.List<Integer> xs) {
            for (Integer x : xs) { xs.forEach(y -> { if (y > 0) { } }); }
        }
    }
    """
    (m,) = _metodos(src)
    assert calcular_complexidade_ciclomatica(m) == 3


def test_wmc_is_sum_over_methods_and_at_least_nom():
    """WMC sums per-method complexities; getters weigh 1 each."""
    src = """
    class A {
        int a; int b;
        int getA() { return a; }
        int getB() { return b; }
        int f(int x) { if (x > 0) { return a; } return b; }
    }
    """
    metodos = _metodos(src)
    assert calcular_wmc(metodos) == 1 + 1 + 2
    assert calcular_wmc(metodos) >= len(metodos)


def test_wmc_no_methods_is_zero():
    """A class without methods has WMC 0 (NOM 0)."""
    assert calcular_wmc([]) == 0
