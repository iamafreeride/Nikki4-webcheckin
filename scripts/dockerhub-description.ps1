<#
.SYNOPSIS
    Push this repo's README to Docker Hub as the repository description (with icon).

.DESCRIPTION
    Docker Hub cannot read the README from GitHub for a normal repository, so the
    page ends up empty.  This script logs in with an Access Token and PATCHes both
    the short description and the full markdown description, which is where the
    project icon lives.

    Create the token at: https://hub.docker.com/settings/security  (Read & Write)

.EXAMPLE
    ./scripts/dockerhub-description.ps1 -Username iamafreeride -Token dckr_pat_xxx
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Username,
    [Parameter(Mandatory = $true)][string]$Token,
    [string]$Repository = "nikki4-webcheckin",
    [string]$ShortDescription = "Daily check-in and reward redemption for the Nikki4 (閃耀暖暖) web event"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$readme = Join-Path $root "README.md"

if (-not (Test-Path -LiteralPath $readme)) { throw "README.md not found at $readme" }
$body = [IO.File]::ReadAllText($readme, [Text.Encoding]::UTF8)

Write-Host "==> Logging in as $Username" -ForegroundColor Cyan
$login = @{ username = $Username; password = $Token } | ConvertTo-Json -Compress
$payloadFile = Join-Path $env:TEMP "dh-login.json"
[IO.File]::WriteAllText($payloadFile, $login)
$loginResponse = curl.exe -sS -X POST "https://hub.docker.com/v2/users/login" `
    -H "Content-Type: application/json" --data "@$payloadFile"
Remove-Item $payloadFile -ErrorAction SilentlyContinue

$jwt = ($loginResponse | ConvertFrom-Json).token
if (-not $jwt) { throw "Login failed: $loginResponse" }

Write-Host "==> Updating $Username/$Repository" -ForegroundColor Cyan
$patch = @{ description = $ShortDescription; full_description = $body } | ConvertTo-Json -Compress
$patchFile = Join-Path $env:TEMP "dh-patch.json"
[IO.File]::WriteAllText($patchFile, $patch, [Text.UTF8Encoding]::new($false))

$result = curl.exe -sS -X PATCH "https://hub.docker.com/v2/repositories/$Username/$Repository/" `
    -H "Authorization: JWT $jwt" -H "Content-Type: application/json" --data "@$patchFile" -w "`nHTTP %{http_code}"
Remove-Item $patchFile -ErrorAction SilentlyContinue

Write-Host $result
Write-Host "==> Done: https://hub.docker.com/r/$Username/$Repository" -ForegroundColor Green
