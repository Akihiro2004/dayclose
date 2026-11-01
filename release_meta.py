"""Generate Windows version resources from the app's single version source."""
from pathlib import Path
import re
import sys
from version import APP_VERSION


def write_metadata():
    if not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', APP_VERSION):
        raise ValueError('APP_VERSION must be MAJOR.MINOR.PATCH.')
    parts = tuple(int(part) for part in APP_VERSION.split('.')) + (0,)
    if any(part > 65535 for part in parts):
        raise ValueError('Windows version components must be at most 65535.')
    text = f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={parts!r}, prodvers={parts!r}, mask=0x3f,
    flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'Dayclose'),
    StringStruct('FileDescription', 'Dayclose - Reminder Manager'),
    StringStruct('FileVersion', '{APP_VERSION}'),
    StringStruct('InternalName', 'Dayclose'),
    StringStruct('OriginalFilename', 'Dayclose.exe'),
    StringStruct('ProductName', 'Dayclose'),
    StringStruct('ProductVersion', '{APP_VERSION}')
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
'''
    Path(__file__).with_name('version-info.txt').write_text(text, encoding='utf-8', newline='\n')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] != 'v' + APP_VERSION:
        raise SystemExit('The Git tag must match APP_VERSION in version.py.')
    write_metadata()
