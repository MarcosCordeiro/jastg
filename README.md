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
syntactic signals in the source code. A dependency `A → B` with weight `w`
means that class `A` references class `B` in `w` distinct typed positions.

JASTG inspects the following **six categories** of typed syntactic sites
(matching the enumeration in Section 3.1 of the accompanying paper):

### (i) `extends` and `implements` clauses

```java
class A extends B           // A → B
class A implements I        // A → I
```

### (ii) Field types

```java
private B field;            // A → B
```

### (iii) Method and constructor signatures (return and parameter types)

```java
public B getB() { … }       // return type → B
void f(B param)             // parameter type → B
A(B param)                  // constructor parameter type → B
```

### (iv) Object instantiations (`ClassCreator`)

```java
new B(…)                    // A → B
```

### (v) Local variable declarations and cast expressions

```java
B local = …;                // declared type → B
(B) value                   // cast target → B
```

### (vi) `MethodInvocation` qualifier path

```java
B.staticCall()              // A → B (resolved under the upper heuristic)
```

The qualifier path is resolved under a configurable heuristic
(`qualifier_heuristic`, default `upper`); see the *Limitations* section
below for details and modes.

### Nested classes

Inner classes are registered as independent nodes with the `$` notation
used by the Java Virtual Machine for inner-class binary names:
`com.example.Outer$Inner`, `com.example.Outer$Inner$Deep`.

### Object-oriented metrics

JASTG computes the following metrics per class. Note that some
implementations differ from the canonical definitions in ways documented
in the *Limitations* section and in Section 3.2 of the paper:

| Metric | Definition |
|---|---|
| **LCOM4** | Lack of Cohesion of Methods (v4): weakly connected components in the method–attribute graph |
| **CBO** | Coupling Between Objects: number of distinct internal classes depended on (lower bound — see Limitations) |
| **RFC** | Response For a Class: NOM + distinct invoked method names (lower bound — see Limitations) |
| **NOM** | Number of Methods (including constructors) |
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
  "python_version": "3.12.13",
  "platform": "Linux-7.0.5-arch1-1-x86_64-...",
  "javalang_version": "0.13.0",
  "networkx_version": "3.6.1",
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
- **File traversal** uses sorted order to eliminate OS-level non-determinism.
- **Reproducibility fingerprint.** The `metadata_{domain}.json` file records
  the full fingerprint required to reproduce a run, composed of:
    - `config_hash` — SHA-256 digest of the analysis parameters (domains,
      paths, graph mode, qualifier heuristic)
    - `jastg_version`, `javalang_version`, `networkx_version`,
      `python_version` — tool and dependency versions that materially
      affect parsing and graph construction
    - `commit_hash` — exact source version analysed (when run inside a
      git repository)

  No individual field is sufficient in isolation: the `config_hash` alone
  does not capture dependency versions, and the `commit_hash` alone does
  not capture the analysis configuration. The combination of all fields
  is what guarantees exact reproduction of a prior run.

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

## Benchmark Dataset

The official structural graph benchmark generated using JASTG is available at:
https://doi.org/10.5281/zenodo.18744313

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
