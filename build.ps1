param([string]$Python='python')
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
& $Python -m unittest discover -v
if($LASTEXITCODE -ne 0){throw 'Fallaron las pruebas'}
& $Python -m PyInstaller --noconfirm --clean --onefile --noconsole --name BPower-Calificador --exclude-module PIL --exclude-module numpy --exclude-module cryptography --collect-all pypdf app.py
if($LASTEXITCODE -ne 0){throw 'Falló la compilación de la app'}
& $Python -m PyInstaller --noconfirm --clean --onefile --noconsole --name BPower-Calificador-Instalador --add-data 'dist/BPower-Calificador.exe;.' --add-data 'licenses;licenses' installer.py
if($LASTEXITCODE -ne 0){throw 'Falló la compilación del instalador'}
Get-FileHash dist/BPower-Calificador*.exe -Algorithm SHA256
