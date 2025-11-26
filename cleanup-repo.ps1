# Repository Cleanup Script
# Moves temporary files to archive directories

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Repository Cleanup Script" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# Navigate to project root
$projectRoot = "C:\Users\tech\Projects\docling-n8n"
Set-Location $projectRoot

# Create archive directories
Write-Host "Creating archive directories..." -ForegroundColor Yellow
$archiveDocs = "._archive/docs"
$archiveScripts = "._archive/scripts"
$archiveOutput = "._archive/output"
$archiveOld = "._archive/old-workflows"

New-Item -ItemType Directory -Path $archiveDocs -Force | Out-Null
New-Item -ItemType Directory -Path $archiveScripts -Force | Out-Null
New-Item -ItemType Directory -Path $archiveOutput -Force | Out-Null
New-Item -ItemType Directory -Path $archiveOld -Force | Out-Null
Write-Host "  ✓ Archive directories created" -ForegroundColor Green

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Phase 1: Archiving Temporary Documentation" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# List of temporary documentation files to archive
$docsToArchive = @(
    "ANSWERS.md",
    "API_REFERENCE.md",
    "CHAT_FEATURE_FIXED.md",
    "CHAT_FEATURE_GUIDE.md",
    "CHAT_FORMATTING_FIX.md",
    "CHAT_HISTORY_IMPLEMENTATION.md",
    "CHAT_IMPROVEMENTS_IMPLEMENTED.md",
    "CHAT_IMPROVEMENTS_PLAN.md",
    "CHAT_QUICKSTART.md",
    "CHAT_SYSTEM_STATUS.md",
    "CHAT_UI_IMPROVEMENTS.md",
    "CHAT_UI_REFINEMENTS.md",
    "CHAT_UX_IMPROVEMENTS.md",
    "CLEAN_IMPLEMENTATION_GUIDE.md",
    "CODE_NODE_ROUTER_FIX.md",
    "COMPLETE_PIPELINE_ANALYSIS.md",
    "CONTEXT_EXPANSION_FIX.md",
    "CRITICAL_ISSUES_STATUS.md",
    "CURRENT_SYSTEM_AUDIT.md",
    "DASHBOARD_README.md",
    "DEPLOYMENT_CHECKLIST.md",
    "DEPLOYMENT_CORRECTED.md",
    "DEPLOYMENT_READY.md",
    "DOCKER_SETUP.md",
    "DOCKER_START.md",
    "ERROR_RESPONSE_FIX.md",
    "FINAL_STEPS.md",
    "FIXES_APPLIED.md",
    "FORMATTING_FINAL_FIX.md",
    "GDRIVE_CITATION_SETUP.md",
    "GDRIVE_CORS_FIXED.md",
    "GDRIVE_CORS_SOLUTIONS.md",
    "GDRIVE_MANUAL_UPDATE.md",
    "GDRIVE_UPLOAD_FIXED.md",
    "GOLDEN_CHUNK_MULTIMODAL_PLAN.md",
    "GOOGLE_DRIVE_COMPLETE.md",
    "GOOGLE_DRIVE_SETUP.md",
    "GPT4O_MINI_COST_SAVINGS.md",
    "HIERARCHY_FIXES.md",
    "IF_NODE_FIX.md",
    "IMPLEMENTATION_COMPLETE_SUMMARY.md",
    "IMPLEMENTATION_SUMMARY.md",
    "LARGE_PDF_FIXES.md",
    "LAUNCH.md",
    "MIGRATION_STATUS.md",
    "MULTIMODAL_RAG_COMPLETE.md",
    "MULTI_DOCUMENT_SEARCH_PLAN.md",
    "ORCHESTRATOR_ARCHITECTURE.md",
    "PAGE_NUMBER_FIX.md",
    "PHASE1_DOCUMENT_SEARCH.md",
    "PIPELINE_ARCHITECTURE.md",
    "PROJECT_STATUS.md",
    "QUERY_COST_TRACKING_COMPLETE.md",
    "QUICKSTART.md",
    "QUICKSTART_HYBRID.md",
    "QUICKSTART_IMPROVEMENTS.md",
    "RAG_IMPROVEMENTS.md",
    "RAG_IMPROVEMENTS_IMPLEMENTED.md",
    "README_START_HERE.md",
    "REPROCESS_FEATURE.md",
    "RESUME_FEATURE_GUIDE.md",
    "SEMANTIC_SEARCH_IMPLEMENTED.md",
    "SETUP_YOUTUBE.md",
    "TESTING_CHAT_FEATURE.md",
    "WARP.md",
    "WORKFLOW_FIXES.md",
    "YOUTUBE_QUICKSTART.md",
    "YOUTUBE_SETUP_GUIDE.md",
    "YOUTUBE_VIDEO_RAG_ARCHITECTURE.md"
)

$movedDocs = 0
foreach ($doc in $docsToArchive) {
    if (Test-Path $doc) {
        Move-Item -Path $doc -Destination $archiveDocs -Force
        Write-Host "  ✓ Moved: $doc" -ForegroundColor Green
        $movedDocs++
    }
}
Write-Host ""
Write-Host "  Archived $movedDocs documentation files" -ForegroundColor Cyan

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Phase 2: Archiving Temporary Scripts" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# List of temporary scripts to archive
$scriptsToArchive = @(
    "check_docker_setup.py",
    "debug_docling.py",
    "apply-migration.sh",
    "test_api.sh",
    "test_gdrive_setup.py",
    "test_youtube.py",
    "ingest.py",
    "reingest.py",
    "app.py",
    "START_ALL.ps1",
    "TEST_SYSTEM.ps1"
)

$movedScripts = 0
foreach ($script in $scriptsToArchive) {
    if (Test-Path $script) {
        Move-Item -Path $script -Destination $archiveScripts -Force
        Write-Host "  ✓ Moved: $script" -ForegroundColor Green
        $movedScripts++
    }
}
Write-Host ""
Write-Host "  Archived $movedScripts script files" -ForegroundColor Cyan

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Phase 3: Archiving Output Directories" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# Archive output directories
$outputDirs = @("output")
$movedOutputs = 0

foreach ($dir in $outputDirs) {
    if (Test-Path $dir) {
        $items = Get-ChildItem -Path $dir -Directory
        foreach ($item in $items) {
            $destPath = Join-Path $archiveOutput $item.Name
            Move-Item -Path $item.FullName -Destination $destPath -Force
            Write-Host "  ✓ Moved: $($item.Name)" -ForegroundColor Green
            $movedOutputs++
        }
    }
}
Write-Host ""
Write-Host "  Archived $movedOutputs output directories" -ForegroundColor Cyan

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Phase 4: Archiving Old Workflow Files" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# Archive old n8n workflows
$workflowFiles = @(
    "extraction_result.json",
    "extraction_sample.json",
    "hierarchy_sample.json"
)

$movedWorkflows = 0
foreach ($file in $workflowFiles) {
    if (Test-Path $file) {
        Move-Item -Path $file -Destination $archiveOld -Force
        Write-Host "  ✓ Moved: $file" -ForegroundColor Green
        $movedWorkflows++
    }
}
Write-Host ""
Write-Host "  Archived $movedWorkflows workflow files" -ForegroundColor Cyan

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Phase 5: Removing Deleted Files from Git" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# Remove files that were marked as deleted
$deletedFiles = @(
    "api/app.py",
    "api/document_processor/__init__.py",
    "api/document_processor/adapter.py",
    "api/document_processor/core.py",
    "api/requirements.txt",
    "api/utils/__init__.py",
    "api/utils/extraction.py",
    "api/utils/processing.py",
    "api/utils/tokenization.py",
    "n8n-node/nodes/DoclingExtractor/DoclingExtractor.node.ts",
    "n8n-node/nodes/package.json",
    "n8n-node/nodes/tsconfig.json",
    "sample.pdf"
)

$removedFiles = 0
foreach ($file in $deletedFiles) {
    if (Test-Path $file) {
        Remove-Item -Path $file -Force -Recurse
        Write-Host "  ✓ Removed: $file" -ForegroundColor Green
        $removedFiles++
    }
}

# Remove empty directories
$emptyDirs = @("api", "n8n-node/nodes", "n8n-node")
foreach ($dir in $emptyDirs) {
    if (Test-Path $dir) {
        $isEmpty = (Get-ChildItem -Path $dir -Recurse -Force | Measure-Object).Count -eq 0
        if ($isEmpty) {
            Remove-Item -Path $dir -Force -Recurse
            Write-Host "  ✓ Removed empty directory: $dir" -ForegroundColor Green
            $removedFiles++
        }
    }
}
Write-Host ""
Write-Host "  Removed $removedFiles deleted files/directories" -ForegroundColor Cyan

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Phase 6: Updating Git" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

Write-Host "Staging deleted files..." -ForegroundColor Yellow
git add -u
Write-Host "  ✓ Staged deletions" -ForegroundColor Green

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "Cleanup Summary" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Documentation files archived: $movedDocs" -ForegroundColor White
Write-Host "  Script files archived: $movedScripts" -ForegroundColor White
Write-Host "  Output directories archived: $movedOutputs" -ForegroundColor White
Write-Host "  Workflow files archived: $movedWorkflows" -ForegroundColor White
Write-Host "  Files/directories removed: $removedFiles" -ForegroundColor White
Write-Host ""
Write-Host "  Archive location: ._archive/" -ForegroundColor Cyan
Write-Host "    - ._archive/docs/ (temporary documentation)" -ForegroundColor White
Write-Host "    - ._archive/scripts/ (temporary scripts)" -ForegroundColor White
Write-Host "    - ._archive/output/ (old output files)" -ForegroundColor White
Write-Host "    - ._archive/old-workflows/ (old workflow files)" -ForegroundColor White
Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host "Cleanup Complete!" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Review git status: git status" -ForegroundColor White
Write-Host "  2. Commit changes: git add . && git commit -m 'Clean up repository'" -ForegroundColor White
Write-Host "  3. Review ._archive/ directory before pushing" -ForegroundColor White
Write-Host ""
