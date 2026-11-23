#!/usr/bin/env bash
# AI Board Study Kit 설치 스크립트 (macOS · Linux · Windows Git Bash)
#
#   공부할 과목 폴더에서:
#   curl -fsSL https://raw.githubusercontent.com/IBORY-PURPLE/ai-board-study-kit/main/install.sh | bash
#
#   다른 폴더에 설치하려면:
#   curl -fsSL https://raw.githubusercontent.com/IBORY-PURPLE/ai-board-study-kit/main/install.sh | bash -s -- "<폴더 경로>"
#
# 이미 있는 파일은 덮어쓰지 않는다. CLAUDE.md·AGENTS.md가 이미 있으면 *.study-kit.md로 옆에 둔다.
set -euo pipefail

REPO="IBORY-PURPLE/ai-board-study-kit"
BRANCH="${KIT_BRANCH:-main}"
TARGET="${1:-$PWD}"

say() { printf '%s\n' "$*"; }
mkdir -p "$TARGET"
TARGET="$(cd "$TARGET" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

say ""
say "AI Board Study Kit → $TARGET"
say ""
say "[1/4] 키트 내려받기"
curl -fsSL "https://codeload.github.com/$REPO/tar.gz/$BRANCH" | tar -xz -C "$TMP"
SRC="$(find "$TMP" -mindepth 2 -maxdepth 2 -type d -name template | head -n 1)"
[ -d "$SRC" ] || { say "오류: 키트 압축을 풀지 못했습니다."; exit 1; }

say "[2/4] 학습 폴더 구성 (기존 파일은 그대로 둠)"
added=0; kept=0
while IFS= read -r -d '' f; do
  rel="${f#"$SRC"/}"
  dest="$TARGET/$rel"
  mkdir -p "$(dirname "$dest")"
  if [ -e "$dest" ]; then
    case "$rel" in
      CLAUDE.md|AGENTS.md)
        cp "$f" "${dest%.md}.study-kit.md"
        say "  - $rel 이(가) 이미 있어 ${rel%.md}.study-kit.md 로 저장했습니다. 필요한 부분을 합쳐 쓰세요." ;;
      *) kept=$((kept + 1)) ;;
    esac
  else
    cp "$f" "$dest"; added=$((added + 1))
  fi
done < <(find "$SRC" -type f -print0)
say "  새 파일 $added개, 기존 파일 유지 $kept개"

say "[3/4] Obsidian 플러그인 내려받기 (공식 GitHub 릴리스)"
get_plugin() {  # $1=id  $2=GitHub 저장소
  local dir="$TARGET/.obsidian/plugins/$1"
  if [ -f "$dir/main.js" ]; then say "  - $1: 이미 있음"; return; fi
  mkdir -p "$dir"
  for a in main.js manifest.json styles.css; do
    curl -fsSL "https://github.com/$2/releases/latest/download/$a" -o "$dir/$a" || true
  done
  if [ -f "$dir/main.js" ]; then say "  - $1: 설치 ($2)"; else say "  - $1: 내려받기 실패. Obsidian 커뮤니티 플러그인에서 직접 설치하세요."; fi
}
get_plugin pdf-plus RyotaUshio/obsidian-pdf-plus
get_plugin realclaudian YishenTu/claudian

say "[4/4] 실행 환경 확인"
PY=""
for c in python3 python py; do command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }; done
if [ -z "$PY" ]; then
  say "  - Python이 없습니다. https://www.python.org 에서 설치한 뒤: pip install pymupdf"
elif "$PY" -c "import fitz" >/dev/null 2>&1; then
  say "  - Python + PyMuPDF: 준비됨"
else
  say "  - PyMuPDF(PDF 필기 도구에 필요) 설치 중..."
  "$PY" -m pip install --user --quiet --disable-pip-version-check --no-warn-script-location pymupdf && say "  - PyMuPDF: 설치됨" || say "  - 설치 실패. 직접 실행: $PY -m pip install pymupdf"
fi
if command -v claude >/dev/null 2>&1; then
  say "  - Claude Code: 준비됨"
else
  say "  - Claude Code가 없습니다. 설치: npm install -g @anthropic-ai/claude-code  (그다음 터미널에서 claude 로그인)"
fi

cat <<'EOF'

설치가 끝났습니다. 다음 순서로 시작하세요.
  1. 강의자료/ 폴더에 강의 PDF를 넣는다.
  2. Obsidian → "폴더를 보관함으로 열기" → 이 폴더 선택 → 플러그인 사용 허용(제한 모드 끄기).
  3. 오른쪽 Claudian 창에서: "강의자료 폴더로 지식베이스 만들어줘. 너는 나의 시험 학습 에이전트야."
  4. 사용법: https://github.com/IBORY-PURPLE/ai-board-study-kit

EOF
