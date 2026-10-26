#!/usr/bin/env bash
# Build Wooju.app and a .dmg on an Apple Silicon Mac.
#
#   ./scripts/build-mac.sh
#
# Needs Rust (rustup), Node.js 20+, and uv. Output:
#   apps/desktop/src-tauri/target/release/bundle/macos/Wooju.app
#   apps/desktop/src-tauri/target/release/bundle/dmg/Wooju_<version>_aarch64.dmg
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"

step() { printf '\n\033[1;34m▶ %s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31m✗ %s\033[0m\n' "$1"; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || fail "$1 이(가) 없어요. $2"; }

[[ "$(uname -s)" == "Darwin" ]] || fail "Mac에서 실행해 주세요."
need cargo "https://rustup.rs 에서 Rust를 설치해 주세요."
need node "Node.js 20 이상을 설치해 주세요."
need npm "Node.js와 함께 설치돼요."
need uv "https://docs.astral.sh/uv/ 에서 uv를 설치해 주세요."
TRIPLE="$(rustc -vV | sed -n 's/^host: //p')"
echo "target: $TRIPLE"

step "1/4 화면(UI) 빌드"
npm ci --prefix apps/web --no-audit --no-fund
npm run build --prefix apps/web

step "2/4 Python 서버를 실행 파일 하나로 묶기"
uv sync --all-packages
rm -rf build/pyinstaller
uv run --with "pyinstaller>=6.10" pyinstaller --noconfirm --clean --onefile \
  --name wooju-server \
  --distpath build/pyinstaller/dist --workpath build/pyinstaller/work --specpath build/pyinstaller \
  --paths "$ROOT/apps/server" --paths "$ROOT/packages/brain-core/src" --paths "$ROOT/agents/src" \
  --add-data "$ROOT/apps/web/dist:web" \
  --add-data "$ROOT/template:template" \
  --hidden-import app.main \
  --collect-submodules app \
  --collect-submodules uvicorn \
  --collect-submodules keyring \
  --collect-submodules mcp.server \
  --collect-submodules mcp.shared \
  --hidden-import mcp.types \
  --exclude-module mcp.cli \
  --exclude-module mcp.server.fastmcp \
  --collect-data jsonschema_specifications \
  "$ROOT/apps/server/app/launcher.py"
mkdir -p apps/desktop/src-tauri/binaries
# Replace, never overwrite in place: macOS caches the old code signature for
# the same file and kills the new binary on launch ("Killed: 9").
rm -f "apps/desktop/src-tauri/binaries/wooju-server-$TRIPLE"
cp build/pyinstaller/dist/wooju-server "apps/desktop/src-tauri/binaries/wooju-server-$TRIPLE"

step "3/4 서버 실행 파일 점검"
SMOKE="$(mktemp -d)"
WOOJU_DATA_DIR="$SMOKE" "apps/desktop/src-tauri/binaries/wooju-server-$TRIPLE" --port 48799 >"$SMOKE/server.log" 2>&1 &
PID=$!
ok=""
for _ in $(seq 1 120); do
  if curl -sf http://127.0.0.1:48799/api/health >/dev/null && curl -sf http://127.0.0.1:48799/ | grep -q "<title>"; then ok=1; break; fi
  sleep 0.5
done
kill "$PID" 2>/dev/null || true
[[ -n "$ok" ]] || { tail -40 "$SMOKE/server.log"; fail "서버 실행 파일이 시작되지 않았어요. 위 로그를 확인해 주세요."; }
echo "서버 실행 파일 정상 (API와 화면 응답 확인)"

# The Claude connection: the same binary must answer an MCP handshake on stdio.
mkdir -p "$SMOKE/brain"
printf '{"brain_path": "%s"}' "$SMOKE/brain" >"$SMOKE/settings.json"
INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}'
(printf '%s\n' "$INIT"; sleep 20) | WOOJU_DATA_DIR="$SMOKE" "apps/desktop/src-tauri/binaries/wooju-server-$TRIPLE" --mcp >"$SMOKE/mcp.out" 2>"$SMOKE/mcp.err" &
MCP_PID=$!
ok=""
for _ in $(seq 1 60); do
  if grep -q '"serverInfo"' "$SMOKE/mcp.out" 2>/dev/null; then ok=1; break; fi
  sleep 0.5
done
kill "$MCP_PID" 2>/dev/null || true
pkill -f "wooju-server-$TRIPLE --mcp" 2>/dev/null || true
[[ -n "$ok" ]] || { tail -40 "$SMOKE/mcp.err"; fail "Claude 연결(MCP)이 응답하지 않았어요. 위 로그를 확인해 주세요."; }
echo "Claude 연결(MCP) 정상"

step "4/4 데스크톱 앱 빌드 (처음에는 Rust 컴파일로 몇 분 걸려요)"
npm ci --prefix apps/desktop --no-audit --no-fund
(cd apps/desktop && npx tauri build)

APP="apps/desktop/src-tauri/target/release/bundle/macos/Wooju.app"
printf '\n\033[1;32m✓ 완료\033[0m\n  앱: %s\n  설치 파일: %s\n' "$ROOT/$APP" "$(ls "$ROOT"/apps/desktop/src-tauri/target/release/bundle/dmg/*.dmg 2>/dev/null | head -1)"
echo "  실행: open \"$ROOT/$APP\""
