#!/usr/bin/env pwsh
# ===========================================================================
# mlauto.ps1 - single entry point to manage the automation_machine_learning stack
# (Docker: backend FastAPI :8000 + frontend nginx :5173) on Windows / PowerShell.
#
# Inspired by the recette.sh dispatcher pattern (mo0ogly/recette_IA_agents).
#
#   .\mlauto.ps1 up            # build if needed + start, wait until healthy
#   .\mlauto.ps1 down          # stop and remove containers
#   .\mlauto.ps1 restart       # restart both services
#   .\mlauto.ps1 build         # build images
#   .\mlauto.ps1 rebuild       # build --no-cache + restart
#   .\mlauto.ps1 logs [svc]    # follow logs (optionally one service)
#   .\mlauto.ps1 ps            # container status
#   .\mlauto.ps1 status        # status + health snapshot
#   .\mlauto.ps1 health        # probe backend /health + frontend
#   .\mlauto.ps1 shell [svc]   # open a shell in a service (default: backend)
#   .\mlauto.ps1 test          # run the backend test-suite inside the container
#   .\mlauto.ps1 clean         # stop + remove the session volume (DESTRUCTIVE)
#   .\mlauto.ps1 help
#
# Author: Fabrice Pizzi
# ===========================================================================
[CmdletBinding()]
param(
    [Parameter(Position = 0)] [string]$Command = 'help',
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)] [string[]]$Rest
)
$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Write-Hdr  { param([string]$m) Write-Host "`n== $m ==" -ForegroundColor Cyan }
function Write-Info { param([string]$m) Write-Host $m -ForegroundColor Green }
function Write-Warn { param([string]$m) Write-Host $m -ForegroundColor Yellow }
function Write-Err  { param([string]$m) Write-Host $m -ForegroundColor Red }

# --- docker compose (v2 preferred, v1 fallback) ------------------------------
$script:DCexe = 'docker'; $script:DCargs = @('compose')
& docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
        $script:DCexe = 'docker-compose'; $script:DCargs = @()
    } else {
        Write-Err "Docker Compose introuvable. Installez Docker Desktop / le plugin compose."
        exit 1
    }
}
function DC { & $script:DCexe @($script:DCargs + $args) }

# --- host ports (mirror .env so messages match what's published) -------------
$BackendPort = '8000'; $FrontendPort = '5173'
if (Test-Path .env) {
    $lines = Get-Content .env
    $bp = ($lines | Where-Object { $_ -match '^BACKEND_PORT=' }  | Select-Object -Last 1)
    $fp = ($lines | Where-Object { $_ -match '^FRONTEND_PORT=' } | Select-Object -Last 1)
    if ($bp) { $BackendPort  = $bp.Split('=', 2)[1].Trim() }
    if ($fp) { $FrontendPort = $fp.Split('=', 2)[1].Trim() }
}

function Require-Daemon {
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Le demon Docker ne repond pas - demarrez Docker Desktop puis reessayez."
        exit 1
    }
}

function Show-Urls {
    Write-Info "Frontend : http://localhost:$FrontendPort"
    Write-Info "Backend  : http://localhost:$BackendPort  (sante : /health)"
}

function Test-Url {
    param([string]$Url)
    try { Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 3 *> $null; return $true }
    catch { return $false }
}

function Wait-Healthy {
    Write-Host -NoNewline "Attente du backend "
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-Url "http://localhost:$BackendPort/health") { Write-Host " OK" -ForegroundColor Green; return }
        Write-Host -NoNewline "."; Start-Sleep -Seconds 2
    }
    Write-Warn " (pas encore pret - voir '.\mlauto.ps1 logs')"
}

function Invoke-Health {
    $b = Test-Url "http://localhost:$BackendPort/health"
    $f = Test-Url "http://localhost:$FrontendPort/"
    Write-Host ("  backend  (:{0}) : " -f $BackendPort)  -NoNewline; if ($b) { Write-Info 'UP' } else { Write-Warn 'DOWN' }
    Write-Host ("  frontend (:{0}) : " -f $FrontendPort) -NoNewline; if ($f) { Write-Info 'UP' } else { Write-Warn 'DOWN' }
    return $b
}

switch ($Command) {
    { $_ -in 'up', 'start' } {
        Require-Daemon; Write-Hdr "Demarrage de la stack (build si necessaire)"
        DC up -d --build; Wait-Healthy; Show-Urls
    }
    { $_ -in 'down', 'stop' } { Require-Daemon; Write-Hdr "Arret"; DC down }
    'restart' { Require-Daemon; Write-Hdr "Redemarrage"; DC restart; Wait-Healthy; Show-Urls }
    'build'   { Require-Daemon; Write-Hdr "Build des images"; DC build }
    'rebuild' {
        Require-Daemon; Write-Hdr "Rebuild complet (--no-cache)"
        DC build --no-cache; DC up -d; Wait-Healthy; Show-Urls
    }
    'logs'   { Require-Daemon; DC logs -f --tail=120 @Rest }
    'ps'     { Require-Daemon; DC ps }
    'status' { Require-Daemon; Write-Hdr "Conteneurs"; DC ps; Write-Hdr "Sante"; [void](Invoke-Health) }
    'health' { [void](Invoke-Health) }
    'shell' {
        Require-Daemon
        $svc = if ($Rest -and $Rest.Count -ge 1) { $Rest[0] } else { 'backend' }
        Write-Hdr "Shell dans '$svc' (exit pour sortir)"; DC exec $svc sh
    }
    'test' {
        Require-Daemon; Write-Hdr "Tests backend (dans le conteneur)"
        DC exec -T backend python -m pytest tests/test_api.py -q
    }
    'clean' {
        Require-Daemon
        Write-Warn "Ceci arrete la stack ET supprime le volume des sessions (sessions.db perdues)."
        $ans = Read-Host "Confirmer ? [y/N]"
        if ($ans -match '^(y|o)') { DC down -v --remove-orphans; Write-Info "Volume supprime." }
        else { Write-Info "Annule." }
    }
    default {
        # Print the header usage block (lines 4..23).
        Get-Content $PSCommandPath | Select-Object -Skip 3 -First 20 | ForEach-Object { $_ -replace '^#\s?', '' }
    }
}
