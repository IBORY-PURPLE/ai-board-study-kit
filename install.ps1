# AI Board Study Kit 설치 스크립트 (Windows PowerShell)
#
#   공부할 과목 폴더에서:
#   irm https://raw.githubusercontent.com/IBORY-PURPLE/ai-board-study-kit/main/install.ps1 | iex
#
# 이미 있는 파일은 덮어쓰지 않는다. CLAUDE.md·AGENTS.md가 이미 있으면 *.study-kit.md로 옆에 둔다.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Repo = 'IBORY-PURPLE/ai-board-study-kit'
$Branch = if ($env:KIT_BRANCH) { $env:KIT_BRANCH } else { 'main' }
$Target = if ($env:KIT_TARGET) { $env:KIT_TARGET } else { (Get-Location).Path }
New-Item -ItemType Directory -Force -Path $Target | Out-Null
$Target = (Resolve-Path $Target).Path
$Tmp = Join-Path ([IO.Path]::GetTempPath()) ("studykit_" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Tmp | Out-Null

try {
    Write-Host ""
    Write-Host "AI Board Study Kit -> $Target"
    Write-Host ""
    Write-Host "[1/4] 키트 내려받기"
    $zip = Join-Path $Tmp 'kit.zip'
    Invoke-WebRequest -UseBasicParsing "https://codeload.github.com/$Repo/zip/$Branch" -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $Tmp
    $Src = Get-ChildItem -Path $Tmp -Directory | ForEach-Object { Join-Path $_.FullName 'template' } | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $Src) { throw '키트 압축을 풀지 못했습니다.' }

    Write-Host "[2/4] 학습 폴더 구성 (기존 파일은 그대로 둠)"
    $added = 0; $kept = 0
    Get-ChildItem -Path $Src -Recurse -File -Force | ForEach-Object {
        $rel = $_.FullName.Substring($Src.Length + 1)
        $dest = Join-Path $Target $rel
        New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
        if (Test-Path $dest) {
            if ($rel -in @('CLAUDE.md', 'AGENTS.md')) {
                $alt = $dest -replace '\.md$', '.study-kit.md'
                Copy-Item $_.FullName $alt -Force
                Write-Host "  - $rel 이(가) 이미 있어 $(Split-Path $alt -Leaf) 로 저장했습니다. 필요한 부분을 합쳐 쓰세요."
            } else { $kept++ }
        } else {
            Copy-Item $_.FullName $dest; $added++
        }
    }
    Write-Host "  새 파일 $added개, 기존 파일 유지 $kept개"

    Write-Host "[3/4] Obsidian 플러그인 내려받기 (공식 GitHub 릴리스)"
    $plugins = @(@{ id = 'pdf-plus'; repo = 'RyotaUshio/obsidian-pdf-plus' }, @{ id = 'realclaudian'; repo = 'YishenTu/claudian' })
    foreach ($p in $plugins) {
        $dir = Join-Path $Target ".obsidian\plugins\$($p.id)"
        if (Test-Path (Join-Path $dir 'main.js')) { Write-Host "  - $($p.id): 이미 있음"; continue }
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        foreach ($a in 'main.js', 'manifest.json', 'styles.css') {
            try { Invoke-WebRequest -UseBasicParsing "https://github.com/$($p.repo)/releases/latest/download/$a" -OutFile (Join-Path $dir $a) } catch {}
        }
        if (Test-Path (Join-Path $dir 'main.js')) { Write-Host "  - $($p.id): 설치 ($($p.repo))" }
        else { Write-Host "  - $($p.id): 내려받기 실패. Obsidian 커뮤니티 플러그인에서 직접 설치하세요." }
    }

    Write-Host "[4/4] 실행 환경 확인"
    $py = @('python', 'py', 'python3') | Where-Object { Get-Command $_ -ErrorAction SilentlyContinue } | Select-Object -First 1
    if (-not $py) {
        Write-Host "  - Python이 없습니다. https://www.python.org 에서 설치한 뒤: pip install pymupdf"
    } else {
        & $py -c "import fitz" 2>$null
        if ($LASTEXITCODE -eq 0) { Write-Host "  - Python + PyMuPDF: 준비됨" }
        else {
            Write-Host "  - PyMuPDF(PDF 필기 도구에 필요) 설치 중..."
            & $py -m pip install --user --quiet --disable-pip-version-check --no-warn-script-location pymupdf
            if ($LASTEXITCODE -eq 0) { Write-Host "  - PyMuPDF: 설치됨" } else { Write-Host "  - 설치 실패. 직접 실행: $py -m pip install pymupdf" }
        }
    }
    if (Get-Command claude -ErrorAction SilentlyContinue) { Write-Host "  - Claude Code: 준비됨" }
    else { Write-Host "  - Claude Code가 없습니다. 설치: npm install -g @anthropic-ai/claude-code  (그다음 터미널에서 claude 로그인)" }

    Write-Host ""
    Write-Host "설치가 끝났습니다. 다음 순서로 시작하세요."
    Write-Host "  1. 강의자료\ 폴더에 강의 PDF를 넣는다."
    Write-Host "  2. Obsidian -> '폴더를 보관함으로 열기' -> 이 폴더 선택 -> 플러그인 사용 허용(제한 모드 끄기)."
    Write-Host "  3. 오른쪽 Claudian 창에서: '강의자료 폴더로 지식베이스 만들어줘. 너는 나의 시험 학습 에이전트야.'"
    Write-Host "  4. 사용법: https://github.com/IBORY-PURPLE/ai-board-study-kit"
    Write-Host ""
}
finally {
    Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}
