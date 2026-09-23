#!/usr/bin/env python3
"""Measure peak resident set size (peak RSS) of `jastg analyze` per system.

Reads scripts/perf/systems.csv, runs `/usr/bin/time -v jastg analyze ...` for
each domain (1 warm-up + N measured runs), extracts Maximum resident set size
from GNU time's stderr, reports the median in MB. Output is a single
structured log at scripts/perf/results/memory_measurements.log, also streamed
to stdout in real time.

Stdlib only.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CSV_PATH = SCRIPT_DIR / "systems.csv"
RESULTS_DIR = SCRIPT_DIR / "results"
LOG_PATH = RESULTS_DIR / "memory_measurements.log"

GNU_TIME = "/usr/bin/time"

RSS_RE = re.compile(r"Maximum resident set size \(kbytes\):\s*(\d+)")
WALL_RE = re.compile(r"Elapsed \(wall clock\) time \([^)]*\):\s*([0-9:.]+)")


@dataclass
class RunResult:
    rss_mb: float
    wall_s: float


def tee(line: str, log_file) -> None:
    print(line, flush=True)
    log_file.write(line + "\n")
    log_file.flush()


def run_cmd(cmd: list[str]) -> str:
    """Run a command, return stdout stripped. Return '<N/A>' on any failure."""
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, check=False
        )
        if out.returncode != 0:
            return "<N/A>"
        return out.stdout.strip()
    except (FileNotFoundError, OSError):
        return "<N/A>"


def parse_wall(s: str) -> float:
    """Parse GNU time's wall-clock string (m:ss.ss or h:mm:ss) into seconds."""
    parts = s.split(":")
    parts = [float(p) for p in parts]
    if len(parts) == 2:
        m, sec = parts
        return m * 60.0 + sec
    if len(parts) == 3:
        h, m, sec = parts
        return h * 3600.0 + m * 60.0 + sec
    raise ValueError(f"unrecognized wall-clock format: {s!r}")


def check_gnu_time() -> None:
    """Abort with a clear message if /usr/bin/time -v is not available."""
    if not (os.path.isfile(GNU_TIME) and os.access(GNU_TIME, os.X_OK)):
        print("ERROR: /usr/bin/time not found. install GNU time: pacman -S time",
              file=sys.stderr)
        sys.exit(1)
    probe = subprocess.run(
        [GNU_TIME, "-v", "true"], capture_output=True, text=True, check=False
    )
    if "Maximum resident set size" not in probe.stderr:
        print("ERROR: /usr/bin/time exists but does not support -v. "
              "install GNU time: pacman -S time", file=sys.stderr)
        sys.exit(1)


def check_jastg() -> None:
    if shutil.which("jastg") is None:
        print("ERROR: `jastg` not found in PATH. Activate the venv or run "
              "`pip install -e .` from the repo root.", file=sys.stderr)
        sys.exit(1)


def collect_header() -> dict[str, str]:
    info = {}
    info["kernel"] = run_cmd(["uname", "-a"])

    lscpu = run_cmd(["lscpu"])
    cpu_model = "<N/A>"
    cpu_cores = "<N/A>"
    if lscpu != "<N/A>":
        for raw in lscpu.splitlines():
            if cpu_model == "<N/A>" and raw.startswith("Model name:"):
                cpu_model = raw.split(":", 1)[1].strip()
            elif cpu_cores == "<N/A>" and raw.startswith("CPU(s):"):
                cpu_cores = raw.split(":", 1)[1].strip()
    info["cpu_model"] = cpu_model
    info["cpu_cores"] = cpu_cores

    free = run_cmd(["free", "-h"])
    ram = "<N/A>"
    if free != "<N/A>":
        for raw in free.splitlines():
            if raw.startswith("Mem:"):
                cols = raw.split()
                if len(cols) >= 2:
                    ram = cols[1]
                break
    info["ram"] = ram

    info["python"] = sys.version.split()[0]
    info["jastg"] = run_cmd(["jastg", "--version"])

    for pkg in ("javalang", "networkx"):
        version = "<N/A>"
        show = run_cmd([sys.executable, "-m", "pip", "show", pkg])
        if show != "<N/A>":
            for raw in show.splitlines():
                if raw.startswith("Version:"):
                    version = raw.split(":", 1)[1].strip()
                    break
        info[pkg] = version

    return info


def write_header(log_file, info: dict[str, str], started: str,
                 warmup: int, repeats: int) -> None:
    bar = "=" * 62
    tee(bar, log_file)
    tee("JASTG Memory Measurement Run", log_file)
    tee(f"Started: {started}", log_file)
    tee("System:", log_file)
    tee(f"  Kernel: {info['kernel']}", log_file)
    tee(f"  CPU: {info['cpu_model']}", log_file)
    tee(f"  Cores: {info['cpu_cores']}", log_file)
    tee(f"  RAM: {info['ram']}", log_file)
    tee(f"  Python: {info['python']}", log_file)
    tee(f"  JASTG: {info['jastg']}", log_file)
    tee(f"  javalang: {info['javalang']}", log_file)
    tee(f"  networkx: {info['networkx']}", log_file)
    tee(f"Protocol: {warmup} warm-up + {repeats} measured runs, median reported",
        log_file)
    tee(bar, log_file)


def run_jastg(domain: str, abs_path: Path) -> RunResult:
    """Run one /usr/bin/time -v jastg analyze; return (rss_mb, wall_s).

    Raises RuntimeError on jastg failure or parse failure.
    """
    out_dir = Path(f"/tmp/jastg_perf_{domain}")
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        GNU_TIME, "-v",
        "jastg", "analyze",
        "--domain", domain,
        "--path", str(abs_path),
        "--out", str(out_dir),
    ]
    proc = subprocess.run(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, check=False,
    )
    if proc.returncode != 0:
        tail = ""
        if proc.stderr:
            non_time_lines = [
                ln for ln in proc.stderr.splitlines()
                if ln and not ln.startswith("\t")
            ]
            if non_time_lines:
                tail = " | " + non_time_lines[-1][:160]
        raise RuntimeError(f"jastg exited with code {proc.returncode}{tail}")

    rss_match = RSS_RE.search(proc.stderr)
    wall_match = WALL_RE.search(proc.stderr)
    if not rss_match or not wall_match:
        missing = []
        if not rss_match:
            missing.append("Maximum resident set size")
        if not wall_match:
            missing.append("Elapsed (wall clock) time")
        snippet = (proc.stderr or "").strip().replace("\n", " | ")[:240] or "<empty>"
        raise RuntimeError(
            f"failed to parse /usr/bin/time output "
            f"(missing: {', '.join(missing)}; stderr={snippet})"
        )

    rss_kb = int(rss_match.group(1))
    wall_s = parse_wall(wall_match.group(1))
    return RunResult(rss_mb=rss_kb / 1024.0, wall_s=wall_s)


def format_elapsed(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure peak RSS of `jastg analyze` per system.",
    )
    parser.add_argument("--only", metavar="DOMAIN",
                        help="run only the named domain from systems.csv")
    parser.add_argument("--repeats", type=int, default=2,
                        help="number of measured runs (default: 2)")
    parser.add_argument("--warmup", type=int, default=1,
                        help="number of warm-up runs to discard (default: 1)")
    args = parser.parse_args()

    if args.repeats < 1:
        print("ERROR: --repeats must be >= 1", file=sys.stderr)
        return 2
    if args.warmup < 0:
        print("ERROR: --warmup must be >= 0", file=sys.stderr)
        return 2

    check_gnu_time()
    check_jastg()

    if not CSV_PATH.is_file():
        print(f"ERROR: CSV not found at {CSV_PATH}", file=sys.stderr)
        return 1

    csv_dir = CSV_PATH.parent
    with CSV_PATH.open(newline="") as fh:
        rows = list(csv.DictReader(fh))

    if not rows:
        print(f"ERROR: {CSV_PATH} has no data rows", file=sys.stderr)
        return 1

    if "domain" not in rows[0] or "local_path" not in rows[0]:
        print(f"ERROR: CSV must have columns 'domain' and 'local_path'; "
              f"got {list(rows[0].keys())}", file=sys.stderr)
        return 1

    if args.only:
        rows = [r for r in rows if r["domain"] == args.only]
        if not rows:
            print(f"ERROR: domain {args.only!r} not found in {CSV_PATH}",
                  file=sys.stderr)
            return 1

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    started_dt = datetime.now()
    started_iso = started_dt.replace(microsecond=0).isoformat()
    started_monotonic = time.monotonic()

    info = collect_header()

    total = len(rows)
    summary: list[tuple[str, str]] = []  # (domain, median_str_or_ERROR)

    with LOG_PATH.open("w") as log_file:
        write_header(log_file, info, started_iso, args.warmup, args.repeats)

        for i, row in enumerate(rows, start=1):
            domain = row["domain"].strip()
            raw_path = row["local_path"].strip()
            abs_path = (csv_dir / raw_path).resolve()

            tee("", log_file)
            tee(f"[{i}/{total}] {domain}", log_file)

            if not abs_path.is_dir():
                tee(f"  ERROR: path does not exist: {abs_path}", log_file)
                summary.append((domain, "ERROR"))
                continue

            results: list[RunResult] = []
            failed = False
            for k in range(args.warmup + args.repeats):
                if k < args.warmup:
                    label = "warm-up" if args.warmup == 1 else f"warm-up {k + 1}"
                else:
                    label = f"run {k - args.warmup + 1}"
                try:
                    r = run_jastg(domain, abs_path)
                except RuntimeError as exc:
                    tee(f"  ERROR: {label}: {exc}", log_file)
                    failed = True
                    break
                tee(f"  {label:<10} peak_rss={r.rss_mb:.1f} MB  "
                    f"wall={r.wall_s:.2f}s", log_file)
                if k >= args.warmup:
                    results.append(r)

            shutil.rmtree(Path(f"/tmp/jastg_perf_{domain}"), ignore_errors=True)

            if failed or not results:
                summary.append((domain, "ERROR"))
                continue

            median_rss = statistics.median(r.rss_mb for r in results)
            tee(f"  --> median peak_rss = {median_rss:.2f} MB", log_file)
            summary.append((domain, f"{median_rss:.2f}"))

        bar = "=" * 62
        tee("", log_file)
        tee(bar, log_file)
        tee("SUMMARY", log_file)
        tee(bar, log_file)

        name_w = max(len("domain"), max(len(d) for d, _ in summary))
        val_w = max(len("median_peak_rss_mb"),
                    max(len(v) for _, v in summary))
        tee(f"{'domain':<{name_w}}  {'median_peak_rss_mb':>{val_w}}",
            log_file)
        for d, v in summary:
            tee(f"{d:<{name_w}}  {v:>{val_w}}", log_file)
        tee(bar, log_file)

        finished_iso = datetime.now().replace(microsecond=0).isoformat()
        elapsed = time.monotonic() - started_monotonic
        tee(f"Finished: {finished_iso}", log_file)
        tee(f"Total elapsed: {format_elapsed(elapsed)}", log_file)
        tee(bar, log_file)

    return 0


if __name__ == "__main__":
    sys.exit(main())
