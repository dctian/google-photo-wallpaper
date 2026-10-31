[CmdletBinding()]
param([Parameter(Mandatory)][string[]]$Paths, [string]$Publisher = 'SignPath Foundation')
$ErrorActionPreference = 'Stop'
foreach ($path in $Paths) {
    $signature = Get-AuthenticodeSignature -LiteralPath $path
    if ($signature.Status -ne 'Valid' -or -not $signature.TimeStamperCertificate) {
        throw "Missing valid timestamped Authenticode signature: $path"
    }
    $name = $signature.SignerCertificate.GetNameInfo([Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false)
    if ($name -ne $Publisher) { throw "Unexpected signing publisher: $name" }
    Write-Output "Verified $path ($name)."
}
