param([string]$PackageDir=$PSScriptRoot)
$ErrorActionPreference="Stop"
$resolvedPackage=(Resolve-Path -LiteralPath $PackageDir).Path
$imageTar=Join-Path $resolvedPackage "local-sensitive-filter.tar"
$checksumFile=Join-Path $resolvedPackage "SHA256SUMS.txt"
if(-not(Test-Path -LiteralPath $imageTar)){throw "Missing image file: $imageTar"}
if(-not(Test-Path -LiteralPath $checksumFile)){throw "Missing checksum file: $checksumFile"}
$expected=((Get-Content -LiteralPath $checksumFile -Raw).Trim()-split "\s+")[0]
$actual=(Get-FileHash -Algorithm SHA256 -LiteralPath $imageTar).Hash.ToLower()
if($expected-ne$actual){throw "Image checksum failed. The package may be incomplete."}
docker version|Out-Null
docker load --input $imageTar
$envFile=Join-Path $resolvedPackage ".env"
if(-not(Test-Path -LiteralPath $envFile)){
  Copy-Item -LiteralPath (Join-Path $resolvedPackage ".env.example") -Destination $envFile
  Write-Warning "Created .env. Set ADMIN_PASSWORD, then run: docker compose up -d"
  exit 0
}
docker compose --project-directory $resolvedPackage up -d
docker compose --project-directory $resolvedPackage ps
