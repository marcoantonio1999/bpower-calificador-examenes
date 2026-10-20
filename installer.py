import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import sys

VERSION='1.0.0'
PAYLOAD=Path(__file__).resolve().parent/'BPower-Calificador.exe'


def install(folder,payload=PAYLOAD):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    target=folder/f'BPower-Calificador-{VERSION}.exe'
    temp=folder/f'BPower-Calificador-{VERSION}.instalando'
    shutil.copyfile(payload,temp)
    with temp.open('r+b') as handle:os.fsync(handle.fileno())
    os.replace(temp,target)
    licenses=Path(__file__).resolve().parent/'licenses'
    if licenses.exists():shutil.copytree(licenses,folder/'licenses',dirs_exist_ok=True)
    return target


def shortcuts(target):
    script=r'''
    $ErrorActionPreference='Stop'
    $shell=New-Object -ComObject WScript.Shell
    foreach($place in @([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('Programs'))){
      $link=$shell.CreateShortcut((Join-Path $place 'BPower Calificador de examenes.lnk'))
      $link.TargetPath=$env:BPOWER_EXAM_APP
      $link.WorkingDirectory=$env:BPOWER_EXAM_FOLDER
      $link.Description='Calificar PDF de examenes y generar Excel'
      $link.Save()
    }
    '''
    subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
       env={**os.environ,'BPOWER_EXAM_APP':str(target),'BPOWER_EXAM_FOLDER':str(target.parent)},
       capture_output=True,timeout=30,check=True,creationflags=subprocess.CREATE_NO_WINDOW)


def main():
    box=ctypes.windll.user32.MessageBoxW
    folder=Path(os.environ['LOCALAPPDATA'])/'BPower-Calificador-Examenes'
    if box(None,f'Instalar BPower Calificador de exámenes {VERSION}\n\nSólo para tu usuario:\n{folder}\n\nNo requiere Python. No incluye ninguna API key. Es independiente de las apps de candidatos.\n\n¿Continuar?','Instalar BPower Calificador',0x24)!=6:return
    try:target=install(folder);shortcuts(target)
    except Exception:
        box(None,'No se completó la instalación. Revisa permisos y espacio disponible. No se modificaron tus exámenes.','Instalación incompleta',0x10);return
    box(None,'Instalación terminada. Abre «BPower Calificador de examenes» desde el escritorio o Inicio.','BPower Calificador',0x40)


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--self-test':
        assert PAYLOAD.stat().st_size>1_000_000 and PAYLOAD.open('rb').read(2)==b'MZ'
        Path(sys.argv[2]).write_text('OK '+VERSION,encoding='utf-8')
    else:main()
