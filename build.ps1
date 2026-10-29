# Gera o executavel e o arquivo .sha256 que acompanham cada Release no GitHub.
# Antes: aumente VERSAO em versao.py. Uso:  powershell -File build.ps1
Set-Location $PSScriptRoot
$nome = "Extrato Fretes Agregados"
$exe = "dist\$nome.exe"
$antes = if (Test-Path $exe) { (Get-Item $exe).LastWriteTime } else { [datetime]::MinValue }

python -m PyInstaller --noconfirm --onefile --windowed --name $nome `
    --add-data "$PSScriptRoot\config.ini;." --hidden-import openpyxl --hidden-import pythoncom `
    --hidden-import win32com.client --exclude-module matplotlib --exclude-module scipy `
    --exclude-module IPython --workpath build --specpath build --distpath dist app.py
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $exe) -or (Get-Item $exe).LastWriteTime -le $antes) {
    Write-Host "`nERRO: o build falhou; nenhum arquivo novo foi gerado." -ForegroundColor Red
    exit 1
}

$hash = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
[IO.File]::WriteAllText("$PSScriptRoot\dist\$nome.exe.sha256", "$hash  $nome.exe`n")
$versao = (Select-String -Path versao.py -Pattern 'VERSAO = "(.+)"').Matches[0].Groups[1].Value
Write-Host "`nPronto: versao $versao | SHA-256 $hash"
Write-Host "Publique em uma Release com a tag v$versao anexando os DOIS arquivos de dist\:"
Write-Host "  $nome.exe  e  $nome.exe.sha256"
