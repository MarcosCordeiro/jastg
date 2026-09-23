# JASTG perf — peak RSS measurement

Mede o pico de memória residente (peak RSS) de `jastg analyze` por sistema,
para complementar a tabela de performance no artigo (SoftwareX).

Nada aqui é versionado: `systems.csv`, `results/` e os diretórios temporários
em `/tmp/jastg_perf_*` ficam fora do git por design (`.gitignore` cobre o CSV
e o diretório `results/`).

## Pré-requisitos

- **GNU time** disponível em `/usr/bin/time` (não confundir com o `time`
  builtin do shell). Em Arch:
  ```bash
  sudo pacman -S time
  ```
  O script aborta com `install GNU time: pacman -S time` se não encontrar.
- `jastg` no PATH (ative o venv ou rode `pip install -e .` na raiz do repo).
- `lscpu`, `free`, `uname` (típicos em qualquer distro Linux).

## Entrada

`scripts/perf/systems.csv` com colunas `domain,local_path`. Paths em
`local_path` podem ser relativos — são resolvidos a partir do próprio
diretório do CSV (`scripts/perf/`).

## Uso

Run completo (21 sistemas, 1 warm-up + 2 medições cada):

```bash
python scripts/perf/measure_memory.py
```

Variantes úteis:

```bash
# Um sistema só (debug ou retomar após falha)
python scripts/perf/measure_memory.py --only camel

# Mais medições por sistema
python scripts/perf/measure_memory.py --repeats 3

# Sem warm-up (não recomendado, mas útil pra smoke test rápido)
python scripts/perf/measure_memory.py --warmup 0 --repeats 1
```

## Saída

Arquivo único: `scripts/perf/results/memory_measurements.log`. O mesmo
conteúdo é emitido no stdout em tempo real (use `tail -f` em outra janela se
quiser observar o progresso enquanto roda).

Estrutura:

- Header com kernel, CPU, RAM, versões de Python/jastg/javalang/networkx e
  protocolo de medição.
- Um bloco `[N/total] <domain>` por sistema, com uma linha por run e a
  mediana ao final.
- Sistemas que falham aparecem como `ERROR: <descrição>` e o script segue
  para o próximo.
- Tabela `SUMMARY` ao final com `domain | median_peak_rss_mb`, mais
  `Finished:` e `Total elapsed:`.

## Protocolo

Para cada sistema: 1 warm-up (descartado) + 2 medições. Mediana das 2
medições é o número reportado. O diretório de saída do `jastg`
(`/tmp/jastg_perf_<domain>`) é apagado e recriado entre runs para isolar a
medida.
