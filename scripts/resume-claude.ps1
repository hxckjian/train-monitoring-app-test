# Resume a Claude Code session from its project folder, from anywhere.
#
#   powershell -ExecutionPolicy Bypass -File scripts\resume-claude.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\resume-claude.ps1 -Path "D:\other\project" -Session <id>
#
# Claude Code keys sessions to the folder they were started in, which is why
# `claude --resume <id>` only works after `cd` into that folder. This script does both.
param(
  [string]$Path = "C:\Users\Asus\Desktop\Everything in one\NUS FYP",
  [string]$Session = "d0e7a8e3-0409-4d76-9d40-99f1321cd4fd"
)
$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $Path)) { throw "Project folder not found: $Path" }
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { throw "claude is not on PATH. Install Claude Code or open a terminal where 'claude' works." }
Set-Location -LiteralPath $Path
Write-Host "Resuming Claude session $Session in $Path"
claude --resume $Session
