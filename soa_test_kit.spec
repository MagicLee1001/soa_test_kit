# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files
block_cipher = None

add_files = [
                ('.\\remote_job.exe','.'),
                ('.\\settings.yaml','.'),
                ('.\\ui\\icons\\*', 'ui\\icons'),
                ('.\\data\\case\\debug\\*', 'data\\case\\debug'),
                ('.\\data\\case\\xpp\\*', 'data\\case\\xpp'),
                ('.\\data\\key\\*', 'data\\key'),
                ('.\\data\\matrix\\*', 'data\\matrix'),
                ('.\\data\\result', 'data\\result'),
                ('.\\data\\log', 'data\\log'),
                ('.\\data\\conf\\*', 'data\\conf'),
                ('.\\protocol\\lidds130\\*', 'protocol\\lidds130'),
                ('.\\protocol\\rtidds\\rticonnextdds-connector\\lib\\win-x64\\*', 'rticonnextdds-connector\\lib\\win-x64'),
             ]

a = Analysis(['soa_test_kit.py'],
             pathex=[],
             binaries=[],
             datas=add_files,
             hiddenimports=[],
             hookspath=[],
             hooksconfig={},
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts, 
          [],
          exclude_binaries=True,
          name='soa_test_kit',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False,
          disable_windowed_traceback=False,
          target_arch=None,
          codesign_identity=None,
          entitlements_file=None , icon='ui\\icons\\icon.ico')
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas, 
               strip=False,
               upx=True,
               upx_exclude=[],
               name='soa_test_kit')
