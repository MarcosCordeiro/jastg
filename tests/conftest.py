"""Shared fixtures for the JASTG test suite.

Creates a temporary mini Java project on disk (session-scoped) and derives
the ``classes_internas`` / ``index_nome_simples`` data structures from it.
All individual test modules import these fixtures rather than rebuilding
the project themselves.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Mini Java project source code (mirrors the baseline _teste_rapido() data)
# ---------------------------------------------------------------------------

JAVA_SOURCES: dict[str, str] = {
    "com/example/Foo.java": """\
package com.example;

import com.other.Helper;
import static com.other.Helper.staticMethod;

public class Foo extends Bar implements Baz {
    private Qux atributo;
    private Helper helper;

    public Baz metodo(Qux param) {
        Bar local = new Bar();
        Qux outro = (Qux) algo;
        return null;
    }

    public class Inner {
        private Bar ref;
        public void doSomething() {
            new Qux();
        }

        public class Deep {
            private Qux deepRef;
        }
    }
}
""",
    "com/example/Bar.java": """\
package com.example;

public class Bar {
    private int valor;

    public Foo criarFoo() {
        return new Foo();
    }
}
""",
    "com/example/Baz.java": """\
package com.example;

public interface Baz {
    void fazer();
}
""",
    "com/example/Qux.java": """\
package com.example;

public class Qux {
    private String nome;
}
""",
    "com/other/Helper.java": """\
package com.other;

import com.example.Foo;

public class Helper {
    private Foo foo;
}
""",
    "com/example/User.java": """\
package com.example;

public class User {
    private Foo.Inner innerRef;
}
""",
    "com/other/User2.java": """\
package com.other;

public class User2 {
    private com.example.Foo.Inner qualifiedInnerRef;
}
""",
}


@pytest.fixture(scope="session")
def mini_project_dir() -> Path:  # type: ignore[misc]
    """Create the mini Java project in a temporary directory (session-scoped).

    Yields the root :class:`~pathlib.Path` and cleans up after the session.
    """
    tmpdir = tempfile.mkdtemp(prefix="jastg_test_")
    try:
        for rel_path, content in JAVA_SOURCES.items():
            full_path = Path(tmpdir) / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
        yield Path(tmpdir)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="session")
def collected(mini_project_dir: Path):
    """Return the output of Pass 1 for the mini project (session-scoped)."""
    from jastg.ast.collect import coletar_classes_internas

    classes_internas, index_nome_simples, dominio_por_classe, total_arquivos = (
        coletar_classes_internas(["test-domain"], [mini_project_dir])
    )
    return classes_internas, index_nome_simples, dominio_por_classe, total_arquivos


@pytest.fixture(scope="session")
def classes_internas(collected):
    return collected[0]


@pytest.fixture(scope="session")
def index_nome_simples(collected):
    return collected[1]


@pytest.fixture(scope="session")
def total_arquivos(collected):
    return collected[3]
