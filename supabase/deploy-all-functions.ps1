# Deploy All Supabase Edge Functions
# Windows PowerShell script for deploying Phase 2 RAG functions

Write-Host "🚀 Deploying Supabase Edge Functions for RAG Pipeline" -ForegroundColor Cyan
Write-Host "=" * 60

# Check if Supabase CLI is installed
$supabaseVersion = & supabase --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Supabase CLI not found. Install with: scoop install supabase" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Supabase CLI: $supabaseVersion" -ForegroundColor Green

# Verify project is linked
Write-Host "`n📋 Checking project link..." -ForegroundColor Yellow
$projectStatus = & supabase projects list 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Not linked to a Supabase project" -ForegroundColor Red
    Write-Host "   Run: supabase link --project-ref YOUR_PROJECT_REF" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ Project linked successfully" -ForegroundColor Green

# List of functions to deploy
$functions = @(
    "hybrid-search",
    "search-keyword",
    "retrieve-with-images",
    "retrieve-with-tables",
    "context-expansion"
)

Write-Host "`n🔧 Deploying $($functions.Count) edge functions..." -ForegroundColor Cyan

$successCount = 0
$failCount = 0

foreach ($func in $functions) {
    Write-Host "`n  📦 Deploying: $func" -ForegroundColor Yellow
    
    $deployOutput = & supabase functions deploy $func 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✅ $func deployed successfully" -ForegroundColor Green
        $successCount++
    } else {
        Write-Host "  ❌ $func deployment failed" -ForegroundColor Red
        Write-Host "     $deployOutput" -ForegroundColor Gray
        $failCount++
    }
}

# Summary
Write-Host "`n" + ("=" * 60)
Write-Host "📊 Deployment Summary" -ForegroundColor Cyan
Write-Host "  ✅ Success: $successCount" -ForegroundColor Green
Write-Host "  ❌ Failed:  $failCount" -ForegroundColor Red

if ($failCount -eq 0) {
    Write-Host "`n🎉 All functions deployed successfully!" -ForegroundColor Green
    Write-Host "`n📝 Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Set secrets: supabase secrets set OPENAI_API_KEY=sk-..." -ForegroundColor Yellow
    Write-Host "  2. Apply FTS migration: migrations/002_add_fts_indexes.sql" -ForegroundColor Yellow
    Write-Host "  3. Update n8n workflow with new tool URLs" -ForegroundColor Yellow
    Write-Host "  4. Test functions with docs/SUPABASE_EDGE_FUNCTIONS.md" -ForegroundColor Yellow
} else {
    Write-Host "`n⚠️  Some functions failed to deploy. Check errors above." -ForegroundColor Yellow
    exit 1
}

Write-Host "`n✨ Done!" -ForegroundColor Cyan
