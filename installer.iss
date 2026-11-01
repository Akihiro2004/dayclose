#ifndef AppVersion
#define AppVersion "1.0.0"
#endif

[Setup]
AppId={{20E87304-B8CB-46D9-957D-CF5A88A972F9}
AppName=Dayclose
AppVersion={#AppVersion}
AppPublisher=Dayclose
AppComments=Local reminders before shutting down your computer.
DefaultDirName={localappdata}\Programs\Dayclose
DefaultGroupName=Dayclose
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
UninstallDisplayIcon={app}\Dayclose.exe
UninstallDisplayName=Dayclose
SetupIconFile=assets\dayclose.ico
OutputDir=release
OutputBaseFilename=Dayclose-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=no
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Dayclose Installer

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcuts"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Files]
Source: "dist\Dayclose.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "RELEASING.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "THIRD-PARTY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "app.py"; DestDir: "{app}\source"; Flags: ignoreversion
Source: "core.py"; DestDir: "{app}\source"; Flags: ignoreversion
Source: "appearance.py"; DestDir: "{app}\source"; Flags: ignoreversion
Source: "updater.py"; DestDir: "{app}\source"; Flags: ignoreversion
Source: "version.py"; DestDir: "{app}\source"; Flags: ignoreversion
Source: "release_meta.py"; DestDir: "{app}\source"; Flags: ignoreversion
Source: "UpdateHelper.cs"; DestDir: "{app}\source"; Flags: ignoreversion
Source: "assets\dayclose.ico"; DestDir: "{app}\source\assets"; Flags: ignoreversion
Source: "requirements.txt"; DestDir: "{app}\source"; Flags: ignoreversion

[Icons]
Name: "{group}\Dayclose"; Filename: "{app}\Dayclose.exe"; AppUserModelID: "Dayclose.Desktop"
Name: "{group}\Review & Shut Down"; Filename: "{app}\Dayclose.exe"; Parameters: "--shutdown"; AppUserModelID: "Dayclose.Desktop"
Name: "{group}\Uninstall Dayclose"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Dayclose"; Filename: "{app}\Dayclose.exe"; Tasks: desktopicon; AppUserModelID: "Dayclose.Desktop"
Name: "{autodesktop}\Review & Shut Down"; Filename: "{app}\Dayclose.exe"; Parameters: "--shutdown"; Tasks: desktopicon; AppUserModelID: "Dayclose.Desktop"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\Dayclose.exe"; ValueType: string; ValueData: "{app}\Dayclose.exe"; Flags: uninsdeletekey

[Run]
Filename: "{app}\Dayclose.exe"; Description: "Open Dayclose"; Flags: nowait postinstall skipifsilent

; Reminder data is outside the install folder and deliberately survives uninstall.
