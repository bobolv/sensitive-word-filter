param(
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
Set-Location -LiteralPath $projectRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is not installed or is not available in PATH."
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is not installed or is not available in PATH."
}

$currentBranch = (git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "The current directory is not a Git repository: $projectRoot"
}
if ($currentBranch -ne $Branch) {
    throw "Current branch is '$currentBranch'. Switch to '$Branch' before deploying."
}

$trackedChanges = git status --porcelain --untracked-files=no
if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect the Git working tree."
}
if ($trackedChanges) {
    throw "Tracked files contain local changes. Commit or back them up before deploying."
}

Write-Host "Pulling origin/$Branch..."
git pull --ff-only origin $Branch
if ($LASTEXITCODE -ne 0) {
    throw "Git pull failed."
}

$envFile = Join-Path $projectRoot ".env"
if (-not (Test-Path -LiteralPath $envFile)) {
    Copy-Item -LiteralPath (Join-Path $projectRoot ".env.example") -Destination $envFile
    throw "Created .env. Set ADMIN_PASSWORD in it, then run this script again."
}

$wordsFile = Join-Path $projectRoot "data\words.json"
if (-not (Test-Path -LiteralPath $wordsFile)) {
    Copy-Item -LiteralPath (Join-Path $projectRoot "data\words.example.json") -Destination $wordsFile
    Write-Warning "Created data\words.json from the example dictionary. Review it after deployment."
}

Write-Host "Validating Docker Compose configuration..."
docker compose config --quiet
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose configuration validation failed."
}

Write-Host "Rebuilding the image..."
docker compose build --pull
if ($LASTEXITCODE -ne 0) {
    throw "Docker image build failed."
}

Write-Host "Deploying the rebuilt container..."
docker compose up -d --force-recreate
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose deployment failed."
}

docker compose ps
Write-Host "Deployment completed. Existing data\words.json was preserved."
