#!/bin/bash
# Install the scanners `make security` needs, at pinned versions, into the
# user's own bin directory (no sudo). Each download is refused unless its
# SHA-256 matches the value pinned here (taken from the GitHub release on
# 2026-11-12; the newest release before the exclude-newer cut-off).
# Linux x86-64 (the TUF) only. semgrep runs through `uvx semgrep==<pinned>`.
set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local/bin}"
mkdir -p "$PREFIX"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if [ "$(uname -s)-$(uname -m)" != "Linux-x86_64" ]; then
    echo "This installer is for Linux x86-64 (the server)." >&2
    exit 1
fi

fetch() { # url sha256 output
    curl -fsSL --proto '=https' --tlsv1.2 "$1" -o "$3"
    echo "$2  $3" | sha256sum --check --quiet || {
        echo "CHECKSUM MISMATCH for $1: refusing to install" >&2
        exit 1
    }
}

GH=https://github.com

fetch "$GH/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz" \
    551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb "$WORK/gitleaks.tgz"
tar -xzf "$WORK/gitleaks.tgz" -C "$WORK" gitleaks
install -m 0755 "$WORK/gitleaks" "$PREFIX/gitleaks"

fetch "$GH/aquasecurity/trivy/releases/download/v0.76.2/trivy_0.76.2_Linux-64bit.tar.gz" \
    bc0fc726e017b8927a62b2d3531d7a84ee01769daf5c99ed866dced54089fdbf "$WORK/trivy.tgz"
tar -xzf "$WORK/trivy.tgz" -C "$WORK" trivy
install -m 0755 "$WORK/trivy" "$PREFIX/trivy"

fetch "$GH/google/osv-scanner/releases/download/v2.7.0/osv-scanner_linux_amd64" \
    160c6253e2922e9e0a6a9771c5c4c40a4b3c6090b34a3cdd5e80c96cc2e4218b "$WORK/osv-scanner"
install -m 0755 "$WORK/osv-scanner" "$PREFIX/osv-scanner"

fetch "$GH/hadolint/hadolint/releases/download/v2.15.1/hadolint-linux-x86_64" \
    c7187db94eeeeca956519a6af171adc31453941a1e777961f6e680f697c8c507 "$WORK/hadolint"
install -m 0755 "$WORK/hadolint" "$PREFIX/hadolint"

echo "Installed into $PREFIX:"
"$PREFIX/gitleaks" version
"$PREFIX/trivy" --version | head -1
"$PREFIX/osv-scanner" --version | head -1
"$PREFIX/hadolint" --version
command -v shellcheck >/dev/null || echo "Also install shellcheck: sudo apt install shellcheck"
