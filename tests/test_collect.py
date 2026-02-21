"""Tests for Pass 1: internal class collection (jastg.ast.collect)."""

from __future__ import annotations


def test_collect_internal_classes(classes_internas, total_arquivos):
    """All top-level and inner classes must be collected, including multilevel."""
    expected = {
        "com.example.Foo",
        "com.example.Bar",
        "com.example.Baz",
        "com.example.Qux",
        "com.other.Helper",
        "com.example.User",
        "com.other.User2",
        "com.example.Foo$Inner",
        "com.example.Foo$Inner$Deep",
    }
    assert expected <= classes_internas, (
        f"Missing classes: {expected - classes_internas}"
    )


def test_inner_class_registered(classes_internas):
    """Inner class must be registered as an independent node with '$' separator."""
    assert "com.example.Foo$Inner" in classes_internas, (
        f"Inner class not found. All classes: {sorted(classes_internas)}"
    )


def test_deep_inner_class_registered(classes_internas):
    """Multilevel inner class must be registered (Outer$Inner$Deep)."""
    assert "com.example.Foo$Inner$Deep" in classes_internas, (
        f"Deep inner class not found. All classes: {sorted(classes_internas)}"
    )


def test_total_file_count(total_arquivos):
    """Should find exactly 7 .java files in the mini project."""
    assert total_arquivos == 7
