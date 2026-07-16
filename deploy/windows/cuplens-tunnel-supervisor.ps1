param(
    [Parameter(Mandatory = $true)]
    [string]$IdentityFile,

    [Parameter(Mandatory = $true)]
    [string]$RemoteHost,

    [int]$RemotePort = 18080,

    [int]$LocalPort = 18080,

    [int]$RetrySeconds = 5
)

$ErrorActionPreference = "Continue"
$sshExecutable = Join-Path $env:WINDIR "System32\OpenSSH\ssh.exe"

$sshArguments = @(
    "-N",
    "-F", "NUL",
    "-i", $IdentityFile,
    "-p", "22",
    "-o", "IdentitiesOnly=yes",
    "-o", "BatchMode=yes",
    "-o", "ExitOnForwardFailure=yes",
    "-o", "ServerAliveInterval=15",
    "-o", "ServerAliveCountMax=3",
    "-o", "TCPKeepAlive=yes",
    "-R", "127.0.0.1:${RemotePort}:127.0.0.1:${LocalPort}",
    $RemoteHost
)

while ($true) {
    & $sshExecutable @sshArguments
    Start-Sleep -Seconds $RetrySeconds
}
