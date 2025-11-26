# Start Celery Worker
# This runs a worker locally in your working venv where Docling works perfectly

Write-Host "⚙️  Starting Celery Worker..." -ForegroundColor Cyan

# Change to backend directory
Set-Location "C:\Users\tech\Projects\docling-n8n\backend"

# Activate virtual environment
Write-Host "📦 Activating virtual environment..." -ForegroundColor Yellow
& "C:\Users\tech\Projects\docling-n8n\venv\Scripts\Activate.ps1"

# Set PYTHONPATH to include both backend and src directories
Write-Host "🔧 Setting PYTHONPATH..." -ForegroundColor Yellow
$env:PYTHONPATH = "C:\Users\tech\Projects\docling-n8n\backend;C:\Users\tech\Projects\docling-n8n\src"

# Load environment variables from .env
Write-Host "📝 Loading environment variables from .env..." -ForegroundColor Yellow
Get-Content "C:\Users\tech\Projects\docling-n8n\.env" | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') {
        $key = $matches[1]
        $value = $matches[2]
        [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
}

# Set HuggingFace cache workaround for Windows (no symlinks)
Write-Host "🔧 Setting Windows compatibility mode for HuggingFace..." -ForegroundColor Yellow
[System.Environment]::SetEnvironmentVariable('HF_HUB_DISABLE_SYMLINKS_WARNING', '1', 'Process')
[System.Environment]::SetEnvironmentVariable('HF_HUB_DISABLE_SYMLINK_CACHE', '1', 'Process')

Write-Host ""
Write-Host "✅ Worker starting..." -ForegroundColor Green
Write-Host "📡 Connecting to Redis at localhost:6379" -ForegroundColor Green
Write-Host "🔄 Concurrency: 2 (adjust based on your RAM)" -ForegroundColor Yellow
Write-Host "💡 To run multiple workers, open another terminal and run this script again" -ForegroundColor Cyan
Write-Host ""

# Start celery worker
# --pool=solo is for Windows compatibility
# --concurrency=2 means 2 documents can be processed in parallel
# Adjust --concurrency=1 if you have limited RAM (8GB)
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2 --pool=solo
