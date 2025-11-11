#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.."; pwd)"
CADIR="$ROOT/certs/ca"
mkdir -p "$CADIR"
openssl genrsa -out "$CADIR/ca.key" 4096
openssl req -x509 -new -nodes -key "$CADIR/ca.key" -sha256 -days 3650 \
  -subj "/C=IN/O=Electrolyser CA/CN=Electrolyser-Root-CA" \
  -out "$CADIR/ca.crt"
echo "01" > "$CADIR/serial"
touch "$CADIR/index.txt"
echo "CA created at certs/ca"

