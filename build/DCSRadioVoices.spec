# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: genera dist/DCSRadioVoices/ con la app de ventana y la de consola.
import os
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
datas, binaries, hidden = [], [], []
for pkg in ("kokoro_onnx", "espeakng_loader", "piper", "phonemizer", "soundfile", "onnxruntime"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hidden += h
datas += [(os.path.join(ROOT, "models"), "models"),
          (os.path.join(ROOT, "samples"), "samples"),
          (os.path.join(ROOT, "LICENSES"), "LICENSES")]
icon = os.path.join(ROOT, "build", "icon.ico")
excludes = ["tkinter", "matplotlib", "PIL", "IPython", "pytest", "PySide6.QtWebEngineCore",
            "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtMultimedia"]

a = Analysis([os.path.join(ROOT, "main.py")],
             pathex=[ROOT], binaries=binaries, datas=datas, hiddenimports=hidden,
             excludes=excludes, noarchive=False)
pyz = PYZ(a.pure)
gui = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name="DCSRadioVoices", console=False, icon=icon if os.path.exists(icon) else None,
          version=None, upx=False)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True,
          name="DCSRadioVoicesCLI", console=True, icon=icon if os.path.exists(icon) else None, upx=False)
coll = COLLECT(gui, cli, a.binaries, a.datas, strip=False, upx=False, name="DCSRadioVoices")
