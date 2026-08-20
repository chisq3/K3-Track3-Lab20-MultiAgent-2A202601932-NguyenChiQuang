$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$GitIgnore = Join-Path $RepoRoot ".gitignore"
$Readme = Join-Path $RepoRoot "README.md"

$ignoreMarker = "# --- Lab 20 showcase / temporary benchmark outputs ---"
$ignoreBlock = @'

# --- Lab 20 showcase / temporary benchmark outputs ---
reports/benchmark_smoke/
reports/benchmark_pilot*/
reports/offline_benchmark_smoke/
reports/*_smoke/
reports/*_pilot*/
!reports/README.md
.streamlit/secrets.toml
# --- end Lab 20 showcase block ---
'@

if (-not (Test-Path $GitIgnore)) {
    New-Item -ItemType File -Path $GitIgnore -Force | Out-Null
}
$ignoreText = Get-Content $GitIgnore -Raw
if (-not $ignoreText.Contains($ignoreMarker)) {
    Add-Content -Path $GitIgnore -Value $ignoreBlock
    Write-Host "Updated .gitignore" -ForegroundColor Green
}
else {
    Write-Host ".gitignore showcase block already present" -ForegroundColor DarkGray
}

$readmeMarker = "<!-- lab20-showcase:start -->"
$readmeBlock = @'

<!-- lab20-showcase:start -->
## Showcase demo

A Streamlit showcase is available at `demo/streamlit_app.py`. The default dashboard reads the committed 27-run online benchmark and 18-run controlled offline benchmark without calling external APIs. Live mode reuses the production Baseline / Multi-agent / Critic runners and can run with either Tavily retrieval or the fixed offline corpus.

```powershell
uv run --locked --extra llm --with "streamlit>=1.38,<2" streamlit run demo/streamlit_app.py
```

See [`demo/README.md`](demo/README.md) for the recommended presentation flow and [`reports/README.md`](reports/README.md) for the evidence layout.
<!-- lab20-showcase:end -->
'@

if (Test-Path $Readme) {
    $readmeText = Get-Content $Readme -Raw

    # Safely update starter checklist lines only when their original text is still present.
    $updatedText = $readmeText.Replace(
        "- [ ] Benchmark report và failure analysis.",
        "- [x] Benchmark report và failure analysis."
    ).Replace(
        "- [ ] Critic/revision loop (bonus).",
        "- [x] Critic/revision loop (bonus; default off, MAX_REVISIONS=1)."
    )
    if ($updatedText -ne $readmeText) {
        Set-Content -Path $Readme -Value $updatedText -Encoding utf8
        $readmeText = $updatedText
        Write-Host "Updated completed milestone checkboxes in README.md" -ForegroundColor Green
    }

    if (-not $readmeText.Contains($readmeMarker)) {
        Add-Content -Path $Readme -Value $readmeBlock
        Write-Host "Added Showcase demo section to README.md" -ForegroundColor Green
    }
    else {
        Write-Host "README showcase section already present" -ForegroundColor DarkGray
    }
}
else {
    Write-Warning "README.md was not found; demo files were still installed."
}
