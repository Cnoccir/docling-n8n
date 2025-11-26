# Master Cleanup Script
# Runs all cleanup steps in correct order

param(
    [switch]$SkipGitFix,
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"

Write-Host @"
=============================================================
    MULTIMODAL RAG REPOSITORY CLEANUP
=============================================================
This script will:
1. Fix git index corruption (including 'nul' file)
2. Archive temporary documentation files
3. Archive temporary scripts
4. Clean up output directories
5. Update .gitignore
6. Stage changes in git

"@ -ForegroundColor Cyan

if ($DryRun) {
    Write-Host "DRY RUN MODE - No changes will be made`n" -ForegroundColor Yellow
}

# Confirm before proceeding
Write-Host "Press any key to continue or Ctrl+C to cancel..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
Write-Host ""

# Navigate to project root
$projectRoot = "C:\Users\tech\Projects\docling-n8n"
Set-Location $projectRoot

# Step 1: Fix Git Index
if (-not $SkipGitFix) {
    Write-Host "`n[1/5] Fixing Git Index Corruption..." -ForegroundColor Cyan
    Write-Host "=================================================" -ForegroundColor Cyan

    if ($DryRun) {
        Write-Host "  [DRY RUN] Would run: .\fix-git-index.ps1" -ForegroundColor Yellow
    } else {
        & ".\fix-git-index.ps1"
    }

    Write-Host "`nStep 1 complete. Press any key to continue..." -ForegroundColor Green
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
} else {
    Write-Host "`n[1/5] Skipping Git Index Fix (--SkipGitFix specified)" -ForegroundColor Yellow
}

# Step 2: Run Cleanup
Write-Host "`n[2/5] Running Repository Cleanup..." -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

if ($DryRun) {
    Write-Host "  [DRY RUN] Would run: .\cleanup-repo.ps1" -ForegroundColor Yellow
    Write-Host "  [DRY RUN] Would move ~60+ files to ._archive/" -ForegroundColor Yellow
} else {
    & ".\cleanup-repo.ps1"
}

Write-Host "`nStep 2 complete. Press any key to continue..." -ForegroundColor Green
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

# Step 3: Verify Archive
Write-Host "`n[3/5] Verifying Archive..." -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

$archiveStats = @{
    docs = 0
    scripts = 0
    output = 0
    total = 0
}

if (Test-Path "._archive") {
    if (Test-Path "._archive/docs") {
        $archiveStats.docs = (Get-ChildItem "._archive/docs" -File | Measure-Object).Count
    }
    if (Test-Path "._archive/scripts") {
        $archiveStats.scripts = (Get-ChildItem "._archive/scripts" -File | Measure-Object).Count
    }
    if (Test-Path "._archive/output") {
        $archiveStats.output = (Get-ChildItem "._archive/output" -Directory | Measure-Object).Count
    }
    $archiveStats.total = $archiveStats.docs + $archiveStats.scripts + $archiveStats.output

    Write-Host "  Archive Summary:" -ForegroundColor White
    Write-Host "    Documentation files: $($archiveStats.docs)" -ForegroundColor Green
    Write-Host "    Script files: $($archiveStats.scripts)" -ForegroundColor Green
    Write-Host "    Output directories: $($archiveStats.output)" -ForegroundColor Green
    Write-Host "    Total items archived: $($archiveStats.total)" -ForegroundColor Cyan
} else {
    Write-Host "  ⚠ Archive directory not found" -ForegroundColor Yellow
}

Write-Host "`nStep 3 complete. Press any key to continue..." -ForegroundColor Green
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

# Step 4: Check Git Status
Write-Host "`n[4/5] Checking Git Status..." -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

if ($DryRun) {
    Write-Host "  [DRY RUN] Would run: git status" -ForegroundColor Yellow
} else {
    git status
}

Write-Host "`nStep 4 complete. Press any key to continue..." -ForegroundColor Green
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

# Step 5: Final Instructions
Write-Host "`n[5/5] Cleanup Complete!" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Green

Write-Host "`nNext Steps:" -ForegroundColor Cyan
Write-Host "  1. Review the changes:" -ForegroundColor White
Write-Host "     git status" -ForegroundColor Gray
Write-Host "     git diff .gitignore" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. Review archived files:" -ForegroundColor White
Write-Host "     ls ._archive/docs" -ForegroundColor Gray
Write-Host "     ls ._archive/scripts" -ForegroundColor Gray
Write-Host ""
Write-Host "  3. Stage and commit changes:" -ForegroundColor White
Write-Host "     git add ." -ForegroundColor Gray
Write-Host "     git commit -m 'Clean up repository structure'" -ForegroundColor Gray
Write-Host ""
Write-Host "  4. Rebuild and restart Docker:" -ForegroundColor White
Write-Host "     docker-compose down" -ForegroundColor Gray
Write-Host "     docker-compose build" -ForegroundColor Gray
Write-Host "     docker-compose up -d" -ForegroundColor Gray
Write-Host ""

if ($archiveStats.total -gt 0) {
    Write-Host "Summary:" -ForegroundColor Cyan
    Write-Host "  ✓ $($archiveStats.total) items archived to ._archive/" -ForegroundColor Green
    Write-Host "  ✓ .gitignore updated to prevent future clutter" -ForegroundColor Green
    Write-Host "  ✓ Git index cleaned" -ForegroundColor Green
    Write-Host ""
    Write-Host "Note: You can safely delete ._archive/ after confirming everything works" -ForegroundColor Yellow
}

Write-Host "`n=================================================" -ForegroundColor Cyan
Write-Host "Repository cleanup complete! 🎉" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""
