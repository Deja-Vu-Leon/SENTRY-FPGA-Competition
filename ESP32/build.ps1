param(
    [string]$IdfPath = 'G:/esp/v6.0.2/esp-idf',
    [string]$Port,
    [string]$BuildDirectory = 'build-local',
    [switch]$Flash
)
$ErrorActionPreference = 'Stop'
if (-not $env:IDF_PATH) {
    $env:IDF_TOOLS_PATH = 'G:/Espressif'
    $env:IDF_PYTHON_ENV_PATH = 'G:/Espressif/tools/python/v6.0.2/venv'
    $env:IDF_PYTHON_CHECK_CONSTRAINTS = 'no'
    $env:PATH = "$env:IDF_PYTHON_ENV_PATH/Scripts;$env:PATH"
    . "$IdfPath/export.ps1"
}
Push-Location $PSScriptRoot
try {
    python "$env:IDF_PATH/tools/idf.py" -B $BuildDirectory build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($Flash) {
        if (-not $Port) { throw '请使用 -Port 指定串口，例如 COM8。' }
        python "$env:IDF_PATH/tools/idf.py" -B $BuildDirectory -p $Port flash
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
} finally {
    Pop-Location
}
