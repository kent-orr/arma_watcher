; Arma Watcher - Inno Setup installer script
; Build with: ISCC.exe installer\arma_watcher.iss
; CI can override the version: ISCC.exe /DMyAppVersion=1.2.3 installer\arma_watcher.iss

#ifndef MyAppVersion
  #define MyAppVersion "0.1.3"
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

; Note: the heavy lifting (uv, Ollama, Python deps, model pull) is run from the
; [Code] section below on a custom wizard page, with a hidden PowerShell process
; whose output is tailed live into an in-wizard log box. This replaces the old
; visible console window so nothing scary pops up outside the installer.

[UninstallDelete]
; Remove the isolated virtual environment and caches created at runtime.
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\arma_watcher\__pycache__"
Type: filesandordirs; Name: "{app}\arma_watcher.egg-info"

[Code]
const
  EM_SCROLLCARET = $00B7;  { SW_HIDE is already a built-in Inno constant }

function SendMessage(Wnd: HWND; Msg, WParam, LParam: Longint): Longint;
  external 'SendMessageW@user32.dll stdcall';

var
  ModelPage: TInputOptionWizardPage;
  LogPage: TWizardPage;
  LogMemo: TNewMemo;
  ModelTags: array[0..4] of String;
  BootstrapStarted: Boolean;

procedure InitializeWizard;
begin
  // Order must match the radio buttons added below; 'none' = skip the download.
  ModelTags[0] := 'qwen3.5:0.8b';
  ModelTags[1] := 'qwen3.5:2b';
  ModelTags[2] := 'qwen3.5:4b';
  ModelTags[3] := 'qwen3.5:9b';
  ModelTags[4] := 'none';

  ModelPage := CreateInputOptionPage(wpSelectTasks,
    'Choose a vision model',
    'Arma Watcher reads your screen with a local AI model.',
    'Pick the model to download during setup. Bigger models are more accurate but'
    + ' need more video memory (VRAM). You can change this later inside the app.',
    True, False);
  ModelPage.Add('qwen3.5:0.8b   -   ~1.0 GB VRAM   (fastest, least accurate)');
  ModelPage.Add('qwen3.5:2b     -   ~2.7 GB VRAM');
  ModelPage.Add('qwen3.5:4b     -   ~3.4 GB VRAM');
  ModelPage.Add('qwen3.5:9b     -   ~6.6 GB VRAM   (recommended)');
  ModelPage.Add('Don''t download a model now  -  I''ll choose one later in the app');
  ModelPage.SelectedValueIndex := 3;

  // Custom page shown right after the file-copy step, where the bootstrap runs
  // and streams its output into a read-only memo.
  LogPage := CreateCustomPage(wpInstalling,
    'Setting up Arma Watcher',
    'Installing uv, Ollama, Python dependencies and your model.'
    + ' This can take several minutes - hang tight.');

  LogMemo := TNewMemo.Create(WizardForm);
  LogMemo.Parent := LogPage.Surface;
  LogMemo.SetBounds(0, 0, LogPage.SurfaceWidth, LogPage.SurfaceHeight);
  LogMemo.ScrollBars := ssVertical;
  LogMemo.ReadOnly := True;
  LogMemo.WordWrap := False;
  LogMemo.Font.Name := 'Consolas';
  LogMemo.Font.Size := 9;
end;

function GetSelectedModel: String;
begin
  Result := ModelTags[ModelPage.SelectedValueIndex];
end;

// Pull any lines the bootstrap has written since we last looked into the memo.
procedure AppendNewLines(var Shown: Integer);
var
  Lines: TArrayOfString;
  i: Integer;
begin
  if LoadStringsFromFile(ExpandConstant('{tmp}\aw_bootstrap.log'), Lines) then
  begin
    if GetArrayLength(Lines) > Shown then
    begin
      for i := Shown to GetArrayLength(Lines) - 1 do
        LogMemo.Lines.Add(Lines[i]);
      Shown := GetArrayLength(Lines);
      SendMessage(LogMemo.Handle, EM_SCROLLCARET, 0, 0);
      LogMemo.Update;
    end;
  end;
end;

procedure RunBootstrap;
var
  LogFile, DoneFile, Params: String;
  DoneText: AnsiString;
  ResultCode, Shown: Integer;
begin
  LogFile  := ExpandConstant('{tmp}\aw_bootstrap.log');
  DoneFile := ExpandConstant('{tmp}\aw_bootstrap.done');
  DeleteFile(LogFile);
  DeleteFile(DoneFile);
  SaveStringToFile(LogFile, '', False);

  // Run PowerShell hidden, then unconditionally (&) drop a sentinel file with its
  // exit code so we know when (and whether) it finished even though we don't wait
  // on it. /V:ON + !ERRORLEVEL! forces delayed expansion, otherwise cmd would
  // bake in the errorlevel from before PowerShell even runs (always 0).
  Params := '/V:ON /C powershell.exe -NoProfile -ExecutionPolicy Bypass -File "'
    + ExpandConstant('{app}\installer\bootstrap.ps1')
    + '" -Model "' + GetSelectedModel + '" -LogFile "' + LogFile
    + '" & echo DONE:!ERRORLEVEL!>"' + DoneFile + '"';

  WizardForm.BackButton.Enabled := False;
  WizardForm.NextButton.Enabled := False;
  WizardForm.CancelButton.Enabled := False;

  if not Exec(ExpandConstant('{cmd}'), Params, '', SW_HIDE, ewNoWait, ResultCode) then
  begin
    LogMemo.Lines.Add('ERROR: could not start the setup process.');
    WizardForm.NextButton.Enabled := True;
    WizardForm.CancelButton.Enabled := True;
    Exit;
  end;

  Shown := 0;
  repeat
    AppendNewLines(Shown);
    WizardForm.Update;
    Sleep(250);
  until FileExists(DoneFile);

  // The bootstrap may still be flushing its last lines when the sentinel lands.
  Sleep(250);
  AppendNewLines(Shown);

  DoneText := '';
  LoadStringFromFile(DoneFile, DoneText);
  if Pos('DONE:0', DoneText) = 0 then
  begin
    LogMemo.Lines.Add('');
    LogMemo.Lines.Add('Setup hit a problem. You can close this and re-run the installer,');
    LogMemo.Lines.Add('or open the install folder and run install.bat manually.');
    SendMessage(LogMemo.Handle, EM_SCROLLCARET, 0, 0);
  end;

  WizardForm.NextButton.Enabled := True;
  WizardForm.CancelButton.Enabled := True;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  // Kick off the (one-time) bootstrap as soon as the log page is shown.
  if (CurPageID = LogPage.ID) and (not BootstrapStarted) then
  begin
    BootstrapStarted := True;
    RunBootstrap;
  end;
end;
