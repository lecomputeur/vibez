param(
  [string]$OutputDirectory = ""
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$repoRoot = (Resolve-Path (Join-Path $projectRoot '..')).Path
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) { $OutputDirectory = Join-Path $projectRoot 'artifacts\windows' }

$config = Get-Content (Join-Path $projectRoot 'src-tauri\tauri.conf.json') -Raw | ConvertFrom-Json
$match = [regex]::Match([string]$config.version, '^(\d+)\.(\d+)\.(\d+)')
if (-not $match.Success) { throw "Invalid preview version: $($config.version)" }
$msixVersion = '{0}.{1}.{2}.0' -f $match.Groups[1].Value,$match.Groups[2].Value,$match.Groups[3].Value
$exe = Join-Path $projectRoot 'src-tauri\target\release\vibez3.exe'
if (-not (Test-Path $exe)) { throw "Windows preview executable missing: $exe" }

$stage = Join-Path $projectRoot 'artifacts\store-staging'
$assets = Join-Path $stage 'Assets'
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $stage,$assets,$OutputDirectory -Force | Out-Null
Copy-Item $exe (Join-Path $stage 'vibez3.exe')

$sourceIcon = Join-Path $repoRoot 'build\icons\icon_512x512.png'
Add-Type -AssemblyName System.Drawing
$image = [System.Drawing.Image]::FromFile($sourceIcon)
try {
  function Logo([int]$w,[int]$h,[string]$name) {
    $bmp = New-Object System.Drawing.Bitmap($w,$h,[System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    try {
      $g.Clear([System.Drawing.Color]::Transparent)
      $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
      $s = [Math]::Floor([Math]::Min($w,$h)*0.82)
      $g.DrawImage($image,[Math]::Floor(($w-$s)/2),[Math]::Floor(($h-$s)/2),$s,$s)
      $bmp.Save((Join-Path $assets $name),[System.Drawing.Imaging.ImageFormat]::Png)
    } finally { $g.Dispose(); $bmp.Dispose() }
  }
  Logo 50 50 'StoreLogo.png'; Logo 44 44 'Square44x44Logo.png'; Logo 150 150 'Square150x150Logo.png'; Logo 310 150 'Wide310x150Logo.png'; Logo 310 310 'Square310x310Logo.png'
} finally { $image.Dispose() }

$manifest = @"
<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
 xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
 xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
 IgnorableNamespaces="uap rescap">
 <Identity Name="LeComputeur.VibeZDesktop" Publisher="CN=613EFBB1-83C3-495D-9C3B-D4EE98C72B95" Version="$msixVersion" ProcessorArchitecture="x64" />
 <Properties>
  <DisplayName>VibeZ 3</DisplayName>
  <PublisherDisplayName>Le Computeur</PublisherDisplayName>
  <Description>VibeZ 3 desktop client for Mistral Vibe.</Description>
  <Logo>Assets\StoreLogo.png</Logo>
 </Properties>
 <Dependencies><TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.26100.0" /></Dependencies>
 <Resources><Resource Language="en-us" /><Resource Language="nl-nl" /></Resources>
 <Applications>
  <Application Id="VibeZDesktop" Executable="vibez3.exe" EntryPoint="Windows.FullTrustApplication">
   <uap:VisualElements DisplayName="VibeZ 3"
    Description="VibeZ 3 desktop client for Mistral Vibe."
    BackgroundColor="transparent" Square150x150Logo="Assets\Square150x150Logo.png" Square44x44Logo="Assets\Square44x44Logo.png">
    <uap:DefaultTile Wide310x150Logo="Assets\Wide310x150Logo.png" Square310x310Logo="Assets\Square310x310Logo.png" ShortName="VibeZ 3" />
   </uap:VisualElements>
  </Application>
 </Applications>
 <Capabilities><Capability Name="internetClient" /><rescap:Capability Name="runFullTrust" /></Capabilities>
</Package>
"@
Set-Content -Path (Join-Path $stage 'AppxManifest.xml') -Value $manifest -Encoding utf8

$makeAppx = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Filter makeappx.exe -Recurse |
  Where-Object { $_.FullName -match '\\x64\\makeappx\.exe$' } | Select-Object -Last 1
if (-not $makeAppx) { throw 'makeappx.exe not found' }

$out = Join-Path $OutputDirectory "VibeZ-$($config.version)-Windows-x64-Store.msix"
& $makeAppx.FullName pack /d $stage /p $out /o
if ($LASTEXITCODE -ne 0) { throw "makeappx failed: $LASTEXITCODE" }

$verify = Join-Path $projectRoot 'artifacts\store-verify'
Remove-Item $verify -Recurse -Force -ErrorAction SilentlyContinue
& $makeAppx.FullName unpack /p $out /d $verify /o
if ($LASTEXITCODE -ne 0) { throw "MSIX verification failed: $LASTEXITCODE" }
[xml]$packed = Get-Content (Join-Path $verify 'AppxManifest.xml') -Raw
if ($packed.Package.Identity.Name -ne 'LeComputeur.VibeZDesktop') { throw 'Preview identity mismatch' }
# Package creation is not Store submission.
if ($packed.Package.Identity.Version -ne $msixVersion) { throw 'Version mismatch' }
Write-Output $out
