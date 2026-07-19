param([string]$Image="local-sensitive-filter:latest",[string]$OutputRoot="releases")
$ErrorActionPreference="Stop"
$projectRoot=Split-Path -Parent $PSScriptRoot
$stamp=Get-Date -Format "yyyyMMdd-HHmmss"
$packageDir=Join-Path (Join-Path $projectRoot $OutputRoot) "sensitive-filter-$stamp"
New-Item -ItemType Directory -Path (Join-Path $packageDir "data") -Force|Out-Null
docker image inspect $Image|Out-Null
docker save --output (Join-Path $packageDir "local-sensitive-filter.tar") $Image
Copy-Item -LiteralPath (Join-Path $projectRoot "compose.yaml") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $projectRoot ".env.example") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $projectRoot "data\words.json") -Destination (Join-Path $packageDir "data\words.json")
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "import.ps1") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $projectRoot "MIGRATION.md") -Destination $packageDir
$checksum=Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $packageDir "local-sensitive-filter.tar")
"$($checksum.Hash.ToLower())  local-sensitive-filter.tar"|Set-Content -Encoding ascii -LiteralPath (Join-Path $packageDir "SHA256SUMS.txt")
Write-Output "Migration package created: $packageDir"
Write-Output "Image SHA256: $($checksum.Hash.ToLower())"
