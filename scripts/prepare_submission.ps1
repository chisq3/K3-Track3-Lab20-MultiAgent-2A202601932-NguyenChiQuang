param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Reports = Join-Path $RepoRoot "reports"

Write-Host "Lab 20 submission cleanup" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"

$temporaryNames = @(
    "benchmark_smoke",
    "benchmark_pilot",
    "benchmark_pilot_v2",
    "offline_benchmark_smoke"
)

foreach ($name in $temporaryNames) {
    $target = Join-Path $Reports $name
    if (Test-Path $target) {
        if ($DryRun) {
            Write-Host "[dry-run] remove $target" -ForegroundColor Yellow
        }
        else {
            Remove-Item $target -Recurse -Force
            Write-Host "removed $target" -ForegroundColor Green
        }
    }
}

$gitkeep = Join-Path $Reports ".gitkeep"
if (Test-Path $gitkeep) {
    if ($DryRun) {
        Write-Host "[dry-run] remove $gitkeep" -ForegroundColor Yellow
    }
    else {
        Remove-Item $gitkeep -Force
        Write-Host "removed $gitkeep" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Final report artifacts expected to remain:" -ForegroundColor Cyan
$expected = @(
    "reports/README.md",
    "reports/benchmark_raw.jsonl",
    "reports/benchmark_summary.csv",
    "reports/benchmark_report.md",
    "reports/trace_evidence.md",
    "reports/images/langsmith_multi_agent_trace.png",
    "reports/offline_benchmark/benchmark_raw.jsonl",
    "reports/offline_benchmark/benchmark_summary.csv",
    "reports/offline_benchmark/benchmark_report.md",
    "reports/offline_benchmark/retrieval_manifest.json"
)
foreach ($relative in $expected) {
    $full = Join-Path $RepoRoot $relative
    $marker = if (Test-Path $full) { "OK" } else { "MISSING" }
    Write-Host ("{0,-7} {1}" -f $marker, $relative)
}

if ((Test-Path (Join-Path $RepoRoot ".git")) -and -not $DryRun) {
    Write-Host ""
    Write-Host "git status --short" -ForegroundColor Cyan
    Push-Location $RepoRoot
    try {
        git status --short
    }
    finally {
        Pop-Location
    }
}
