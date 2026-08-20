$ErrorActionPreference = "Stop"

Write-Host "[1/8] Ruff lint" -ForegroundColor Cyan
uv run --locked ruff check src tests demo

Write-Host "[2/8] Ruff format check" -ForegroundColor Cyan
uv run --locked ruff format --check src tests demo

Write-Host "[3/8] Mypy" -ForegroundColor Cyan
uv run --locked mypy src

Write-Host "[4/8] Pytest" -ForegroundColor Cyan
uv run --locked pytest -q

Write-Host "[5/8] Demo syntax" -ForegroundColor Cyan
uv run --locked python -m py_compile demo/streamlit_app.py

Write-Host "[6/8] Package compile" -ForegroundColor Cyan
uv run --locked python -m compileall -q src demo

Write-Host "[7/8] Check unexpected TODO(student) in implementation" -ForegroundColor Cyan
$todoMatches = Get-ChildItem src,tests -Recurse -File | Select-String -Pattern 'TODO\(student\)' -ErrorAction SilentlyContinue
if ($todoMatches) {
    $todoMatches | ForEach-Object { Write-Host $_ }
    throw "Found TODO(student) markers in src/tests."
}
Write-Host "No TODO(student) markers in src/tests."

Write-Host "[8/8] Git + secret-prone files" -ForegroundColor Cyan
Write-Host "--- git status --short ---"
git status --short
Write-Host "--- tracked .env/key/cache candidates ---"
$tracked = git ls-files
$bad = $tracked | Where-Object {
    $_ -match '(^|/)\.env($|\.)' -or
    $_ -match '__pycache__|\.pyc$|\.pyo$|\.coverage$|\.DS_Store$|\.egg-info/'
}
if ($bad) {
    $bad | ForEach-Object { Write-Host $_ -ForegroundColor Yellow }
    throw "Tracked secret/cache candidate files found."
}
Write-Host "No tracked .env/cache artifacts found."

Write-Host "ALL CHECKS PASSED" -ForegroundColor Green
