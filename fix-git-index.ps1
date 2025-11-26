# Fix Git Index Corruption Script
# Run this FIRST before cleanup

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Git Index Corruption Fix" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# Navigate to project root
$projectRoot = "C:\Users\tech\Projects\docling-n8n"
Set-Location $projectRoot

Write-Host "Step 1: Checking for 'nul' file (Windows reserved name)..." -ForegroundColor Yellow
if (Test-Path "nul") {
    Write-Host "  Found 'nul' file - this is causing issues!" -ForegroundColor Red
    Write-Host "  Attempting to remove..." -ForegroundColor Yellow

    # Multiple methods to remove 'nul' file
    try {
        # Method 1: Use full path
        $fullPath = Join-Path $projectRoot "nul"
        Remove-Item -Path "\\?\$fullPath" -Force -ErrorAction Stop
        Write-Host "  ✓ Removed 'nul' file using full path" -ForegroundColor Green
    } catch {
        Write-Host "  Method 1 failed, trying alternative..." -ForegroundColor Yellow
        try {
            # Method 2: Use cmd
            cmd /c "del nul"
            Write-Host "  ✓ Removed 'nul' file using cmd" -ForegroundColor Green
        } catch {
            Write-Host "  ✗ Failed to remove 'nul' file automatically" -ForegroundColor Red
            Write-Host "  Manual fix: Open Command Prompt as Admin and run: del nul" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "  ✓ No 'nul' file found" -ForegroundColor Green
}

Write-Host ""
Write-Host "Step 2: Backing up current git index..." -ForegroundColor Yellow
if (Test-Path ".git\index") {
    Copy-Item ".git\index" ".git\index.backup" -Force
    Write-Host "  ✓ Backup created: .git\index.backup" -ForegroundColor Green
} else {
    Write-Host "  ! No index file found" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Step 3: Resetting git index..." -ForegroundColor Yellow
try {
    # Remove the corrupt index
    Remove-Item ".git\index" -Force -ErrorAction Stop
    Write-Host "  ✓ Removed corrupt index" -ForegroundColor Green

    # Reset the index
    git reset
    Write-Host "  ✓ Git index reset" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Error resetting index: $_" -ForegroundColor Red
    Write-Host "  Restoring backup..." -ForegroundColor Yellow
    Copy-Item ".git\index.backup" ".git\index" -Force
}

Write-Host ""
Write-Host "Step 4: Running git garbage collection..." -ForegroundColor Yellow
git gc --prune=now
Write-Host "  ✓ Garbage collection complete" -ForegroundColor Green

Write-Host ""
Write-Host "Step 5: Checking git status..." -ForegroundColor Yellow
git status --short | Select-Object -First 20

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Git index fix complete!" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next step: Run .\cleanup-repo.ps1" -ForegroundColor Cyan
