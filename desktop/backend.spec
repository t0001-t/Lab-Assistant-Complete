from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent
staging = ROOT / 'desktop' / 'staged-application'
datas = [(str(staging), 'application')]
binaries = []
hiddenimports = ['pwa_server', 'tornado', 'uvicorn.logging', 'uvicorn.loops.auto',
                 'uvicorn.protocols.http.h11_impl', 'uvicorn.protocols.websockets.websockets_sansio_impl',
                 'uvicorn.lifespan.on']
for name in ['streamlit', 'pydantic', 'reportlab', 'docx']:
    d, b, h = collect_all(name)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += [p.stem for p in ROOT.glob('*.py') if p.name not in {'build_app.py', 'generate_icons.py', 'pwa_entrypoint.py', 'lab_assistant.py', 'app.py', 'gel_app.py'}]
datas += copy_metadata('streamlit')
hiddenimports += collect_submodules('streamlit')
a = Analysis([str(ROOT / 'desktop' / 'desktop_server.py')], pathex=[str(ROOT)],
             binaries=binaries, datas=datas, hiddenimports=hiddenimports, hookspath=[str(ROOT / "desktop" / "hooks")],
             excludes=['pytest', 'ruff', 'tkinter', 'IPython', 'matplotlib', 'scipy', 'cv2'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='LabAssistantServer',
          console=True, strip=False, upx=False, target_arch='arm64')
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='LabAssistantServer')
