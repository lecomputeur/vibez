param(
  [string]$OutputDirectory = "",
  [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repoRoot

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
  $OutputDirectory = Join-Path $repoRoot 'dist\store'
}

$package = Get-Content (Join-Path $repoRoot 'package.json') -Raw | ConvertFrom-Json
$match = [regex]::Match([string]$package.version, '^(\d+)\.(\d+)\.(\d+)')
if (-not $match.Success) {
  throw "Package version '$($package.version)' cannot be converted to a four-part MSIX version."
}

$msixVersion = '{0}.{1}.{2}.0' -f $match.Groups[1].Value, $match.Groups[2].Value, $match.Groups[3].Value
$executableName = "$($package.build.executableName).exe"
$payloadDirectory = Join-Path $repoRoot 'dist\win-unpacked'
$stagingDirectory = Join-Path $repoRoot 'dist\store-staging'
$assetsDirectory = Join-Path $stagingDirectory 'Assets'

if (-not $SkipBuild) {
  $env:CSC_IDENTITY_AUTO_DISCOVERY = 'false'
  & npx electron-builder --win dir --x64 --publish never
  if ($LASTEXITCODE -ne 0) { throw "electron-builder failed with exit code $LASTEXITCODE." }
}

if (-not (Test-Path (Join-Path $payloadDirectory $executableName))) {
  throw "Packaged executable not found: $payloadDirectory\$executableName"
}

if (Test-Path $stagingDirectory) { Remove-Item $stagingDirectory -Recurse -Force }
if (Test-Path $OutputDirectory) { Remove-Item $OutputDirectory -Recurse -Force }
New-Item -ItemType Directory -Path $stagingDirectory, $assetsDirectory, $OutputDirectory -Force | Out-Null
Copy-Item (Join-Path $payloadDirectory '*') $stagingDirectory -Recurse -Force

$sourceIcon = Join-Path $repoRoot 'build\icons\icon_512x512.png'
Add-Type -AssemblyName System.Drawing
$sourceImage = [System.Drawing.Image]::FromFile($sourceIcon)
try {
  function Write-Logo([int]$width, [int]$height, [string]$name) {
    $bitmap = New-Object System.Drawing.Bitmap($width, $height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
      $graphics.Clear([System.Drawing.Color]::Transparent)
      $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
      $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
      $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
      $logoSize = [Math]::Floor([Math]::Min($width, $height) * 0.82)
      $x = [Math]::Floor(($width - $logoSize) / 2)
      $y = [Math]::Floor(($height - $logoSize) / 2)
      $graphics.DrawImage($sourceImage, $x, $y, $logoSize, $logoSize)
      $bitmap.Save((Join-Path $assetsDirectory $name), [System.Drawing.Imaging.ImageFormat]::Png)
    } finally {
      $graphics.Dispose()
      $bitmap.Dispose()
    }
  }

  Write-Logo 50 50 'StoreLogo.png'
  Write-Logo 44 44 'Square44x44Logo.png'
  Write-Logo 150 150 'Square150x150Logo.png'
  Write-Logo 310 150 'Wide310x150Logo.png'
  Write-Logo 310 310 'Square310x310Logo.png'
} finally {
  $sourceImage.Dispose()
}

$manifest = @"
<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:desktop="http://schemas.microsoft.com/appx/manifest/desktop/windows10"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap desktop rescap">
  <Identity
    Name="LeComputeur.VibeZDesktop"
    Publisher="CN=613EFBB1-83C3-495D-9C3B-D4EE98C72B95"
    Version="$msixVersion"
    ProcessorArchitecture="x64" />
  <Properties>
    <DisplayName>VibeZ Desktop</DisplayName>
    <PublisherDisplayName>Le Computeur</PublisherDisplayName>
    <Description>A cross-platform desktop client for Mistral Vibe.</Description>
    <Logo>Assets\StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.26100.0" />
  </Dependencies>
  <Resources>
    <Resource Language="en-us" />
    <Resource Language="nl-nl" />
  </Resources>
  <Applications>
    <Application Id="VibeZDesktop" Executable="$executableName" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements
        DisplayName="VibeZ Desktop"
        Description="A cross-platform desktop client for Mistral Vibe."
        BackgroundColor="transparent"
        Square150x150Logo="Assets\Square150x150Logo.png"
        Square44x44Logo="Assets\Square44x44Logo.png">
        <uap:DefaultTile
          Wide310x150Logo="Assets\Wide310x150Logo.png"
          Square310x310Logo="Assets\Square310x310Logo.png"
          ShortName="VibeZ" />
      </uap:VisualElements>
      <Extensions>
        <uap:Extension Category="windows.protocol">
          <uap:Protocol Name="vibez">
            <uap:DisplayName>VibeZ</uap:DisplayName>
          </uap:Protocol>
        </uap:Extension>
        <desktop:Extension Category="windows.startupTask" Executable="$executableName" EntryPoint="Windows.FullTrustApplication">
          <desktop:StartupTask TaskId="VibeZStartupTask" Enabled="false" DisplayName="VibeZ Desktop" />
        </desktop:Extension>
      </Extensions>
    </Application>
  </Applications>
  <Capabilities>
    <Capability Name="internetClient" />
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"@

$manifestPath = Join-Path $stagingDirectory 'AppxManifest.xml'
Set-Content -Path $manifestPath -Value $manifest -Encoding utf8

$makeAppx = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Filter makeappx.exe -Recurse |
  Where-Object { $_.FullName -match '\\x64\\makeappx\.exe$' } |
  Sort-Object { try { [version]$_.Directory.Parent.Name } catch { [version]'0.0' } } -Descending |
  Select-Object -First 1
if (-not $makeAppx) { throw 'makeappx.exe was not found in the Windows SDK.' }

$artifactName = "VibeZ-$($package.version)-Windows-x64-Microsoft-Store.msix"
$artifactPath = Join-Path $OutputDirectory $artifactName
& $makeAppx.FullName pack /d $stagingDirectory /p $artifactPath /o
if ($LASTEXITCODE -ne 0) { throw "makeappx.exe failed with exit code $LASTEXITCODE." }

$verifyDirectory = Join-Path $repoRoot 'dist\store-verify'
if (Test-Path $verifyDirectory) { Remove-Item $verifyDirectory -Recurse -Force }
& $makeAppx.FullName unpack /p $artifactPath /d $verifyDirectory /o
if ($LASTEXITCODE -ne 0) { throw "MSIX unpack verification failed with exit code $LASTEXITCODE." }

[xml]$packedManifest = Get-Content (Join-Path $verifyDirectory 'AppxManifest.xml') -Raw
$identity = $packedManifest.Package.Identity
if ($identity.Name -ne 'LeComputeur.VibeZDesktop') { throw "Unexpected MSIX identity name: $($identity.Name)" }
if ($identity.Publisher -ne 'CN=613EFBB1-83C3-495D-9C3B-D4EE98C72B95') { throw "Unexpected MSIX publisher: $($identity.Publisher)" }
if ($identity.Version -ne $msixVersion) { throw "Unexpected MSIX version: $($identity.Version)" }
if (-not (Test-Path (Join-Path $verifyDirectory $executableName))) { throw 'The packaged VibeZ executable is missing from the MSIX.' }

Write-Output $artifactPath
