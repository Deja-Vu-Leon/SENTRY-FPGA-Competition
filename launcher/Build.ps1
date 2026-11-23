param([string]$Output = (Join-Path (Split-Path $PSScriptRoot) '一键烧录并启动.exe'))
$ErrorActionPreference = 'Stop'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$source = Join-Path $PSScriptRoot 'Launcher.cs'
$workflow = Join-Path $PSScriptRoot 'FlashAndStart.ps1'
$compilerArgs = @('/nologo','/target:winexe','/platform:anycpu','/optimize+','/codepage:65001',
    '/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll',
    "/resource:$workflow,FlashAndStart.ps1",
    "/out:$Output",$source)
& $compiler @compilerArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
