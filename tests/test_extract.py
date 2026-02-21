"""Tests for Pass 2: dependency and metrics extraction (jastg.extract)."""

from __future__ import annotations

from pathlib import Path

import javalang
import pytest  # noqa: F401  # used via pytest fixtures

from jastg.extract import extrair_dependencias_e_metricas

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_file(mini_project_dir: Path, rel_path: str):
    source = (mini_project_dir / rel_path).read_text(encoding="utf-8")
    return javalang.parse.parse(source)


def _get_class(resultados, qual_name: str) -> dict:
    matches = [r for r in resultados if r["classe"] == qual_name]
    assert matches, f"{qual_name!r} not found. Available: {[r['classe'] for r in resultados]}"
    return matches[0]


# ---------------------------------------------------------------------------
# Foo extraction
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def resultados_foo(mini_project_dir, classes_internas, index_nome_simples):
    tree = _parse_file(mini_project_dir, "com/example/Foo.java")
    return extrair_dependencias_e_metricas(
        tree, "Foo.java", classes_internas, index_nome_simples, "test-domain"
    )


def test_extract_dependencies_foo_nodes(resultados_foo):
    """Foo.java must yield three independent class nodes."""
    nomes = [r["classe"] for r in resultados_foo]
    assert "com.example.Foo" in nomes, "Foo not extracted"
    assert "com.example.Foo$Inner" in nomes, "Foo$Inner not extracted"
    assert "com.example.Foo$Inner$Deep" in nomes, "Foo$Inner$Deep not extracted"


def test_extract_dependencies_foo_extends(resultados_foo):
    """Foo must depend on Bar (extends)."""
    foo = _get_class(resultados_foo, "com.example.Foo")
    assert "com.example.Bar" in foo["arestas_counter"], "Missing extends Bar"


def test_extract_dependencies_foo_implements(resultados_foo):
    """Foo must depend on Baz (implements)."""
    foo = _get_class(resultados_foo, "com.example.Foo")
    assert "com.example.Baz" in foo["arestas_counter"], "Missing implements Baz"


def test_extract_dependencies_foo_field_and_param(resultados_foo):
    """Foo must depend on Qux (field + param)."""
    foo = _get_class(resultados_foo, "com.example.Foo")
    assert "com.example.Qux" in foo["arestas_counter"], "Missing field/param Qux"


def test_extract_dependencies_foo_explicit_import(resultados_foo):
    """Foo must depend on Helper (resolved via explicit import)."""
    foo = _get_class(resultados_foo, "com.example.Foo")
    assert "com.other.Helper" in foo["arestas_counter"], "Missing explicit import Helper"


def test_extract_dependencies_foo_no_self_reference(resultados_foo):
    """Foo must not have a self-referencing dependency."""
    foo = _get_class(resultados_foo, "com.example.Foo")
    assert "com.example.Foo" not in foo["arestas_counter"], "Self-reference found!"


# ---------------------------------------------------------------------------
# Inner class
# ---------------------------------------------------------------------------


def test_inner_and_deep_inner(resultados_foo):
    """Foo$Inner and Foo$Inner$Deep must have their own dependencies."""
    inner = _get_class(resultados_foo, "com.example.Foo$Inner")
    deps_inner = set(inner["arestas_counter"].keys())
    assert "com.example.Bar" in deps_inner, "Inner: missing field Bar"
    assert "com.example.Qux" in deps_inner, "Inner: missing ClassCreator Qux"

    deep = _get_class(resultados_foo, "com.example.Foo$Inner$Deep")
    deps_deep = set(deep["arestas_counter"].keys())
    assert "com.example.Qux" in deps_deep, "Deep: missing field Qux"


def test_deep_inner_noa(resultados_foo):
    """Foo$Inner$Deep must have NOA=1 (one field: deepRef)."""
    deep = _get_class(resultados_foo, "com.example.Foo$Inner$Deep")
    assert deep["metricas"]["NOA"] == 1, f"Deep NOA expected 1, got {deep['metricas']['NOA']}"


# ---------------------------------------------------------------------------
# Static import ignored
# ---------------------------------------------------------------------------


def test_static_import_ignored(mini_project_dir):
    """Static import must not appear in the explicit import set."""
    from jastg.ast.resolve import _extrair_imports

    source = (mini_project_dir / "com/example/Foo.java").read_text(encoding="utf-8")
    tree = javalang.parse.parse(source)
    imp_expl, imp_wc = _extrair_imports(tree)

    assert "com.other.Helper" in imp_expl, "Helper should be in explicit imports"
    assert "com.other.Helper.staticMethod" not in imp_expl, "Static import must be filtered out"


# ---------------------------------------------------------------------------
# Edge weights (no double-counting)
# ---------------------------------------------------------------------------


def test_edge_weights_no_double_count(resultados_foo):
    """Verify occurrence-based weights for Foo→Qux and Foo→Bar.

    Foo→Qux:
        signature: field(1) + param(1) = 2
        body:      LocalVar(1) + Cast(1)  = 2
        total = 4

    Foo→Bar:
        signature: extends(1)             = 1
        body:      LocalVar(1) + creator(1) = 2
        total = 3
    """
    foo = _get_class(resultados_foo, "com.example.Foo")

    peso_qux = foo["arestas_counter"].get("com.example.Qux", 0)
    assert peso_qux == 4, f"Foo→Qux weight expected 4 (field+param+localvar+cast), got {peso_qux}"

    peso_bar = foo["arestas_counter"].get("com.example.Bar", 0)
    assert peso_bar == 3, f"Foo→Bar weight expected 3 (extends+localvar+creator), got {peso_bar}"


# ---------------------------------------------------------------------------
# Bar extraction
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def resultados_bar(mini_project_dir, classes_internas, index_nome_simples):
    tree = _parse_file(mini_project_dir, "com/example/Bar.java")
    return extrair_dependencias_e_metricas(
        tree, "Bar.java", classes_internas, index_nome_simples, "test-domain"
    )


def test_bar_depends_on_foo(resultados_bar):
    """Bar must depend on Foo (return type + ClassCreator)."""
    bar = _get_class(resultados_bar, "com.example.Bar")
    assert "com.example.Foo" in bar["arestas_counter"], (
        "Bar: missing return type / ClassCreator Foo"
    )


# ---------------------------------------------------------------------------
# Helper cross-package
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def resultados_helper(mini_project_dir, classes_internas, index_nome_simples):
    tree = _parse_file(mini_project_dir, "com/other/Helper.java")
    return extrair_dependencias_e_metricas(
        tree, "Helper.java", classes_internas, index_nome_simples, "test-domain"
    )


def test_helper_cross_package_import(resultados_helper):
    """Helper must resolve Foo via explicit cross-package import."""
    helper = _get_class(resultados_helper, "com.other.Helper")
    assert "com.example.Foo" in helper["arestas_counter"], "Helper: missing import Foo"


# ---------------------------------------------------------------------------
# OO metrics
# ---------------------------------------------------------------------------


def test_foo_metrics(resultados_foo):
    """Verify CBO, NOM, NOA for Foo."""
    foo = _get_class(resultados_foo, "com.example.Foo")
    m = foo["metricas"]
    assert m["CBO"] == 4, f"CBO(Foo) expected 4 (Bar,Baz,Qux,Helper), got {m['CBO']}"
    assert m["NOM"] == 1, f"NOM(Foo) expected 1, got {m['NOM']}"
    assert m["NOA"] == 2, f"NOA(Foo) expected 2 (atributo,helper), got {m['NOA']}"


def test_inner_metrics(resultados_foo):
    """Verify NOA for Foo$Inner."""
    inner = _get_class(resultados_foo, "com.example.Foo$Inner")
    assert inner["metricas"]["NOA"] == 1, (
        f"NOA(Inner) expected 1 (ref), got {inner['metricas']['NOA']}"
    )
