"""Active / désactive le lancement du bot au démarrage de Windows (sans fenêtre)."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "discord-viewer.vbs"


def vbs_content(root: Path, python: str) -> str:
    # Fenêtre cachée (0) ; la sortie va dans viewer.log, réécrit à chaque démarrage.
    cmd = f'cmd /c cd /d "{root}" && "{python}" -u viewer\\bot.py > viewer.log 2>&1'
    return 'CreateObject("WScript.Shell").Run "' + cmd.replace('"', '""') + '", 0\r\n'


def main():
    if os.name != "nt":
        raise SystemExit("Uniquement pour Windows.")
    vbs = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup" / NAME
    if vbs.exists():
        vbs.unlink()
        print("Démarrage automatique DÉSACTIVÉ.")
        print("Si le bot tourne encore en arrière-plan : taskkill /IM python.exe /F")
        return
    if not (ROOT / ".env").exists():
        raise SystemExit("Crée d'abord le fichier .env (voir .env.example).")
    vbs.write_text(vbs_content(ROOT, sys.executable), encoding="utf-8")
    subprocess.Popen(["wscript", str(vbs)])  # lance le bot tout de suite
    print("Démarrage automatique ACTIVÉ : le bot tourne maintenant en arrière-plan")
    print("et se relancera à chaque démarrage de Windows.")
    print("Erreurs éventuelles : fichier viewer.log. Relance ce fichier pour désactiver.")


if __name__ == "__main__":
    main()
