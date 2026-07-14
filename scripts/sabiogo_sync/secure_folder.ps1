param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [string]$AdministratorName = 'Administrador'
)

$ErrorActionPreference = 'Stop'

$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($currentIdentity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Abrir Simbolo del sistema como administrador.'
}

$root = (Resolve-Path -LiteralPath $Path).Path
$administratorSid = (
    [Security.Principal.NTAccount]::new($env:COMPUTERNAME, $AdministratorName)
).Translate([Security.Principal.SecurityIdentifier])
$systemSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$allowedSids = @($administratorSid.Value, $systemSid.Value)
if ($currentIdentity.User.Value -ne $administratorSid.Value) {
    throw "Ejecutar este script con la cuenta local $AdministratorName."
}
$fullControl = [Security.AccessControl.FileSystemRights]::FullControl
$inheritance = (
    [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
    [Security.AccessControl.InheritanceFlags]::ObjectInherit
)
$noPropagation = [Security.AccessControl.PropagationFlags]::None
$allow = [Security.AccessControl.AccessControlType]::Allow

$rootAcl = [Security.AccessControl.DirectorySecurity]::new()
$rootAcl.SetOwner($administratorSid)
$rootAcl.SetAccessRuleProtection($true, $false)
$rootAcl.AddAccessRule(([Security.AccessControl.FileSystemAccessRule]::new(
    $administratorSid, $fullControl, $inheritance, $noPropagation, $allow
)))
$rootAcl.AddAccessRule(([Security.AccessControl.FileSystemAccessRule]::new(
    $systemSid, $fullControl, $inheritance, $noPropagation, $allow
)))
Set-Acl -LiteralPath $root -AclObject $rootAcl

$items = Get-ChildItem -LiteralPath $root -Force -Recurse |
    Sort-Object { $_.FullName.Length }
foreach ($item in $items) {
    $acl = Get-Acl -LiteralPath $item.FullName
    $acl.SetAccessRuleProtection($false, $false)
    foreach ($rule in @($acl.Access | Where-Object { -not $_.IsInherited })) {
        [void]$acl.RemoveAccessRuleSpecific($rule)
    }
    Set-Acl -LiteralPath $item.FullName -AclObject $acl
}

function Assert-AllowedRules {
    param(
        [string]$ItemPath,
        [System.Security.AccessControl.FileSystemSecurity]$Acl,
        [bool]$RootItem
    )

    $rules = @($Acl.Access)
    if ($rules.Count -ne 2) {
        throw "$ItemPath debe tener exactamente dos reglas de acceso."
    }

    $seen = @{}
    foreach ($rule in $rules) {
        $sid = $rule.IdentityReference.Translate(
            [Security.Principal.SecurityIdentifier]
        ).Value
        if ($sid -notin $allowedSids -or $seen.ContainsKey($sid)) {
            throw "Identidad inesperada o duplicada en ${ItemPath}: $sid"
        }
        if ($rule.AccessControlType -ne $allow -or $rule.FileSystemRights -ne $fullControl) {
            throw "Regla sin FullControl permitido en ${ItemPath}: $sid"
        }
        if ($RootItem) {
            if ($rule.IsInherited -or $rule.InheritanceFlags -ne $inheritance -or
                $rule.PropagationFlags -ne $noPropagation) {
                throw "Regla raiz invalida en ${ItemPath}: $sid"
            }
        } elseif (-not $rule.IsInherited) {
            throw "Regla explicita inesperada en ${ItemPath}: $sid"
        }
        $seen[$sid] = $true
    }
}

$verifiedRootAcl = Get-Acl -LiteralPath $root
if (-not $verifiedRootAcl.AreAccessRulesProtected) {
    throw 'La carpeta raiz debe tener herencia deshabilitada.'
}
Assert-AllowedRules -ItemPath $root -Acl $verifiedRootAcl -RootItem $true

foreach ($item in Get-ChildItem -LiteralPath $root -Force -Recurse) {
    $acl = Get-Acl -LiteralPath $item.FullName
    if ($acl.AreAccessRulesProtected) {
        throw "La herencia debe estar habilitada en $($item.FullName)."
    }
    Assert-AllowedRules -ItemPath $item.FullName -Acl $acl -RootItem $false
}

Write-Output '[OK] ACL verificada: solamente Administrador y SYSTEM con FullControl.'