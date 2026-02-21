"""End-to-end pipeline tests (jastg.pipeline + jastg.graph.export)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import javalang
import pytest

from jastg.extract import extrair_dependencias_e_metricas
from jastg.graph.export import exportar_saidas

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_all_results(mini_project_dir: Path, classes_internas, index_nome_simples):
    """Run Pass 2 over all files in the mini project."""
    all_resultados: dict = {}
    all_arestas: Counter = Counter()
    for arquivo_java in sorted(mini_project_dir.rglob("*.java")):
        try:
            src = arquivo_java.read_text(encoding="utf-8")
            tree = javalang.parse.parse(src)
        except Exception:
            continue
        res = extrair_dependencias_e_metricas(
            tree, arquivo_java.name, classes_internas, index_nome_simples,
            "test-domain",
        )
        for r in res:
            chave = r["chave"]
            if chave not in all_resultados:
                all_resultados[chave] = r["metricas"]
            for dest, peso in r["arestas_counter"].items():
                if r["classe"] != dest:
                    all_arestas[(r["classe"], dest)] += peso
    return all_resultados, all_arestas


# ---------------------------------------------------------------------------
# User / User2 inner-class references
# ---------------------------------------------------------------------------

def test_user_inner_ref_resolved(mini_project_dir, classes_internas, index_nome_simples):
    """User.java: 'Foo.Inner' must resolve to 'com.example.Foo$Inner'."""
    source = (mini_project_dir / "com/example/User.java").read_text(encoding="utf-8")
    tree = javalang.parse.parse(source)
    resultados = extrair_dependencias_e_metricas(
        tree, "User.java", classes_internas, index_nome_simples, "test-domain"
    )
    user = next(r for r in resultados if r["classe"] == "com.example.User")
    assert "com.example.Foo$Inner" in user["arestas_counter"], (
        f"Foo.Inner not resolved to Foo$Inner. Deps: "
        f"{set(user['arestas_counter'].keys())}"
    )


def test_user2_qualified_inner_ref_resolved(mini_project_dir, classes_internas,
                                             index_nome_simples):
    """User2.java: 'com.example.Foo.Inner' must resolve to 'com.example.Foo$Inner'."""
    source = (mini_project_dir / "com/other/User2.java").read_text(encoding="utf-8")
    tree = javalang.parse.parse(source)
    resultados = extrair_dependencias_e_metricas(
        tree, "User2.java", classes_internas, index_nome_simples, "test-domain"
    )
    user2 = next(r for r in resultados if r["classe"] == "com.other.User2")
    assert "com.example.Foo$Inner" in user2["arestas_counter"], (
        f"com.example.Foo.Inner not resolved to Foo$Inner. Deps: "
        f"{set(user2['arestas_counter'].keys())}"
    )


# ---------------------------------------------------------------------------
# End-to-end export
# ---------------------------------------------------------------------------

def test_end_to_end_export_outputs(tmp_path, mini_project_dir,
                                    classes_internas, index_nome_simples,
                                    total_arquivos):
    """All four output files must be created and contain valid content."""
    output_dir = tmp_path / "output"
    all_resultados, all_arestas = _build_all_results(
        mini_project_dir, classes_internas, index_nome_simples
    )

    n_arestas, meta = exportar_saidas(
        all_resultados, all_arestas, classes_internas,
        total_arquivos, 0, output_dir,
        ponderado=True, direcionado=True,
    )

    assert (output_dir / "classes_com_ids.txt").exists()
    assert (output_dir / "grafo_dependencias_ids.txt").exists()
    assert (output_dir / "metricas_java.json").exists()
    assert (output_dir / "grafo_metadata.json").exists()

    assert meta["numero_classes"] == len(all_resultados)
    assert meta["ponderado"] is True
    assert meta["direcionado"] is True
    assert meta["arquivos_com_erro"] == 0
    assert "jastg_version" in meta


def test_end_to_end_weighted_format(tmp_path, mini_project_dir,
                                    classes_internas, index_nome_simples,
                                    total_arquivos):
    """Weighted output must have exactly 3 columns per line."""
    output_dir = tmp_path / "output_w"
    all_resultados, all_arestas = _build_all_results(
        mini_project_dir, classes_internas, index_nome_simples
    )
    exportar_saidas(
        all_resultados, all_arestas, classes_internas,
        total_arquivos, 0, output_dir,
        ponderado=True, direcionado=True,
    )
    lines = (output_dir / "grafo_dependencias_ids.txt").read_text().strip().splitlines()
    assert lines, "Graph file must not be empty"
    for line in lines:
        parts = line.split()
        assert len(parts) == 3, f"Expected 3 columns (weighted), got: {line!r}"


def test_end_to_end_unweighted_format(tmp_path, mini_project_dir,
                                      classes_internas, index_nome_simples,
                                      total_arquivos):
    """Unweighted output must have exactly 2 columns per line."""
    output_dir = tmp_path / "output_uw"
    all_resultados, all_arestas = _build_all_results(
        mini_project_dir, classes_internas, index_nome_simples
    )
    exportar_saidas(
        all_resultados, all_arestas, classes_internas,
        total_arquivos, 0, output_dir,
        ponderado=False, direcionado=True,
    )
    lines = (output_dir / "grafo_dependencias_ids.txt").read_text().strip().splitlines()
    assert lines, "Graph file must not be empty"
    for line in lines:
        parts = line.split()
        assert len(parts) == 2, f"Expected 2 columns (unweighted), got: {line!r}"


def test_end_to_end_metrics_json_valid(tmp_path, mini_project_dir,
                                       classes_internas, index_nome_simples,
                                       total_arquivos):
    """metricas_java.json must be valid JSON with expected metric keys."""
    output_dir = tmp_path / "output_m"
    all_resultados, all_arestas = _build_all_results(
        mini_project_dir, classes_internas, index_nome_simples
    )
    exportar_saidas(
        all_resultados, all_arestas, classes_internas,
        total_arquivos, 0, output_dir,
    )
    data = json.loads((output_dir / "metricas_java.json").read_text())
    assert len(data) == len(all_resultados)
    for _key, entry in data.items():
        assert "id" in entry
        for metric in ("LCOM4", "CBO", "RFC", "NOM", "NOA"):
            assert metric in entry, f"Missing metric {metric!r}"


def test_end_to_end_deterministic_ids(tmp_path, mini_project_dir,
                                      classes_internas, index_nome_simples,
                                      total_arquivos):
    """Running the export twice must produce identical classes_com_ids.txt."""
    all_resultados, all_arestas = _build_all_results(
        mini_project_dir, classes_internas, index_nome_simples
    )
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    exportar_saidas(all_resultados, all_arestas, classes_internas,
                    total_arquivos, 0, out1)
    exportar_saidas(all_resultados, all_arestas, classes_internas,
                    total_arquivos, 0, out2)

    text1 = (out1 / "classes_com_ids.txt").read_text()
    text2 = (out2 / "classes_com_ids.txt").read_text()
    assert text1 == text2, "ID mapping must be deterministic across runs"


def test_pipeline_run(tmp_path, mini_project_dir):
    """jastg.pipeline.run() must complete and return a valid metadata dict."""
    from jastg.pipeline import run

    meta = run(
        dominios=["test-domain"],
        caminhos=[str(mini_project_dir)],
        ponderado=True,
        direcionado=True,
        output_dir=str(tmp_path / "pipeline_out"),
    )

    assert meta["numero_classes"] > 0
    assert meta["numero_arestas"] > 0
    assert meta["arquivos_com_erro"] == 0
    assert meta["ponderado"] is True
    assert meta["direcionado"] is True
    assert "jastg_version" in meta
    assert "config_hash" in meta


def test_pipeline_mismatched_lengths(tmp_path):
    """pipeline.run() must raise ValueError on mismatched domain/path lists."""
    from jastg.pipeline import run

    with pytest.raises(ValueError, match="same length"):
        run(
            dominios=["a", "b"],
            caminhos=[str(tmp_path)],
            output_dir=str(tmp_path / "out"),
        )
