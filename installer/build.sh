#!/usr/bin/env bash
# Compila StreamDockLite-Setup.exe y el paquete de actualización.
# Necesita: Go 1.22+, zip, curl. Funciona en Linux, macOS o WSL (genera el .exe de Windows).
#
#   ./installer/build.sh            -> dist/StreamDockLite-Setup.exe
#                                      dist/StreamDockLite-<versión>-actualizacion.zip
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

# Python portátil con tkinter (python-build-standalone). Debe coincidir con pythonVersion en setup/main.go
PY_TAG="20261026"
PY_VER="3.12.16"
PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_TAG}/cpython-${PY_VER}+${PY_TAG}-x86_64-pc-windows-msvc-install_only.tar.gz"

VERSION=$(python3 -c "import re;print(re.search(r'VERSION\s*=\s*\"([^\"]+)\"',open('StreamDockLite/version.py').read()).group(1))")
echo "==> Stream Dock Lite ${VERSION}"

mkdir -p dist installer/setup/payload

echo "==> Paquete de la app"
rm -f installer/setup/payload/app.zip
zip -qr installer/setup/payload/app.zip StreamDockLite -x "*/__pycache__/*"
cp installer/setup/payload/app.zip "dist/StreamDockLite-${VERSION}-actualizacion.zip"
printf '%s' "$VERSION" > installer/setup/payload/version.txt

if [ ! -f installer/setup/payload/python.tar.gz ]; then
  echo "==> Descargando Python portátil (~47 MB)"
  curl -fL -o installer/setup/payload/python.tar.gz "$PY_URL"
fi

echo "==> Lanzador (StreamDockLite.exe)"
(cd installer/launcher && GOOS=windows GOARCH=amd64 CGO_ENABLED=0 \
  go build -trimpath -ldflags "-H windowsgui -s -w" -o ../setup/launcher.exe .)

echo "==> Pruebas del instalador"
(cd installer/setup && go test ./...)

echo "==> Instalador (StreamDockLite-Setup.exe)"
(cd installer/setup && GOOS=windows GOARCH=amd64 CGO_ENABLED=0 \
  go build -trimpath -ldflags "-s -w" -o "$ROOT/dist/StreamDockLite-Setup.exe" .)

ls -lh dist
