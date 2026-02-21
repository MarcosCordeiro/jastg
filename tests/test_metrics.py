"""Tests for OO metrics calculations (jastg.metrics.metrics)."""

from __future__ import annotations

from jastg.metrics.metrics import calcular_lcom4


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
