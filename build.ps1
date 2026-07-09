# Builds a single distributable CoachNote.exe your friends can just double-click.
# Usage:  ./build.ps1        (from the project root, in PowerShell)
# Output: dist/CoachNote.exe  - one self-contained file, no Python needed on their PC.

# Note: native tools (pip) write notices to stderr; PowerShell 'Stop' would treat those as
# fatal, so we leave the default and verify success by checking for the exe at the end.
Write-Host "==> Installing PyInstaller (one-time)..." -ForegroundColor Cyan
python -m pip install --upgrade pyinstaller 2>&1 | Out-Null

Write-Host "==> Building CoachNote.exe..." -ForegroundColor Cyan
# --add-data bundles the JSON knowledge next to the code (Windows uses ';' as the separator).
# --noconfirm overwrites a previous build; --clean drops stale caches.
# Exclude heavy libs our runtime never uses (they only appear via the optional API backend),
# keeping the exe small and less likely to trip antivirus heuristics.
$excludes = @("anthropic","pydantic","numpy","PIL","setuptools","pip")
$exArgs = $excludes | ForEach-Object { "--exclude-module"; $_ }
python -m PyInstaller --onefile --name CoachNote --add-data "data;data" $exArgs --noconfirm --clean run_coach.py

if (Test-Path "dist/CoachNote.exe") {
    Write-Host "==> Done: dist/CoachNote.exe" -ForegroundColor Green
    Write-Host "Hand that ONE file to a friend. They double-click it, launch a League game, note appears in their browser."
} else {
    Write-Host "Build failed. Check the PyInstaller output above." -ForegroundColor Red
    exit 1
}
