# headroom-proxy.ps1
# Launch Claude Code with FULL-TRAFFIC headroom compression (proxy mode).
#
# Difference vs the MCP server (.mcp.json):
#   - MCP mode   = on-demand. Claude chooses to call headroom_compress on big content.
#   - Proxy mode = automatic. EVERY request Claude Code sends is compressed by the
#                  local proxy before it reaches Anthropic. Zero opt-in needed.
#
# Usage (from anywhere):
#   powershell -ExecutionPolicy Bypass -File scripts\headroom-proxy.ps1
# Optional custom port:
#   ... -File scripts\headroom-proxy.ps1 -Port 8080
#
# The proxy opens in its own window so you can watch live savings. Close that
# window when you're done. ANTHROPIC_BASE_URL is set only for the Claude Code
# process this script launches — it does not change your global environment.

param(
    [int]$Port = 8787
)

$ErrorActionPreference = 'Stop'

# 1. Start the headroom proxy in a separate window (stays open to show savings).
#    --no-http2 avoids occasional TLS corruption under many cancelled streams.
Write-Host "Starting headroom proxy on port $Port..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    '-NoExit', '-Command', "headroom proxy --port $Port --no-http2"
)

# 2. Wait for the proxy to report healthy before routing Claude through it.
$healthUrl = "http://127.0.0.1:$Port/health"
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $r = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
        if ($r.ready) { $ready = $true; break }
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $ready) {
    Write-Host "Proxy did not become healthy on $healthUrl. Check the proxy window." -ForegroundColor Red
    exit 1
}
Write-Host "Proxy healthy. Launching Claude Code routed through it..." -ForegroundColor Green

# 3. Route Claude Code through the proxy for THIS launched session only.
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:$Port"
claude
