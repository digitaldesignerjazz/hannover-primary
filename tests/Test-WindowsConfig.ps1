# Dot-sources the Windows helper and checks the JSON it would write.
$ErrorActionPreference = 'Stop'
if (-not $env:ProgramFiles) { $env:ProgramFiles = '/tmp/ygg-program-files' }
if (-not $env:ProgramData) { $env:ProgramData = '/tmp/ygg-program-data' }
$env:YGG_IMPORT_ONLY = '1'

$repo = Split-Path -Parent $PSScriptRoot
. (Join-Path $repo 'windows/Install-YggdrasilNode.ps1')

$overlay = Read-NodeOverlay
$peers = Read-PeerUriList -Path (Join-Path $repo 'config/peers.txt')
$identity = @{ PrivateKey = ('ab' * 64) }
$json = ConvertTo-WindowsNodeConfig -Overlay $overlay -Peers $peers -Identity $identity
$doc = $json | ConvertFrom-Json

if ($doc.NodeInfo.name -ne 'hannover-primary') { throw 'name' }
if ($doc.NodeInfo.location -ne 'Hannover/DE') { throw 'location' }
if ($doc.AdminListen -ne 'tcp://localhost:9001') { throw 'admin' }
if ($doc.IfName -ne 'Yggdrasil') { throw 'ifname' }
if ($doc.PrivateKey -ne ('ab' * 64)) { throw 'key' }
if (@($doc.Peers).Count -lt 1) { throw 'peers' }
if ($json -notmatch '"Peers": \[') { throw 'peers were not encoded as an array' }

$inside = Join-Path $repo 'yggdrasil.conf'
$refused = $false
try {
    Confirm-ConfigOutsideRepository -Path $inside
}
catch {
    $refused = $true
}
if (-not $refused) { throw 'repo path was accepted' }

Write-Output 'WINDOWS_CONFIG_OK'
