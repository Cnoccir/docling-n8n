# Start React Frontend Dashboard
# This runs the Vite dev server for the React UI

Write-Host "🎨 Starting Docling Dashboard Frontend..." -ForegroundColor Cyan

# Change to frontend directory
Set-Location "C:\Users\tech\Projects\docling-n8n\frontend"

# Check if node_modules exists
if (-not (Test-Path "node_modules")) {
    Write-Host "📦 Installing dependencies (first time setup)..." -ForegroundColor Yellow
    npm install
}

Write-Host ""
Write-Host "✅ Frontend starting..." -ForegroundColor Green
Write-Host "🌐 Dashboard UI: http://localhost:3000" -ForegroundColor Green
Write-Host "🔗 Connected to Backend: http://localhost:8000" -ForegroundColor Yellow
Write-Host ""
Write-Host "💡 Make sure the Backend API is running (see backend/start_api.ps1)" -ForegroundColor Cyan
Write-Host ""

# Start Vite dev server
npm run dev
