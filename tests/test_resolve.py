"""Tests for type resolution rules (jastg.ast.resolve)."""

from __future__ import annotations

from jastg.ast.resolve import resolver_tipo


def test_resolve_outer_inner_dot_to_dollar(classes_internas, index_nome_simples):
    """Rule 1b (2-part): 'Foo.Inner' must resolve to 'com.example.Foo$Inner'."""
    result = resolver_tipo(
        "Foo.Inner",
        package="com.example",
        imports_explicitos=set(),
        imports_wildcard=set(),
        classes_internas=classes_internas,
        index_nome_simples=index_nome_simples,
    )
    assert result == "com.example.Foo$Inner", f"Expected 'com.example.Foo$Inner', got {result!r}"


def test_resolve_pkg_outer_inner_dot_to_dollar(classes_internas, index_nome_simples):
    """Rule 1b (3+-part): 'com.example.Foo.Inner' must resolve to 'com.example.Foo$Inner'."""
    result = resolver_tipo(
        "com.example.Foo.Inner",
        package="com.other",
        imports_explicitos=set(),
        imports_wildcard=set(),
        classes_internas=classes_internas,
        index_nome_simples=index_nome_simples,
    )
    assert result == "com.example.Foo$Inner", f"Expected 'com.example.Foo$Inner', got {result!r}"


def test_limitation_outer_inner_deep_dot_discarded(classes_internas, index_nome_simples):
    """Limitation: 'com.example.Foo.Inner.Deep' via '.' must return None.

    Only the two last parts are converted (rule 1b). Multilevel dot-notation
    is a documented limitation and is intentionally not resolved.
    """
    result = resolver_tipo(
        "com.example.Foo.Inner.Deep",
        package="com.other",
        imports_explicitos=set(),
        imports_wildcard=set(),
        classes_internas=classes_internas,
        index_nome_simples=index_nome_simples,
    )
    assert result is None, f"Expected None (documented limitation), got {result!r}"


def test_dollar_notation_resolves_directly(classes_internas, index_nome_simples):
    """Canonical '$' notation must resolve via rule 1 (fully-qualified lookup)."""
    result = resolver_tipo(
        "com.example.Foo$Inner$Deep",
        package="com.other",
        imports_explicitos=set(),
        imports_wildcard=set(),
        classes_internas=classes_internas,
        index_nome_simples=index_nome_simples,
    )
    assert result == "com.example.Foo$Inner$Deep"


def test_resolve_explicit_import(classes_internas, index_nome_simples):
    """Rule 2: explicit import resolves a simple name."""
    result = resolver_tipo(
        "Foo",
        package="com.other",
        imports_explicitos={"com.example.Foo"},
        imports_wildcard=set(),
        classes_internas=classes_internas,
        index_nome_simples=index_nome_simples,
    )
    assert result == "com.example.Foo"


def test_resolve_wildcard_import(classes_internas, index_nome_simples):
    """Rule 3: wildcard import resolves when match is unique."""
    result = resolver_tipo(
        "Baz",
        package="com.other",
        imports_explicitos=set(),
        imports_wildcard={"com.example"},
        classes_internas=classes_internas,
        index_nome_simples=index_nome_simples,
    )
    assert result == "com.example.Baz"


def test_resolve_current_package(classes_internas, index_nome_simples):
    """Rule 4: current package + simple name resolves when the class exists."""
    result = resolver_tipo(
        "Qux",
        package="com.example",
        imports_explicitos=set(),
        imports_wildcard=set(),
        classes_internas=classes_internas,
        index_nome_simples=index_nome_simples,
    )
    assert result == "com.example.Qux"


def test_resolve_unknown_returns_none(classes_internas, index_nome_simples):
    """Unknown type names must return None (rule 6 – discard)."""
    result = resolver_tipo(
        "NonExistentClass",
        package="com.example",
        imports_explicitos=set(),
        imports_wildcard=set(),
        classes_internas=classes_internas,
        index_nome_simples=index_nome_simples,
    )
    assert result is None
