#!/usr/bin/env bash
# Collect machine specs for JASTG performance reporting.
# Usage: bash collect_system_spec.sh > system_spec.txt

set -u

section() {
  echo ""
  echo "=== $1 ==="
}

# Robust hostname (works without inetutils on minimal Arch installs)
get_hostname() {
  if command -v hostname >/dev/null 2>&1; then
    hostname
  elif command -v hostnamectl >/dev/null 2>&1; then
    hostnamectl --static 2>/dev/null || echo "unknown"
  elif [ -r /etc/hostname ]; then
    cat /etc/hostname
  else
    echo "unknown"
  fi
}

echo "JASTG Performance Measurement — System Specification"
echo "Generated: $(date -Iseconds)"
echo "Hostname:  $(get_hostname)"

section "OS / Kernel"
# Source os-release safely (PRETTY_NAME always present; VERSION_ID may not be — Arch is rolling)
PRETTY_NAME=""
VERSION_ID=""
NAME=""
[ -r /etc/os-release ] && . /etc/os-release
echo "Distribution: ${PRETTY_NAME:-unknown}"
echo "Kernel:       $(uname -srm)"
echo "Uptime:       $(uptime -p 2>/dev/null || uptime)"

section "CPU"
lscpu | grep -E "^(Architecture|Model name|CPU\(s\)|Thread\(s\) per core|Core\(s\) per socket|Socket\(s\)|CPU max MHz|CPU min MHz|L1d cache|L2 cache|L3 cache):" \
  | sed 's/^/  /'

section "Memory"
LC_ALL=C free -h | sed 's/^/  /'

section "Storage (root filesystem)"
df -h / 2>/dev/null | sed 's/^/  /'
ROOT_DEV=$(findmnt -no SOURCE / 2>/dev/null | sed 's|/dev/||; s|[0-9]*$||')
if [ -n "${ROOT_DEV:-}" ] && [ -e "/sys/block/$ROOT_DEV/queue/rotational" ]; then
  ROT=$(cat /sys/block/$ROOT_DEV/queue/rotational)
  if [ "$ROT" = "0" ]; then
    echo "  Type: SSD/NVMe (rotational=0)"
  else
    echo "  Type: HDD (rotational=1)"
  fi
fi

section "Python"
echo "  python:  $(python --version 2>&1)"
echo "  python3: $(python3 --version 2>&1)"
echo "  which:   $(which python 2>/dev/null || echo 'not found')"

section "JASTG and key dependencies"
if command -v jastg >/dev/null 2>&1; then
  echo "  jastg --version: $(jastg --version 2>&1)"
else
  echo "  jastg: NOT FOUND in PATH"
fi

for pkg in javalang networkx; do
  ver=$(python -c "import importlib.metadata as m; print(m.version('$pkg'))" 2>/dev/null || echo "")
  if [ -n "$ver" ]; then
    echo "  $pkg: $ver"
  else
    echo "  $pkg: NOT INSTALLED in current env"
  fi
done

section "GNU time"
if [ -x /usr/bin/time ]; then
  /usr/bin/time --version 2>&1 | head -1 | sed 's/^/  /'
else
  echo "  /usr/bin/time NOT FOUND — install with: sudo pacman -S time"
fi

section "Concise summary for paper (copy-paste ready)"
CPU_MODEL=$(lscpu | grep "Model name" | head -1 | sed 's/.*:[ ]*//')
CPU_CORES=$(lscpu | grep "^CPU(s):" | head -1 | awk '{print $2}')
RAM_GB=$(LC_ALL=C free -g | awk '/^Mem:/ {print $2}')
KERNEL_SHORT=$(uname -r)
PYTHON_SHORT=$(python --version 2>&1 | awk '{print $2}')

# Distro label: Arch is rolling, so version=N/A; show PRETTY_NAME if any
if [ -n "${PRETTY_NAME:-}" ]; then
  DISTRO_SHORT="$PRETTY_NAME"
elif [ -n "${NAME:-}" ]; then
  DISTRO_SHORT="$NAME"
else
  DISTRO_SHORT="Linux (unknown distro)"
fi

cat <<EOF
  ${CPU_MODEL} (${CPU_CORES} logical cores), ${RAM_GB} GiB RAM,
  ${DISTRO_SHORT}, kernel ${KERNEL_SHORT}, Python ${PYTHON_SHORT}.
EOF

echo ""
echo "=== END ==="