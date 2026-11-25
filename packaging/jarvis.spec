# PyInstaller recipe for the Jarvis app. Made by Nur Al Mahtab.
# Build with: python packaging/build.py
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
datas, binaries, hiddenimports = [], [], []

# packages that carry data files, models or native libraries
for pkg in ("faster_whisper", "ctranslate2", "onnxruntime", "openwakeword", "piper", "sounddevice",
            "comtypes", "pycaw", "tokenizers", "av", "huggingface_hub", "onnx_asr", "tzdata"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception as e:                      # optional packages may be absent
        print("collect_all skipped", pkg, e)
# the Windows Runtime bindings are many small namespace packages
hiddenimports += collect_submodules("winrt")
hiddenimports += ["win32com", "win32com.client", "pythoncom", "pywintypes"]

datas += [
    (os.path.join(ROOT, "app", "ui", "qml"), os.path.join("app", "ui", "qml")),
    (os.path.join(ROOT, "models", "piper"), os.path.join("models", "piper")),
    (os.path.join(ROOT, "LICENSE"), "."),
    (os.path.join(ROOT, "README.md"), "."),
]

EXCLUDES = ["tkinter", "matplotlib", "pytest", "IPython", "notebook",
            "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
            "PySide6.QtWebSockets", "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
            "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras", "PySide6.QtCharts", "PySide6.QtDataVisualization",
            "PySide6.QtQuick3D", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSql", "PySide6.QtBluetooth",
            "PySide6.QtNfc", "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtLocation", "PySide6.QtPositioning",
            "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSpatialAudio", "PySide6.QtTest", "PySide6.QtDesigner",
            "PySide6.QtHelp", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtTextToSpeech"]

a = Analysis([os.path.join(ROOT, "run.py")], pathex=[ROOT], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, excludes=EXCLUDES, noarchive=False)
# Qt ships many parts this app never uses (a whole web browser engine, PDF, 3D, charts...). Drop them: ~450 MB saved.
DROP = ("Qt6WebEngine", "QtWebEngine", "qtwebengine", "Qt6Pdf", "Qt63D", "Qt6Quick3D", "Qt6Charts", "Qt6DataVisualization",
        "Qt6Graphs", "opengl32sw", "Qt6Designer", "PySide6/translations", r"PySide6\translations")
a.binaries = [b for b in a.binaries if not any(d in b[0] or d in b[1] for d in DROP)]
a.datas = [d for d in a.datas if not any(x in d[0] or x in d[1] for x in DROP)]

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Jarvis", console=False,
          icon=os.path.join(SPECPATH, "jarvis.ico"), version=os.path.join(SPECPATH, "version_info.txt"))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Jarvis")
