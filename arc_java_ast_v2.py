# arc_java_ast_v2.py (v3.2) — Análise estática de código Java via javalang
#
# Versão: v3.2 (congelada para tese)
#
# DEPENDÊNCIAS ESTRUTURAIS CAPTURADAS (sinais tipados, sem type solving):
#   - extends / implements (herança e interfaces)
#   - tipos de campos (fields)
#   - tipos de parâmetros de métodos
#   - tipos de retorno de métodos
#   - ClassCreator (new T(...))
#   - variáveis locais e casts (tipos extraídos do AST)
#   - qualifier de MethodInvocation SOMENTE quando bate inequivocamente
#     com um nome de classe interna do projeto E inicia com maiúscula
#
# RESOLUÇÃO DE TIPOS (sem type solving):
#   1. Tipo já qualificado e presente no conjunto interno -> aceito.
#   1b. Padrão inner class via ".":
#       - 2 partes  (Outer.Inner)     -> Outer$Inner, resolve normalmente.
#       - 3+ partes (pkg.Outer.Inner) -> pkg.Outer$Inner, lookup direto.
#       Apenas as DUAS ÚLTIMAS partes são convertidas. Referências do
#       tipo pkg.Outer.Inner.Deep (inner multinível via ".") NÃO são
#       resolvidas por esta regra — somente inner classes registradas
#       com "$" no conjunto interno são aceitas em lookup direto (regra 1).
#   2. Import explícito (não-static) bate com classe interna -> aceito.
#   3. Import wildcard não-static (a.b.*) + match unívoco -> aceito.
#   4. Pacote atual + nome simples -> aceito se existir nas internas.
#   5. Match unívoco por nome simples global -> aceito.
#   6. Ambiguidade ou ausência -> descartado.
#
# LIMITAÇÕES:
#   - Sem type solving: tipos inferidos (var), genéricos complexos e
#     chamadas encadeadas não são resolvidos.
#   - Inner classes são nós independentes com nome package.Outer$Inner
#     (multinível: package.Outer$Inner$Deep).
#   - Referências a inner classes multinível via notação com ponto
#     (ex.: pkg.Outer.Inner.Deep) NÃO são resolvidas. A regra 1b
#     converte apenas as duas últimas partes (Outer.Inner -> Outer$Inner).
#     Para resolver pkg.Outer.Inner.Deep seria necessário tentar
#     múltiplas posições de corte, o que introduziria ambiguidade sem
#     type solving.
#   - A travessia do corpo de métodos/construtores depende da
#     iterabilidade dos nós do javalang; nós não iteráveis são
#     ignorados (try/except TypeError), o que pode reduzir cobertura
#     em versões futuras da biblioteca.
#   - RFC = NOM + |métodos invocados distintos|. Não distingue classe-alvo
#     da invocação (limitação inerente à análise sem type solving).
#   - CBO conta apenas dependências internas distintas, sem auto-referência.
#   - Qualifier de MethodInvocation: heurística auxiliar filtra qualifiers
#     que iniciam com minúscula (convenção Java: variáveis). Isso reduz
#     falsos positivos mas pode perder referências a classes com nomes
#     fora da convenção.
#   - Imports static são ignorados na resolução de tipos (referem-se a
#     membros, não a classes).
#   - Contagem de peso por aresta: cada ocorrência tipada distinta é
#     contabilizada uma vez (assinatura e corpo contados separadamente,
#     sem dupla contagem).
#
# SAÍDAS:
#   - output/classes_com_ids.txt        (ID dominio/package.Classe)
#   - output/grafo_dependencias_ids.txt (ID_ORIGEM ID_DESTINO PESO)
#   - output/metricas_java.json         (métricas por classe com ID)
#   - output/grafo_metadata.json        (metadados da execução)

import os
import subprocess
import json
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone

import javalang

VERSAO_SCRIPT = "v3.2"


# ═══════════════════════════════════════════════════════════════════════════
# MÓDULO 1: Extração de nomes de tipo do AST javalang
# ═══════════════════════════════════════════════════════════════════════════

def extrair_nomes_de_tipo(type_node):
    """Extrai nomes de tipo (incluindo genéricos) de um nó de tipo javalang.

    Percorre recursivamente ReferenceType, sub_types e argumentos genéricos.
    Retorna set de strings com os nomes encontrados.
    BasicType (int, boolean, etc.) é ignorado.
    """
    nomes = set()
    if type_node is None:
        return nomes

    if isinstance(type_node, javalang.tree.ReferenceType):
        nome = type_node.name
        sub = type_node.sub_type
        while sub is not None:
            nome = f"{nome}.{sub.name}"
            if hasattr(sub, 'arguments') and sub.arguments:
                for arg in sub.arguments:
                    if hasattr(arg, 'type') and arg.type is not None:
                        nomes.update(extrair_nomes_de_tipo(arg.type))
            sub = getattr(sub, 'sub_type', None)
        nomes.add(nome)

        if type_node.arguments:
            for arg in type_node.arguments:
                if hasattr(arg, 'type') and arg.type is not None:
                    nomes.update(extrair_nomes_de_tipo(arg.type))

    elif isinstance(type_node, javalang.tree.BasicType):
        pass

    elif isinstance(type_node, str):
        nomes.add(type_node)

    return nomes


# ═══════════════════════════════════════════════════════════════════════════
# MÓDULO 2: Resolução de tipos
# ═══════════════════════════════════════════════════════════════════════════

def resolver_tipo(nome_tipo, package, imports_explicitos, imports_wildcard,
                  classes_internas, index_nome_simples):
    """Tenta resolver um nome de tipo para um nome qualificado de classe interna.

    Ordem de resolução:
      1. Já qualificado e presente nas classes internas.
      1b. Padrão inner class via ".":
          - 2 partes (Outer.Inner) -> Outer$Inner, resolve recursivamente.
          - 3+ partes (pkg.Outer.Inner) -> pkg.Outer$Inner, lookup direto.
      2. Import explícito (não-static) que termina com o nome e está
         nas internas.
      3. Import wildcard não-static: prefixo + nome, se resultado unívoco
         nas internas.
      4. Pacote atual + nome.
      5. Match unívoco por nome simples no índice global.
      6. None (descartado).
    """
    nome_tipo = nome_tipo.replace("[]", "").strip()
    if not nome_tipo:
        return None

    # 1. Já qualificado?
    if nome_tipo in classes_internas:
        return nome_tipo

    # 1b. Padrão com inner class via "." -> converter últimas 2 partes para "$"
    #
    # Casos tratados (sem type solving, apenas reescrita sintática):
    #   "Outer.Inner"               (2 partes) -> "Outer$Inner"
    #   "com.example.Foo.Inner"     (3+ partes) -> "com.example.Foo$Inner"
    #   "a.b.c.Outer.Inner"         (5 partes)  -> "a.b.c.Outer$Inner"
    #
    # Após a conversão, tenta lookup direto em classes_internas.
    # Não aplica import/pacote/índice ao nome já qualificado (3+ partes),
    # pois ele já carrega o pacote. Para 2 partes, delega recursivamente
    # (o nome convertido não contém ".", então não há recursão infinita).
    if "." in nome_tipo:
        partes = nome_tipo.split(".")
        if len(partes) == 2:
            # Ex: "Outer.Inner" -> "Outer$Inner", resolver normalmente
            candidato_inner = f"{partes[0]}${partes[1]}"
            resultado = resolver_tipo(candidato_inner, package,
                                      imports_explicitos, imports_wildcard,
                                      classes_internas, index_nome_simples)
            if resultado:
                return resultado
        elif len(partes) >= 3:
            # Ex: "com.example.Foo.Inner" -> "com.example.Foo$Inner"
            prefixo = ".".join(partes[:-2])
            candidato_inner = f"{prefixo}.{partes[-2]}${partes[-1]}"
            if candidato_inner in classes_internas:
                return candidato_inner
        return None

    # 2. Import explícito
    for imp in imports_explicitos:
        if imp.endswith(f".{nome_tipo}") and imp in classes_internas:
            return imp

    # 3. Import wildcard
    candidatos_wildcard = []
    for prefix in imports_wildcard:
        candidato = f"{prefix}.{nome_tipo}"
        if candidato in classes_internas:
            candidatos_wildcard.append(candidato)
    if len(candidatos_wildcard) == 1:
        return candidatos_wildcard[0]

    # 4. Pacote atual
    if package:
        candidato = f"{package}.{nome_tipo}"
        if candidato in classes_internas:
            return candidato

    # 5. Match unívoco global por nome simples
    candidatos = index_nome_simples.get(nome_tipo, [])
    if len(candidatos) == 1:
        return candidatos[0]

    return None


def _construir_nome_aninhado(path_ast, decl):
    """Constrói o nome simples de uma declaração, incluindo ancestrais para inner classes.

    Para top-level: retorna decl.name.
    Para inner: retorna Outer$Inner ou Outer$Inner$Deep (multinível).
    """
    outer_classes = [
        n for n in path_ast
        if isinstance(n, (javalang.tree.ClassDeclaration,
                          javalang.tree.InterfaceDeclaration))
    ]
    if outer_classes:
        cadeia = "$".join(n.name for n in outer_classes)
        return f"{cadeia}${decl.name}"
    return decl.name


# ═══════════════════════════════════════════════════════════════════════════
# MÓDULO 3: Coleta de classes internas do projeto (Passe 1)
# ═══════════════════════════════════════════════════════════════════════════

def coletar_classes_internas(dominios, caminhos):
    """Varre todos os .java e constrói o conjunto de classes internas.

    Inner classes são incluídas como nós independentes: package.Outer$Inner.
    Suporta multinível: package.Outer$Inner$Deep.

    Retorna:
        classes_internas: set de nomes qualificados
        index_nome_simples: dict nome_simples -> [lista de qualificados]
        dominio_por_classe: dict nome_qualificado -> dominio
        total_arquivos: int — arquivos .java encontrados
    """
    classes_internas = set()
    dominio_por_classe = {}
    total_arquivos = 0

    for dominio, caminho in zip(dominios, caminhos):
        arquivos = list(Path(caminho).rglob("*.java"))
        total_arquivos += len(arquivos)
        for arquivo in arquivos:
            try:
                source = arquivo.read_text(encoding='utf-8')
                tree = javalang.parse.parse(source)
            except Exception:
                continue

            package = ""
            for _, node in tree:
                if isinstance(node, javalang.tree.PackageDeclaration):
                    package = node.name
                    break

            for tipo_decl in (javalang.tree.ClassDeclaration,
                              javalang.tree.InterfaceDeclaration):
                for path_ast, decl in tree.filter(tipo_decl):
                    nome_simples = _construir_nome_aninhado(path_ast, decl)
                    nome_qual = f"{package}.{nome_simples}" if package else nome_simples
                    classes_internas.add(nome_qual)
                    dominio_por_classe[nome_qual] = dominio

    # Índice nome simples -> qualificados
    index_nome_simples = defaultdict(list)
    for qual in classes_internas:
        partes = qual.rsplit(".", 1)
        nome_s = partes[-1] if len(partes) > 1 else qual
        index_nome_simples[nome_s].append(qual)
        # Registrar também cada segmento após "$" para match por nome simples
        if "$" in nome_s:
            for segmento in nome_s.split("$")[1:]:
                index_nome_simples[segmento].append(qual)

    return classes_internas, dict(index_nome_simples), dominio_por_classe, total_arquivos


# ═══════════════════════════════════════════════════════════════════════════
# MÓDULO 4: Extração de dependências e métricas por classe (Passe 2)
# ═══════════════════════════════════════════════════════════════════════════

def _extrair_imports(tree):
    """Extrai imports explícitos e wildcards de uma CompilationUnit.

    Imports static são ignorados: referem-se a membros (métodos/constantes),
    não a classes, e não devem participar da resolução de tipos.
    """
    explicitos = set()
    wildcards = set()
    for _, node in tree:
        if isinstance(node, javalang.tree.Import):
            if node.path and not node.static:
                if node.wildcard:
                    wildcards.add(node.path)
                else:
                    explicitos.add(node.path)
    return explicitos, wildcards


def _coletar_tipos_no_corpo(class_decl, nome_qual, package,
                             imports_explicitos, imports_wildcard,
                             classes_internas, index_nome_simples):
    """Coleta dependências tipadas e nomes de métodos invocados no corpo de uma classe.

    Retorna:
        dep_counter: Counter {nome_qualificado_destino: contagem}
        rfc_metodos: set de nomes de métodos invocados (distinct)
    """
    dep_counter = Counter()
    rfc_metodos = set()

    def _resolver(nome_tipo):
        return resolver_tipo(nome_tipo, package, imports_explicitos,
                             imports_wildcard, classes_internas, index_nome_simples)

    def _add_tipo(nome_tipo):
        resolvido = _resolver(nome_tipo)
        if resolvido and resolvido != nome_qual:
            dep_counter[resolvido] += 1

    def _add_tipos_de_type_node(type_node):
        for nome in extrair_nomes_de_tipo(type_node):
            _add_tipo(nome)

    # --- extends ---
    if class_decl.extends:
        if isinstance(class_decl.extends, list):
            for ext in class_decl.extends:
                _add_tipos_de_type_node(ext)
        else:
            _add_tipos_de_type_node(class_decl.extends)

    # --- implements (ClassDeclaration) / extends (InterfaceDeclaration pode ter extends) ---
    if hasattr(class_decl, 'implements') and class_decl.implements:
        for impl in class_decl.implements:
            _add_tipos_de_type_node(impl)

    # --- campos (fields) ---
    if class_decl.fields:
        for field in class_decl.fields:
            _add_tipos_de_type_node(field.type)

    def _processar_no(node):
        """Processa um único nó do AST para extração de tipos e RFC."""
        if isinstance(node, javalang.tree.ClassCreator):
            if node.type:
                _add_tipos_de_type_node(node.type)
        elif isinstance(node, javalang.tree.MethodInvocation):
            rfc_metodos.add(node.member)
            # Heurística: só considerar qualifier que inicia com maiúscula
            # (convenção Java — variáveis iniciam com minúscula).
            if node.qualifier and isinstance(node.qualifier, str):
                qual = node.qualifier.strip()
                if qual and qual[0].isupper():
                    resolvido = _resolver(qual)
                    if resolvido and resolvido != nome_qual:
                        dep_counter[resolvido] += 1
        elif isinstance(node, javalang.tree.LocalVariableDeclaration):
            _add_tipos_de_type_node(node.type)
        elif isinstance(node, javalang.tree.Cast):
            _add_tipos_de_type_node(node.type)

    def _percorrer_corpo(statements):
        """Percorre lista de statements (body) extraindo tipos e RFC.

        Recebe metodo.body ou ctor.body (lista de statements), NÃO o nó
        do método/construtor inteiro, para evitar recontagem de tipos
        já contabilizados na assinatura (parâmetros e tipo de retorno).

        Nota: javalang walk_tree yield o próprio nó raiz como primeiro
        elemento, por isso NÃO chamamos _processar_no(stmt) antes de
        iterar — a iteração já inclui o stmt.

        Usa try/except TypeError para robustez: alguns nós do AST podem
        não ser iteráveis dependendo da versão do javalang.
        """
        if not statements:
            return
        for stmt in statements:
            if stmt is None:
                continue
            try:
                for _, node in stmt:
                    _processar_no(node)
            except TypeError:
                continue

    # --- métodos: parâmetros, retorno (assinatura) + corpo (separado) ---
    for metodo in (class_decl.methods or []):
        if metodo.return_type:
            _add_tipos_de_type_node(metodo.return_type)
        for param in (metodo.parameters or []):
            _add_tipos_de_type_node(param.type)
        _percorrer_corpo(metodo.body)

    # --- construtores: parâmetros (assinatura) + corpo (separado) ---
    for ctor in (class_decl.constructors or []):
        for param in (ctor.parameters or []):
            _add_tipos_de_type_node(param.type)
        _percorrer_corpo(ctor.body)

    return dep_counter, rfc_metodos


def calcular_lcom4(metodo_para_atributos):
    """Calcula LCOM4 via componentes conexos no grafo método-atributo."""
    import networkx as nx

    G = nx.Graph()
    metodos = list(metodo_para_atributos.keys())
    for i, m1 in enumerate(metodos):
        G.add_node(m1)
        for j in range(i + 1, len(metodos)):
            m2 = metodos[j]
            if metodo_para_atributos[m1] & metodo_para_atributos[m2]:
                G.add_edge(m1, m2)

    if len(G.nodes) == 0:
        return 1
    return max(nx.number_connected_components(G), 1)


def extrair_dependencias_e_metricas(tree, nome_arquivo, classes_internas,
                                     index_nome_simples, dominio):
    """Extrai métricas e dependências de todas as classes (incluindo inner) em um arquivo.

    Retorna lista de dicts, um por classe/interface encontrada.
    Cada dict contém: classe, chave, arquivo, metricas, arestas_counter.
    """
    package = ""
    for _, node in tree:
        if isinstance(node, javalang.tree.PackageDeclaration):
            package = node.name
            break

    imports_explicitos, imports_wildcard = _extrair_imports(tree)
    resultados = []

    for tipo_decl in (javalang.tree.ClassDeclaration,
                      javalang.tree.InterfaceDeclaration):
        for path_ast, class_decl in tree.filter(tipo_decl):
            nome_simples = _construir_nome_aninhado(path_ast, class_decl)
            nome_qual = f"{package}.{nome_simples}" if package else nome_simples

            # --- Atributos e LCOM4 ---
            atributos = set()
            metodo_para_atributos = defaultdict(set)
            if class_decl.fields:
                for field in class_decl.fields:
                    for decl in field.declarators:
                        atributos.add(decl.name)

            metodos = class_decl.methods or []
            for metodo in metodos:
                for _, node in metodo:
                    if isinstance(node, javalang.tree.MemberReference):
                        if node.member in atributos:
                            metodo_para_atributos[metodo.name].add(node.member)

            lcom4_valor = calcular_lcom4(metodo_para_atributos)

            # --- Dependências (com contagem) e RFC ---
            dep_counter, rfc_metodos = _coletar_tipos_no_corpo(
                class_decl, nome_qual, package,
                imports_explicitos, imports_wildcard,
                classes_internas, index_nome_simples
            )

            # CBO = classes internas distintas das quais esta depende
            # (auto-referência já excluída em _coletar_tipos_no_corpo)
            cbo = len(dep_counter)

            # RFC = NOM + |métodos invocados distintos|
            # Limitação: sem type solving, não sabemos a classe-alvo das invocações.
            nom = len(metodos)
            rfc = nom + len(rfc_metodos)
            noa = len(atributos)

            chave_com_dominio = f"{dominio}/{nome_qual}"

            resultados.append({
                "classe": nome_qual,
                "chave": chave_com_dominio,
                "arquivo": str(nome_arquivo),
                "metricas": {
                    "LCOM4": lcom4_valor,
                    "CBO": cbo,
                    "RFC": rfc,
                    "NOM": nom,
                    "NOA": noa,
                },
                "arestas_counter": dep_counter,  # Counter {destino: peso}
            })

    return resultados


# ═══════════════════════════════════════════════════════════════════════════
# MÓDULO 5: Geração do grafo e exportação
# ═══════════════════════════════════════════════════════════════════════════

def _obter_commit_hash():
    """Tenta obter o hash do commit atual via git. Retorna None se falhar."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def gerar_grafo_nao_direcionado(arestas_ponderadas):
    """Converte arestas direcionadas ponderadas em não-direcionadas.

    Cada aresta (orig, dest) é mapeada para a chave canônica
    (min(orig, dest), max(orig, dest)) e o peso é somado nessa chave.
    Isso significa que pares recíprocos (A->B e B->A) têm seus pesos
    somados, e arestas sem reciprocidade mantêm seu peso original.

    Retorna Counter {(min_id, max_id): peso_somado}.
    """
    grafo_nd = Counter()
    for (orig, dest), peso in arestas_ponderadas.items():
        chave = (min(orig, dest), max(orig, dest))
        grafo_nd[chave] += peso
    return grafo_nd


def exportar_saidas(resultados, arestas_globais, classes_internas,
                    total_arquivos, erros, output_dir,
                    ponderado=True, direcionado=True):
    """Gera todos os arquivos de saída.

    Args:
        resultados: dict chave_com_dominio -> metricas
        arestas_globais: Counter {(nome_qual_orig, nome_qual_dest): peso}
        classes_internas: set de nomes qualificados
        total_arquivos: int
        erros: int
        output_dir: Path
        ponderado: se True, exporta peso na terceira coluna
        direcionado: se True, grafo direcionado; se False, simetriza
    """
    output_dir.mkdir(exist_ok=True)

    # --- Mapeamento chave -> ID ---
    nome_para_id = {
        nome: idx + 1
        for idx, nome in enumerate(sorted(resultados.keys()))
    }

    # --- classes_com_ids.txt ---
    with open(output_dir / "classes_com_ids.txt", "w", encoding="utf-8") as f:
        for nome, idx in nome_para_id.items():
            f.write(f"{idx} {nome}\n")

    # --- Mapear nome_qual -> chave_com_dominio ---
    qual_para_chave = {}
    for chave in resultados:
        pos = chave.index("/")
        nome_qual = chave[pos + 1:]
        qual_para_chave[nome_qual] = chave

    # --- Converter arestas para IDs com peso ---
    arestas_ids = Counter()  # {(id_orig, id_dest): peso}
    for (origem, destino), peso in arestas_globais.items():
        chave_orig = qual_para_chave.get(origem)
        chave_dest = qual_para_chave.get(destino)
        if chave_orig and chave_dest:
            id_orig = nome_para_id.get(chave_orig)
            id_dest = nome_para_id.get(chave_dest)
            if id_orig and id_dest and id_orig != id_dest:
                arestas_ids[(id_orig, id_dest)] += peso

    # --- Simetrizar se não-direcionado ---
    if not direcionado:
        arestas_ids = gerar_grafo_nao_direcionado(arestas_ids)

    # --- grafo_dependencias_ids.txt ---
    arestas_escritas = 0
    with open(output_dir / "grafo_dependencias_ids.txt", "w", encoding="utf-8") as f:
        for (id_a, id_b), peso in sorted(arestas_ids.items()):
            if ponderado:
                f.write(f"{id_a} {id_b} {peso}\n")
            else:
                f.write(f"{id_a} {id_b}\n")
            arestas_escritas += 1

    # --- metricas_java.json ---
    resultados_com_ids = {
        nome: {"id": nome_para_id[nome], **metricas}
        for nome, metricas in resultados.items()
    }
    with open(output_dir / "metricas_java.json", "w", encoding="utf-8") as f:
        json.dump(resultados_com_ids, f, indent=2, ensure_ascii=False)

    # --- grafo_metadata.json ---
    commit_hash = _obter_commit_hash()
    metadata = {
        "versao_script": VERSAO_SCRIPT,
        "data_execucao": datetime.now(timezone.utc).isoformat(),
        "commit_hash": commit_hash,
        "numero_classes": len(resultados),
        "numero_arestas": arestas_escritas,
        "total_arquivos_java": total_arquivos,
        "arquivos_com_erro": erros,
        "direcionado": direcionado,
        "ponderado": ponderado,
    }
    with open(output_dir / "grafo_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return arestas_escritas, metadata


# ═══════════════════════════════════════════════════════════════════════════
# MÓDULO 6: Orquestração (main)
# ═══════════════════════════════════════════════════════════════════════════

def main_java(dominios, caminhos, ponderado=True, direcionado=True):
    """Função principal: coleta classes internas, extrai métricas e gera saída.

    Args:
        dominios: lista de nomes de domínio (rótulos)
        caminhos: lista de caminhos raiz para busca de .java
        ponderado: se True, grafo com peso nas arestas
        direcionado: se True, grafo direcionado (default);
                     se False, simetrizado para compatibilidade com Louvain
    """
    output_dir = Path("output")

    # ── Passe 1: coletar classes internas ──
    print("[INFO] Passe 1: coletando classes internas do projeto...")
    classes_internas, index_nome_simples, dominio_por_classe, total_arquivos = \
        coletar_classes_internas(dominios, caminhos)
    print(f"[INFO] Arquivos .java encontrados: {total_arquivos}")
    print(f"[INFO] Classes internas encontradas: {len(classes_internas)}")

    # ── Passe 2: extrair métricas e dependências ──
    print("[INFO] Passe 2: extraindo métricas e dependências...")
    resultados = {}                  # chave_com_dominio -> metricas
    arestas_globais = Counter()      # {(nome_qual_orig, nome_qual_dest): peso}
    erros = 0

    for dominio, caminho in zip(dominios, caminhos):
        print(f"[INFO] Analisando domínio: {dominio}")
        arquivos = list(Path(caminho).rglob("*.java"))
        for arquivo in arquivos:
            try:
                source = arquivo.read_text(encoding='utf-8')
                tree = javalang.parse.parse(source)
            except Exception as e:
                print(f"[ERRO] Falha ao processar {arquivo}: {e}")
                erros += 1
                continue

            resultados_arquivo = extrair_dependencias_e_metricas(
                tree, arquivo.name, classes_internas, index_nome_simples, dominio
            )
            for resultado in resultados_arquivo:
                chave = resultado["chave"]
                if chave not in resultados:
                    resultados[chave] = resultado["metricas"]
                for destino, peso in resultado["arestas_counter"].items():
                    origem = resultado["classe"]
                    if origem != destino:
                        arestas_globais[(origem, destino)] += peso

    # ── Exportar ──
    print("[INFO] Gerando arquivos de saída...")
    arestas_escritas, metadata = exportar_saidas(
        resultados, arestas_globais, classes_internas,
        total_arquivos, erros, output_dir,
        ponderado=ponderado, direcionado=direcionado,
    )

    # ── Log estruturado ──
    print(f"\n{'='*60}")
    print(f"[RESUMO] {VERSAO_SCRIPT}")
    print(f"  Arquivos .java:      {metadata['total_arquivos_java']}")
    print(f"  Arquivos com erro:   {metadata['arquivos_com_erro']}")
    print(f"  Classes internas:    {len(classes_internas)}")
    print(f"  Classes com métrica: {metadata['numero_classes']}")
    print(f"  Arestas geradas:     {metadata['numero_arestas']}")
    print(f"  Direcionado:         {metadata['direcionado']}")
    print(f"  Ponderado:           {metadata['ponderado']}")
    if metadata['commit_hash']:
        print(f"  Commit:              {metadata['commit_hash'][:12]}")
    print(f"  Data execução:       {metadata['data_execucao']}")

    top_cbo = sorted(resultados.items(), key=lambda x: x[1]["CBO"], reverse=True)[:10]
    if top_cbo:
        print(f"\n  Top 10 classes por CBO:")
        for nome, metricas in top_cbo:
            print(f"    CBO={metricas['CBO']:3d}  {nome}")
    print(f"{'='*60}")

    print("\n[INFO] Saídas geradas em output/:")
    print("  - metricas_java.json")
    print("  - grafo_dependencias_ids.txt")
    print("  - classes_com_ids.txt")
    print("  - grafo_metadata.json")


# ═══════════════════════════════════════════════════════════════════════════
# MÓDULO 7: Teste rápido embutido
# ═══════════════════════════════════════════════════════════════════════════

def _teste_rapido():
    """Teste com classes simples para validar extração de dependências."""
    import tempfile
    import shutil

    print(f"\n[TESTE] arc_java_ast_v2.py {VERSAO_SCRIPT}")
    print("="*60)

    # ── Código-fonte de teste ──

    codigo_foo = """\
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
"""

    codigo_bar = """\
package com.example;

public class Bar {
    private int valor;

    public Foo criarFoo() {
        return new Foo();
    }
}
"""

    codigo_baz = """\
package com.example;

public interface Baz {
    void fazer();
}
"""

    codigo_qux = """\
package com.example;

public class Qux {
    private String nome;
}
"""

    codigo_helper = """\
package com.other;

import com.example.Foo;

public class Helper {
    private Foo foo;
}
"""

    codigo_user = """\
package com.example;

public class User {
    private Foo.Inner innerRef;
}
"""

    codigo_user2 = """\
package com.other;

public class User2 {
    private com.example.Foo.Inner qualifiedInnerRef;
}
"""

    tmpdir = tempfile.mkdtemp()
    try:
        pkg_example = Path(tmpdir) / "com" / "example"
        pkg_other = Path(tmpdir) / "com" / "other"
        pkg_example.mkdir(parents=True)
        pkg_other.mkdir(parents=True)

        (pkg_example / "Foo.java").write_text(codigo_foo, encoding="utf-8")
        (pkg_example / "Bar.java").write_text(codigo_bar, encoding="utf-8")
        (pkg_example / "Baz.java").write_text(codigo_baz, encoding="utf-8")
        (pkg_example / "Qux.java").write_text(codigo_qux, encoding="utf-8")
        (pkg_other / "Helper.java").write_text(codigo_helper, encoding="utf-8")
        (pkg_example / "User.java").write_text(codigo_user, encoding="utf-8")
        (pkg_other / "User2.java").write_text(codigo_user2, encoding="utf-8")

        dominios = ["test-domain"]
        caminhos_teste = [tmpdir]

        # ── Teste 1: Coleta de classes internas (inclui multinível) ──
        print("\n[1] Coleta de classes internas")
        classes_internas, index_nome_simples, dominio_por_classe, total_arq = \
            coletar_classes_internas(dominios, caminhos_teste)

        print(f"    Classes: {sorted(classes_internas)}")
        print(f"    Arquivos: {total_arq}")
        assert "com.example.Foo" in classes_internas
        assert "com.example.Bar" in classes_internas
        assert "com.example.Baz" in classes_internas
        assert "com.example.Qux" in classes_internas
        assert "com.other.Helper" in classes_internas
        assert "com.example.User" in classes_internas
        assert "com.other.User2" in classes_internas
        assert "com.example.Foo$Inner" in classes_internas, \
            f"Inner class não encontrada. Classes: {sorted(classes_internas)}"
        assert "com.example.Foo$Inner$Deep" in classes_internas, \
            f"Deep inner class não encontrada. Classes: {sorted(classes_internas)}"
        assert total_arq == 7
        print("    [OK] Classes internas, inner class e multinível detectadas")

        # ── Teste 2: Dependências de Foo (com imports, sem static) ──
        print("\n[2] Dependências de Foo")
        source_foo = (pkg_example / "Foo.java").read_text(encoding="utf-8")
        tree_foo = javalang.parse.parse(source_foo)
        resultados_foo = extrair_dependencias_e_metricas(
            tree_foo, "Foo.java", classes_internas, index_nome_simples, "test-domain"
        )

        nomes_extraidos = [r["classe"] for r in resultados_foo]
        print(f"    Classes extraídas: {nomes_extraidos}")
        assert "com.example.Foo" in nomes_extraidos, "Foo não extraída"
        assert "com.example.Foo$Inner" in nomes_extraidos, "Inner não extraída"
        assert "com.example.Foo$Inner$Deep" in nomes_extraidos, "Deep não extraída"
        print("    [OK] Foo, Foo$Inner e Foo$Inner$Deep extraídas como nós")

        foo = [r for r in resultados_foo if r["classe"] == "com.example.Foo"][0]
        deps_foo = set(foo["arestas_counter"].keys())
        print(f"    Deps Foo: {sorted(deps_foo)}")

        assert "com.example.Bar" in deps_foo, "Falta extends Bar"
        assert "com.example.Baz" in deps_foo, "Falta implements Baz"
        assert "com.example.Qux" in deps_foo, "Falta field/param/cast Qux"
        assert "com.other.Helper" in deps_foo, "Falta import explícito Helper"
        assert "com.example.Foo" not in deps_foo, "Auto-referência!"
        print("    [OK] extends, implements, field, param, creator, cast, import explícito")

        # ── Teste 3: Inner class tem dependências próprias ──
        print("\n[3] Dependências de Foo$Inner")
        inner = [r for r in resultados_foo if r["classe"] == "com.example.Foo$Inner"][0]
        deps_inner = set(inner["arestas_counter"].keys())
        print(f"    Deps Inner: {sorted(deps_inner)}")
        assert "com.example.Bar" in deps_inner, "Inner: falta field Bar"
        assert "com.example.Qux" in deps_inner, "Inner: falta ClassCreator Qux"
        print("    [OK] Inner class com dependências próprias")

        # ── Teste 3b: Deep inner class (multinível) ──
        print("\n[3b] Dependências de Foo$Inner$Deep")
        deep = [r for r in resultados_foo if r["classe"] == "com.example.Foo$Inner$Deep"][0]
        deps_deep = set(deep["arestas_counter"].keys())
        print(f"    Deps Deep: {sorted(deps_deep)}")
        assert "com.example.Qux" in deps_deep, "Deep: falta field Qux"
        assert deep["metricas"]["NOA"] == 1, f"Deep NOA esperado 1, obteve {deep['metricas']['NOA']}"
        print("    [OK] Deep inner class com dependências e métricas próprias")

        # ── Teste 4: Dependências de Bar ──
        print("\n[4] Dependências de Bar")
        source_bar = (pkg_example / "Bar.java").read_text(encoding="utf-8")
        tree_bar = javalang.parse.parse(source_bar)
        resultados_bar = extrair_dependencias_e_metricas(
            tree_bar, "Bar.java", classes_internas, index_nome_simples, "test-domain"
        )
        bar = resultados_bar[0]
        deps_bar = set(bar["arestas_counter"].keys())
        print(f"    Deps Bar: {sorted(deps_bar)}")
        assert "com.example.Foo" in deps_bar, "Falta return type / ClassCreator Foo"
        print("    [OK] return type + ClassCreator")

        # ── Teste 5: Helper com import cross-package ──
        print("\n[5] Dependências de Helper (cross-package import)")
        source_helper = (pkg_other / "Helper.java").read_text(encoding="utf-8")
        tree_helper = javalang.parse.parse(source_helper)
        resultados_helper = extrair_dependencias_e_metricas(
            tree_helper, "Helper.java", classes_internas, index_nome_simples, "test-domain"
        )
        helper = resultados_helper[0]
        deps_helper = set(helper["arestas_counter"].keys())
        print(f"    Deps Helper: {sorted(deps_helper)}")
        assert "com.example.Foo" in deps_helper, "Helper: falta import Foo"
        print("    [OK] import cross-package resolvido")

        # ── Teste 5b: Static import ignorado ──
        print("\n[5b] Static import ignorado")
        tree_foo_imports = javalang.parse.parse(source_foo)
        imp_expl, imp_wc = _extrair_imports(tree_foo_imports)
        print(f"    Imports explícitos: {imp_expl}")
        print(f"    Imports wildcard: {imp_wc}")
        assert "com.other.Helper" in imp_expl, "Import Helper deveria estar nos explícitos"
        assert "com.other.Helper.staticMethod" not in imp_expl, \
            "Import static não deveria estar nos explícitos"
        print("    [OK] Import static filtrado corretamente")

        # ── Teste 6: Pesos (sem dupla contagem) ──
        print("\n[6] Pesos das arestas (sem dupla contagem)")
        # Foo -> Qux:
        #   assinatura: field(1) + param(1) = 2
        #   corpo:      LocalVar "Qux outro"(1) + Cast "(Qux)"(1) = 2
        #   total = 4
        peso_qux = foo["arestas_counter"].get("com.example.Qux", 0)
        print(f"    Foo->Qux peso: {peso_qux}")
        assert peso_qux == 4, \
            f"Peso Foo->Qux esperado 4 (field+param+localvar+cast), obteve {peso_qux}"
        # Foo -> Bar:
        #   assinatura: extends(1) = 1
        #   corpo:      LocalVar "Bar local"(1) + ClassCreator "new Bar()"(1) = 2
        #   total = 3
        peso_bar = foo["arestas_counter"].get("com.example.Bar", 0)
        print(f"    Foo->Bar peso: {peso_bar}")
        assert peso_bar == 3, \
            f"Peso Foo->Bar esperado 3 (extends+localvar+creator), obteve {peso_bar}"
        print("    [OK] Pesos corretos, sem dupla contagem de assinatura")

        # ── Teste 7: Métricas ──
        print("\n[7] Métricas")
        print(f"    Foo:   {foo['metricas']}")
        print(f"    Bar:   {bar['metricas']}")
        print(f"    Inner: {inner['metricas']}")
        print(f"    Deep:  {deep['metricas']}")
        assert foo["metricas"]["CBO"] == 4, \
            f"CBO Foo esperado 4 (Bar,Baz,Qux,Helper), obteve {foo['metricas']['CBO']}"
        assert foo["metricas"]["NOM"] == 1
        assert foo["metricas"]["NOA"] == 2
        assert inner["metricas"]["NOA"] == 1  # ref
        print("    [OK] CBO, NOM, NOA corretos")

        # ── Teste 7b: Referência Outer.Inner resolvida ──
        print("\n[7b] Referência Outer.Inner -> Outer$Inner")
        source_user = (pkg_example / "User.java").read_text(encoding="utf-8")
        tree_user = javalang.parse.parse(source_user)
        resultados_user = extrair_dependencias_e_metricas(
            tree_user, "User.java", classes_internas, index_nome_simples, "test-domain"
        )
        user = resultados_user[0]
        deps_user = set(user["arestas_counter"].keys())
        print(f"    Deps User: {sorted(deps_user)}")
        assert "com.example.Foo$Inner" in deps_user, \
            f"User: falta resolução Foo.Inner -> Foo$Inner. Deps: {deps_user}"
        print("    [OK] Foo.Inner resolvido para Foo$Inner")

        # ── Teste 7c: Referência qualificada com pacote pkg.Outer.Inner ──
        print("\n[7c] Referência com.example.Foo.Inner -> Foo$Inner")
        source_user2 = (pkg_other / "User2.java").read_text(encoding="utf-8")
        tree_user2 = javalang.parse.parse(source_user2)
        resultados_user2 = extrair_dependencias_e_metricas(
            tree_user2, "User2.java", classes_internas, index_nome_simples, "test-domain"
        )
        user2 = resultados_user2[0]
        deps_user2 = set(user2["arestas_counter"].keys())
        print(f"    Deps User2: {sorted(deps_user2)}")
        assert "com.example.Foo$Inner" in deps_user2, \
            f"User2: falta resolução com.example.Foo.Inner -> com.example.Foo$Inner. Deps: {deps_user2}"
        print("    [OK] com.example.Foo.Inner resolvido para com.example.Foo$Inner")

        # ── Teste 7d: pkg.Outer.Inner.Deep via "." é descartado (limitação documentada) ──
        print("\n[7d] Limitação: pkg.Outer.Inner.Deep via '.' é descartado")
        resultado_deep_dot = resolver_tipo(
            "com.example.Foo.Inner.Deep", "com.other",
            set(), set(), classes_internas, index_nome_simples
        )
        print(f"    resolver_tipo('com.example.Foo.Inner.Deep') = {resultado_deep_dot}")
        assert resultado_deep_dot is None, \
            f"Esperava None (limitação), obteve {resultado_deep_dot}"
        # Confirmar que a forma canônica com "$" funciona diretamente (regra 1)
        resultado_deep_dollar = resolver_tipo(
            "com.example.Foo$Inner$Deep", "com.other",
            set(), set(), classes_internas, index_nome_simples
        )
        assert resultado_deep_dollar == "com.example.Foo$Inner$Deep", \
            f"Forma canônica com $ deveria resolver, obteve {resultado_deep_dollar}"
        print("    [OK] pkg.Outer.Inner.Deep descartado; pkg.Outer$Inner$Deep aceito")

        # ── Teste 8: Grafo não-direcionado ──
        print("\n[8] Grafo não-direcionado")
        arestas_dir = Counter()
        arestas_dir[(1, 2)] = 3  # A->B peso 3
        arestas_dir[(2, 1)] = 1  # B->A peso 1
        arestas_dir[(1, 3)] = 2  # A->C peso 2
        nd = gerar_grafo_nao_direcionado(arestas_dir)
        assert nd[(1, 2)] == 4, f"Esperado 4, obteve {nd[(1, 2)]}"
        assert nd[(1, 3)] == 2, f"Esperado 2, obteve {nd[(1, 3)]}"
        print(f"    Simetrizado: {dict(nd)}")
        print("    [OK] Simetrização com soma de pesos")

        # ── Teste 9: Exportação completa ──
        print("\n[9] Exportação completa (end-to-end)")
        output_test = Path(tmpdir) / "output"
        all_resultados = {}
        all_arestas = Counter()
        for arquivo_java in Path(tmpdir).rglob("*.java"):
            try:
                src = arquivo_java.read_text(encoding="utf-8")
                t = javalang.parse.parse(src)
            except Exception:
                continue
            res = extrair_dependencias_e_metricas(
                t, arquivo_java.name, classes_internas, index_nome_simples, "test-domain"
            )
            for r in res:
                chave = r["chave"]
                if chave not in all_resultados:
                    all_resultados[chave] = r["metricas"]
                for dest, peso in r["arestas_counter"].items():
                    if r["classe"] != dest:
                        all_arestas[(r["classe"], dest)] += peso

        n_arestas, meta = exportar_saidas(
            all_resultados, all_arestas, classes_internas,
            total_arq, 0, output_test,
            ponderado=True, direcionado=True,
        )
        assert (output_test / "classes_com_ids.txt").exists()
        assert (output_test / "grafo_dependencias_ids.txt").exists()
        assert (output_test / "metricas_java.json").exists()
        assert (output_test / "grafo_metadata.json").exists()
        assert meta["versao_script"] == VERSAO_SCRIPT
        assert meta["numero_classes"] == len(all_resultados)
        assert meta["ponderado"] is True
        assert meta["direcionado"] is True
        print(f"    Classes exportadas: {meta['numero_classes']}")
        print(f"    Arestas exportadas: {meta['numero_arestas']}")
        print("    [OK] Todos os arquivos gerados com metadata")

        # Verificar formato do grafo (3 colunas)
        linhas = (output_test / "grafo_dependencias_ids.txt").read_text().strip().split("\n")
        for linha in linhas:
            partes = linha.split()
            assert len(partes) == 3, f"Esperava 3 colunas, obteve: {linha}"
        print(f"    [OK] Formato ponderado (3 colunas) em {len(linhas)} arestas")

        # Exportar não-ponderado para verificar
        n_arestas_np, meta_np = exportar_saidas(
            all_resultados, all_arestas, classes_internas,
            total_arq, 0, output_test,
            ponderado=False, direcionado=True,
        )
        linhas_np = (output_test / "grafo_dependencias_ids.txt").read_text().strip().split("\n")
        for linha in linhas_np:
            partes = linha.split()
            assert len(partes) == 2, f"Esperava 2 colunas, obteve: {linha}"
        print(f"    [OK] Formato não-ponderado (2 colunas)")

        print(f"\n{'='*60}")
        print("[TESTE] Todos os testes passaram!")
        print(f"{'='*60}\n")

    finally:
        shutil.rmtree(tmpdir)


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        _teste_rapido()
    else:
        print(f"arc_java_ast_v2.py {VERSAO_SCRIPT}")
        print("Uso: importar main_java() ou executar com --test para teste rápido.")
        print("  python arc_java_ast_v2.py --test")
        print()
        print("Parâmetros de main_java(dominios, caminhos, ponderado=True, direcionado=True):")
        print("  ponderado=True   -> grafo_dependencias_ids.txt com peso (3 colunas)")
        print("  ponderado=False  -> grafo_dependencias_ids.txt sem peso (2 colunas)")
        print("  direcionado=True -> grafo direcionado (default)")
        print("  direcionado=False-> grafo não-direcionado (simetrizado, para Louvain)")
