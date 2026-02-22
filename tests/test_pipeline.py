"""End-to-end pipeline tests (jastg.pipeline + jastg.graph.export)."""

from __future__ import annotations

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
            tree,
            arquivo_java.name,
            classes_internas,
            index_nome_simples,
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
        f"Foo.Inner not resolved to Foo$Inner. Deps: {set(user['arestas_counter'].keys())}"
    )


def test_user2_qualified_inner_ref_resolved(mini_project_dir, classes_internas, index_nome_simples):
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


def test_end_to_end_export_outputs(
    tmp_path, mini_project_dir, classes_internas, index_nome_simples, total_arquivos
):
    """Output files must be created and contain valid content."""
    output_dir = tmp_path / "output"
    all_resultados, all_arestas = _build_all_results(
        mini_project_dir, classes_internas, index_nome_simples
    )

    n_arestas, meta = exportar_saidas(
        all_resultados,
        all_arestas,
        classes_internas,
        total_arquivos,
        0,
        output_dir,
        "test-domain",
        ponderado=True,
        direcionado=True,
    )

    assert (output_dir / "metadata_test-domain.json").exists()
    assert (output_dir / "graph_test-domain.graphml").exists()

    assert meta["num_classes"] == len(all_resultados)
    assert meta["weighted"] is True
    assert meta["directed"] is True
    assert meta["parse_errors"] == 0
    assert "jastg_version" in meta


def test_end_to_end_graphml(
    tmp_path, mini_project_dir, classes_internas, index_nome_simples, total_arquivos
):
    """graph.graphml must be a valid GraphML file with nodes and edges."""
    import networkx as nx

    output_dir = tmp_path / "output_gml"
    all_resultados, all_arestas = _build_all_results(
        mini_project_dir, classes_internas, index_nome_simples
    )
    exportar_saidas(
        all_resultados,
        all_arestas,
        classes_internas,
        total_arquivos,
        0,
        output_dir,
        "test-domain",
        ponderado=True,
        direcionado=True,
    )
    graphml_path = output_dir / "graph_test-domain.graphml"
    assert graphml_path.exists(), "graph_test-domain.graphml must be created"

    G = nx.read_graphml(graphml_path)
    assert G.number_of_nodes() == len(all_resultados)
    assert G.number_of_edges() > 0
    # Every node must carry a label and OO metrics
    for _nid, attrs in G.nodes(data=True):
        assert "label" in attrs
        for metric in ("LCOM4", "CBO", "RFC", "NOM", "NOA"):
            assert metric in attrs, f"Node missing metric {metric!r}"
    # Every edge must carry a weight
    for _u, _v, attrs in G.edges(data=True):
        assert "weight" in attrs
    # Graph-level metadata must be present
    for key in ("jastg_version", "run_date", "num_classes", "num_edges", "directed", "weighted"):
        assert key in G.graph, f"Graph metadata missing key {key!r}"


def test_end_to_end_deterministic_ids(
    tmp_path, mini_project_dir, classes_internas, index_nome_simples, total_arquivos
):
    """Running the export twice must produce identical GraphML node/edge sets."""
    import networkx as nx

    all_resultados, all_arestas = _build_all_results(
        mini_project_dir, classes_internas, index_nome_simples
    )
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    exportar_saidas(
        all_resultados, all_arestas, classes_internas, total_arquivos, 0, out1, "test-domain"
    )
    exportar_saidas(
        all_resultados, all_arestas, classes_internas, total_arquivos, 0, out2, "test-domain"
    )

    G1 = nx.read_graphml(out1 / "graph_test-domain.graphml")
    G2 = nx.read_graphml(out2 / "graph_test-domain.graphml")
    assert set(G1.nodes()) == set(G2.nodes()), "Node sets must be identical across runs"
    assert set(G1.edges()) == set(G2.edges()), "Edge sets must be identical across runs"


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

    assert meta["num_classes"] > 0
    assert meta["num_edges"] > 0
    assert meta["parse_errors"] == 0
    assert meta["weighted"] is True
    assert meta["directed"] is True
    assert "jastg_version" in meta
    assert "config_hash" in meta

    domain_dir = tmp_path / "pipeline_out" / "test-domain"
    assert domain_dir.is_dir(), "Domain subdirectory must be created"
    assert (domain_dir / "metadata_test-domain.json").exists()


def test_pipeline_mismatched_lengths(tmp_path):
    """pipeline.run() must raise ValueError on mismatched domain/path lists."""
    from jastg.pipeline import run

    with pytest.raises(ValueError, match="same length"):
        run(
            dominios=["a", "b"],
            caminhos=[str(tmp_path)],
            output_dir=str(tmp_path / "out"),
        )
