# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for AI 学术写作助手
用于将前后端项目打包为单个可执行文件
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# 获取 spec 文件所在目录
spec_dir = os.path.dirname(os.path.abspath(SPEC))
app_datas = [
    # 包含前端静态文件
    ('static', 'static'),
    # 包含后端 app 目录
    ('backend/app', 'app'),
]

# 收集所需的隐式导入
hidden_imports = [
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
    'httptools',
    'websockets',
    'sqlalchemy.dialects.sqlite',
    'pydantic',
    'pydantic_settings',
    'passlib.handlers.bcrypt',
    'jose',
    'openai',
    'httpx',
    'socksio',
    'aiofiles',
    'sse_starlette',
    'redis',
    'dotenv',
    'docx',
    'lxml',
    'lxml.etree',
    'lxml._elementpath',
]

# 收集 uvicorn 和其他依赖的子模块
hidden_imports += collect_submodules('uvicorn')
hidden_imports += collect_submodules('sqlalchemy')
hidden_imports += collect_submodules('pydantic')
hidden_imports += collect_submodules('pydantic_settings')
hidden_imports += collect_submodules('fastapi')
hidden_imports += collect_submodules('starlette')
hidden_imports += collect_submodules('docx')
hidden_imports += collect_submodules('lxml')

# pkg_resources / jaraco 在 Linux 打包时才显式包含。
# Windows 下强行带入会触发 pyi_rth_pkgres，并可能在部分环境中
# 因 pyexpat / expat 运行库收集异常导致 exe 启动失败。
extra_excludes = []
if sys.platform != 'win32':
    hidden_imports += [
        'jaraco',
        'jaraco.text',
        'jaraco.functools',
        'jaraco.context',
        'pkg_resources',
        'pkg_resources.extern',
    ]
    hidden_imports += collect_submodules('jaraco')
    hidden_imports += collect_submodules('pkg_resources')
else:
    extra_excludes += [
        'jaraco',
        'jaraco.text',
        'jaraco.functools',
        'jaraco.context',
        'pkg_resources',
        'pkg_resources.extern',
        'setuptools',
    ]


extra_binaries = []
if sys.platform == 'win32':
    seen_binary_sources = set()
    candidate_roots = []
    for root in {sys.prefix, getattr(sys, 'base_prefix', sys.prefix)}:
        if root:
            candidate_roots.append(Path(root))

    candidate_dirs = []
    for root in candidate_roots:
        candidate_dirs.extend([
            root / 'Library' / 'bin',
            root / 'DLLs',
        ])

    runtime_patterns = (
        'libssl*.dll',
        'libcrypto*.dll',
        'sqlite3.dll',
        'ffi*.dll',
        'libffi*.dll',
        'libexpat*.dll',
        'libbz2*.dll',
        'liblzma*.dll',
        'vcruntime*.dll',
        'msvcp*.dll',
        'ucrt*.dll',
    )

    for candidate_dir in candidate_dirs:
        if not candidate_dir.exists():
            continue
        for pattern in runtime_patterns:
            for dll_path in candidate_dir.glob(pattern):
                source = str(dll_path.resolve())
                if source not in seen_binary_sources:
                    extra_binaries.append((source, '.'))
                    seen_binary_sources.add(source)

# 分析主入口文件
a = Analysis(
    ['main.py'],
    pathex=[spec_dir, os.path.join(spec_dir, 'backend')],
    binaries=extra_binaries,
    datas=app_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
    ] + extra_excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# 创建 PYZ 归档
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# 创建可执行文件
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AI学术写作助手',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 设置为 True 以显示控制台窗口（可以看到日志）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 可以添加图标文件路径
)
