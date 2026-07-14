# release.ps1
# Automates the release process for LocalTTS

Write-Host "Extracting version from tts_app_local/main.py..."
$MainPyPath = "tts_app_local/main.py"
$VersionRegex = '__version__\s*=\s*"([^"]+)"'

$MainPyContent = Get-Content $MainPyPath -Raw
if ($MainPyContent -match $VersionRegex) {
    $Version = $Matches[1]
    Write-Host "Found version: v$Version" -ForegroundColor Green
} else {
    Write-Host "Could not find __version__ in $MainPyPath" -ForegroundColor Red
    exit 1
}

$ZipName = "LocalTTS-v$Version.zip"

Write-Host "Building executable with PyInstaller..."
# Navigate to tts_app_local as the spec file is there and expects to be run from there
Push-Location tts_app_local
pyinstaller -y build.spec
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller build failed." -ForegroundColor Red
    Pop-Location
    exit 1
}

Write-Host "Compressing dist/LocalTTS to dist/$ZipName..."
if (Test-Path "dist/$ZipName") {
    Remove-Item "dist/$ZipName"
}
Compress-Archive -Path "dist/LocalTTS" -DestinationPath "dist/$ZipName"

Write-Host "Moving zip to root for easy access..."
Move-Item -Path "dist/$ZipName" -Destination "../$ZipName" -Force
Pop-Location

Write-Host "Creating git tag v$Version..."
git tag -a "v$Version" -m "v$Version release"

Write-Host "Pushing tag to origin..."
git push origin "v$Version"

Write-Host "`nRelease preparation complete!" -ForegroundColor Green
Write-Host "Next steps:"
Write-Host "1. Go to https://github.com/rifat-sarkar01/Text-to-Speech-Generator-On-Local-Device/releases/new"
Write-Host "2. Select tag v$Version"
Write-Host "3. Upload $ZipName as a binary asset"
Write-Host "4. Use the template in RELEASE_TEMPLATE.md for the release notes"
Write-Host "(Or use the gh CLI if installed: gh release create v$Version $ZipName --title `"v$Version`" -F RELEASE_TEMPLATE.md)"
