# Gera o executavel e o arquivo .sha256 que acompanham cada Release no GitHub.
# Antes: aumente __version__ em src\robo_agregado\__init__.py.
# Uso:  powershell -File build.ps1 [-Python <caminho do python>]
param([string]$Python)
Set-Location $PSScriptRoot
if (-not $Python) {
    $venv = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    $Python = if (Test-Path $venv) { $venv } else { "python" }
}
$nome = "RoboAgregado"
$exe = "dist\$nome.exe"
$antes = if (Test-Path $exe) { (Get-Item $exe).LastWriteTime } else { [datetime]::MinValue }

& $Python -m PyInstaller --noconfirm --onefile --windowed --name $nome `
    --collect-data tcm_ui --collect-data robo_agregado `
    --hidden-import openpyxl --hidden-import pythoncom --hidden-import win32com.client `
    --hidden-import msal --hidden-import msal_extensions `
    --exclude-module matplotlib --exclude-module scipy --exclude-module IPython --exclude-module tkinter `
    --workpath build --specpath build --distpath dist main.py
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $exe) -or (Get-Item $exe).LastWriteTime -le $antes) {
    Write-Host "`nERRO: o build falhou; nenhum arquivo novo foi gerado." -ForegroundColor Red
    exit 1
}

$hash = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
[IO.File]::WriteAllText("$PSScriptRoot\dist\$nome.exe.sha256", "$hash  $nome.exe`n")
$versao = (Select-String -Path src\robo_agregado\__init__.py -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
Write-Host "`nPronto: versao $versao | SHA-256 $hash"
Write-Host "Publique em uma Release com a tag v$versao anexando os DOIS arquivos de dist\:"
Write-Host "  $nome.exe  e  $nome.exe.sha256"
