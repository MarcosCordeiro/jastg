# JASTG – Java AST Structural Graph

**Static structural dependency analysis for Java codebases.**

[![CI](https://github.com/MarcosCordeiro/jastg/actions/workflows/ci.yml/badge.svg)](https://github.com/MarcosCordeiro/jastg/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/jastg.svg)](https://pypi.org/project/jastg/)
[![Python versions](https://img.shields.io/pypi/pyversions/jastg.svg)](https://pypi.org/project/jastg/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE.txt)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

JASTG extracts class-level dependency graphs and object-oriented metrics from
Java source code using AST parsing only — no JVM, no classpath, no compilation
required.  It is designed for reproducible software-engineering research and
integrates directly with graph analysis tools such as NetworkX, Gephi, and
community-detection algorithms.

---

## Table of Contents

1. [What JASTG captures](#what-jastg-captures)
2. [What JASTG does NOT capture (limitations)](#limitations)
3. [Installation](#installation)
4. [Quick start](#quick-start)
5. [CLI reference](#cli-reference)
6. [Python API](#python-api)
7. [Output formats](#output-formats)
8. [Determinism and reproducibility](#determinism-and-reproducibility)
9. [Running tests](#running-tests)
10. [How to cite](#how-to-cite)
11. [License](#license)

---

## What JASTG captures

JASTG extracts **structural dependencies** between classes based on typed
syntactic signals in the source code.  A dependency `A → B` with weight `w`
means that class `A` references class `B` in `w` distinct typed positions.

| Source of dependency | Example |
|---|---|
| `extends` clause | `class A extends B` |
| `implements` clause | `class A implements I` |
| Field type | `private B field;` |
| Method return type | `public B getB() { … }` |
| Method parameter type | `void f(B param)` |
| Constructor parameter type | `A(B param)` |
| `ClassCreator` | `new B(…)` |
| `LocalVariableDeclaration` | `B local = …;` |
| `Cast` expression | `(B) value` |
| `MethodInvocation` qualifier | `B.staticCall()` (uppercase heuristic) |

**Inner classes** are registered as independent nodes with `$` notation:
`com.example.Outer$Inner`, `com.example.Outer$Inner$Deep`.

**Object-oriented metrics** computed per class:

| Metric | Definition |
|---|---|
| **LCOM4** | Lack of Cohesion of Methods (v4): connected components in method-attribute graph |
| **CBO** | Coupling Between Objects: number of distinct internal classes depended on |
| **RFC** | Response For a Class: NOM + distinct invoked method names |
| **NOM** | Number of Methods |
| **NOA** | Number of Attributes (field declarators) |

---

## Limitations

JASTG performs **syntactic analysis only** — no type solving, no JVM, no
classpath.  The following are known limitations:

- **Type inference** (`var`, generics inference, lambda return types) is not
  resolved.
- **Inner class multilevel dot-notation**: `pkg.Outer.Inner.Deep` is **not**
  resolved.  Only the two last parts are converted (`Outer.Inner` →
  `Outer$Inner`; `pkg.Outer.Inner` → `pkg.Outer$Inner`).  Use `$` notation
  in source code if you need these resolved.
- **Static imports** are ignored (they refer to members, not classes).
- **Chained method calls** (`a.b().c()`) are not type-traced.
- **RFC** does not distinguish the class target of each method invocation
  (inherent limitation without type solving).
- **CBO** counts only references to classes present in the analysed source
  tree (external library classes are not nodes).
- **Qualifier heuristic** (default `--qualifier-heuristic=upper`): only
  `MethodInvocation` qualifiers starting with an uppercase letter are
  resolved as class references.  Classes named with a lowercase first letter
  would be missed; use `--qualifier-heuristic=off` to disable.

---

## Installation

**From PyPI (once published):**

```bash
pip install jastg
```

**From source (editable install for development):**

```bash
git clone https://github.com/MarcosCordeiro/jastg.git
cd jastg
pip install -e ".[dev]"
```

**Requirements:** Python ≥ 3.10, `javalang ≥ 0.13.0`, `networkx ≥ 2.6`.

---

## Quick start

### Single domain

```bash
jastg analyze --domain myapp --path /path/to/src
```

### Multiple domains

```bash
jastg analyze \
    --domain backend  --path /path/to/backend/src \
    --domain frontend --path /path/to/frontend/src
```

### Undirected, unweighted (for Louvain community detection)

```bash
jastg analyze --domain myapp --path /src --undirected --unweighted
```

### From YAML config

```bash
jastg analyze --config analysis.yaml
```

`analysis.yaml` example:

```yaml
domains:
  - name: backend
    path: /path/to/backend
  - name: frontend
    path: /path/to/frontend
weighted: true
directed: true
qualifier_heuristic: upper
output_dir: output
```

### Check installation

```bash
jastg doctor
jastg --version
```

### Try the bundled example

```bash
jastg analyze --domain example --path examples/mini_project
```

---

## CLI reference

```
jastg analyze [OPTIONS]

Options:
  --domain NAME           Domain label (repeat for multiple domains)
  --path PATH             Root path to scan for .java files (paired with --domain)
  --config FILE           YAML configuration file (alternative to --domain/--path)
  --weighted              Export edge weights – third column (default: on)
  --unweighted            Omit edge weights – two-column output
  --directed              Directed graph (default: on)
  --undirected            Symmetrize edges (sum reciprocal weights)
  --out DIR               Output directory (default: output)
  --qualifier-heuristic   'upper' (default) or 'off'
  --fail-fast             Abort on first parse error
  -v, --verbose           DEBUG-level logging
```

---

## Python API

```python
from jastg.pipeline import run

metadata = run(
    dominios=["myapp"],
    caminhos=["/path/to/src"],
    ponderado=True,      # write edge weights
    direcionado=True,    # directed graph
    output_dir="output",
    qualifier_heuristic="upper",
    fail_fast=False,
)

print(metadata["numero_classes"])  # number of classes analysed
print(metadata["numero_arestas"])  # number of edges exported
```

Lower-level API:

```python
import javalang
from jastg.ast.collect import coletar_classes_internas
from jastg.extract import extrair_dependencias_e_metricas

classes, index, domains, n_files = coletar_classes_internas(
    ["myapp"], ["/path/to/src"]
)

source = open("MyClass.java").read()
tree = javalang.parse.parse(source)
results = extrair_dependencias_e_metricas(tree, "MyClass.java", classes, index, "myapp")
```

---

## Output formats

All files are written to `--out/<domain>/` (default `output/<domain>/`).

### `metadata_{domain}.json`

Run provenance for reproducibility (e.g. `metadata_myapp.json`):

```json
{
  "project_url": "https://github.com/owner/repo",
  "jastg_version": "1.0.0",
  "python_version": "3.12.0 ...",
  "platform": "Linux-6.x...",
  "javalang_version": "0.13.0",
  "networkx_version": "3.3",
  "config_hash": "sha256hex...",
  "run_date": "2026-02-22T12:00:00+00:00",
  "commit_hash": "abc123...",
  "num_classes": 9,
  "num_edges": 12,
  "total_java_files": 7,
  "parse_errors": 0,
  "directed": true,
  "weighted": true
}
```

### `graph_{domain}.graphml`

GraphML file ready for import into Gephi or any GraphML-compatible tool
(e.g. `graph_myapp.graphml`).

- **Nodes** – one per class, with attributes:
  - `label`: `domain/package.Class` string
  - `LCOM4`, `CBO`, `RFC`, `NOM`, `NOA`: OO metrics
- **Edges** – one per dependency pair, with optional `weight` attribute
  (present when `--weighted`, absent when `--unweighted`).
  Undirected mode (`--undirected`) symmetrizes pairs as `(min_id, max_id)`
  and sums reciprocal weights.
- **Graph-level metadata** – all fields from `metadata_{domain}.json` are
  embedded directly in the GraphML `<graph>` element.

---

## Determinism and reproducibility

- **IDs** are assigned by alphabetical sort of `domain/class` keys, so they
  are identical across runs given the same input.
- **`config_hash`** in `metadata_{domain}.json` is a SHA-256 digest of the
  effective configuration (domains, paths, graph mode, qualifier heuristic).
  Two runs with the same config hash on the same source tree should produce
  identical graphs.
- File traversal uses sorted order to eliminate OS-level non-determinism.
- The `commit_hash` field (if in a git repository) further pins the exact
  source version analysed.

---

## Running tests

```bash
# All tests (verbose)
pytest -v

# With coverage
pytest --cov=jastg --cov-report=term-missing

# Quick smoke test
pytest -q
```

The test suite requires no external Java installation.  All Java source files
are created as strings in memory during the test session.

---

## How to cite

If you use JASTG in your research, please cite:

```bibtex
@software{jastg2026,
  author    = {Brito Jr, Marcos Cordeiro de},
  title     = {{JASTG}: {Java AST Structural Graph}},
  year      = {2026},
  version   = {1.0.0},
  url       = {https://github.com/MarcosCordeiro/jastg},
  license   = {MIT}
}
```

See also `CITATION.cff` in this repository.

---

## License

MIT — see [LICENSE.txt](LICENSE.txt).
