# Start FastAPI Backend API
# This runs the API server locally in your working venv

Write-Host "🚀 Starting Docling Backend API..." -ForegroundColor Cyan

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

Write-Host ""
Write-Host "✅ Backend API starting on http://localhost:8000" -ForegroundColor Green
Write-Host "📚 API Docs: http://localhost:8000/docs" -ForegroundColor Green
Write-Host "🔍 Health Check: http://localhost:8000/health" -ForegroundColor Green
Write-Host ""

# Start uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
