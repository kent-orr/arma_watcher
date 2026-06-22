; Arma Watcher - Inno Setup installer script
; Build with: ISCC.exe installer\arma_watcher.iss
; CI can override the version: ISCC.exe /DMyAppVersion=1.2.3 installer\arma_watcher.iss

#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif

#define MyAppName "Arma Watcher"
#define MyAppPublisher "Kent Orr"
#define MyAppURL "https://github.com/kent-orr/arma_watcher"
#define MyAppExeName "launch_gui.vbs"
#define SrcRoot ".."

[Setup]
; A unique (random) AppId. Do not change this between releases or upgrades break.
AppId={{8F4C2A91-3D6E-4B7A-9C0F-1E2D3A4B5C6D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
; Per-user install: no admin rights, no UAC prompt.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\Arma Watcher
DefaultGroupName=Arma Watcher
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir={#SrcRoot}\dist
OutputBaseFilename=ArmaWatcherSetup
SetupIconFile={#SrcRoot}\arma_watcher\assets\icon.ico
UninstallDisplayIcon={app}\arma_watcher\assets\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Arma Watcher targets 64-bit Windows.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile={#SrcRoot}\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; Python package (excluding caches / build artifacts)
Source: "{#SrcRoot}\arma_watcher\*"; DestDir: "{app}\arma_watcher"; Flags: recursesubdirs createallsubdirs ignoreversion; Excludes: "__pycache__\*,*.pyc,*.pyo"
; Project + launcher + helper scripts
Source: "{#SrcRoot}\pyproject.toml";   DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\uv.lock";          DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\.python-version";  DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\README.md";        DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\LICENSE";          DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\launch_gui.vbs";   DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\run.ps1";          DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\run.bat";          DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\update.ps1";       DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\update.bat";       DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\install.ps1";      DestDir: "{app}"; Flags: ignoreversion
Source: "{#SrcRoot}\install.bat";      DestDir: "{app}"; Flags: ignoreversion
; Post-install bootstrap (uv + Ollama + uv sync)
Source: "{#SrcRoot}\installer\bootstrap.ps1"; DestDir: "{app}\installer"; Flags: ignoreversion

[Icons]
; Launch via wscript.exe so no console window flashes (launch_gui.vbs runs the GUI hidden).
Name: "{group}\Arma Watcher"; Filename: "{win}\System32\wscript.exe"; Parameters: """{app}\launch_gui.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\arma_watcher\assets\icon.ico"; Comment: "Start Arma Watcher"
Name: "{group}\Update Arma Watcher"; Filename: "{app}\update.bat"; WorkingDir: "{app}"; IconFilename: "{app}\arma_watcher\assets\icon.ico"; Comment: "Update Arma Watcher to the latest version"
Name: "{group}\Uninstall Arma Watcher"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Arma Watcher"; Filename: "{win}\System32\wscript.exe"; Parameters: """{app}\launch_gui.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\arma_watcher\assets\icon.ico"; Comment: "Start Arma Watcher"; Tasks: desktopicon

[Run]
; Heavy lifting: install uv, Ollama, Python and sync dependencies. Shown in a
; visible console so the user can watch progress (this can take several minutes).
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installer\bootstrap.ps1"""; StatusMsg: "Installing uv, Ollama, and Python dependencies (this can take several minutes)..."; Flags: waituntilterminated

[UninstallDelete]
; Remove the isolated virtual environment and caches created at runtime.
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\arma_watcher\__pycache__"
Type: filesandordirs; Name: "{app}\arma_watcher.egg-info"
