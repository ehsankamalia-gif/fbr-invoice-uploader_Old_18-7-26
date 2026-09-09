; Inno Setup Script for Ehsan Trader FBR System
; Build the application first:  python build_exe.py
; Then compile this script with Inno Setup to produce installer_output\EhsanTraderFBR_Setup.exe

[Setup]
AppId={{EHSAN-TRADER-FBR-SYSTEM-2026}}
AppName=Ehsan Trader FBR System
AppVersion=1.0.0
AppPublisher=Ehsan Trader
DefaultDirName={autopf}\EhsanTraderFBR
DefaultGroupName=Ehsan Trader
OutputDir=installer_output
OutputBaseFilename=EhsanTraderFBR_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
LicenseFile=LICENSE.txt
SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\EhsanTraderFBR.exe
ArchitecturesInstallIn64BitMode=x64
DisableProgramGroupPage=yes
DisableDirPage=no
AlwaysShowDirOnReadyPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Ships the whole PyInstaller onedir output, including bundled configuration
; (capture_config.json, .env.example, assets) that the app seeds on first run.
Source: "dist\EhsanTraderFBR\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Ehsan Trader FBR System"; Filename: "{app}\EhsanTraderFBR.exe"
Name: "{group}\{cm:UninstallProgram,Ehsan Trader FBR System}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Ehsan Trader FBR System"; Filename: "{app}\EhsanTraderFBR.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\EhsanTraderFBR.exe"; Description: "{cm:LaunchProgram,Ehsan Trader FBR System}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Deliberately does NOT remove %APPDATA%\EhsanTraderFBR: it holds the user's
; configuration and, on machines without MySQL, the SQLite database.

[Code]
function MySqlServerDetected(): Boolean;
begin
  Result := DirExists('C:\laragon\bin\mysql')
         or DirExists('C:\xampp\mysql')
         or DirExists(ExpandConstant('{sd}\laragon\bin\mysql'))
         or DirExists(ExpandConstant('{sd}\xampp\mysql'))
         or DirExists(ExpandConstant('{pf}\MySQL'));
end;

function InitializeSetup(): Boolean;
begin
  Result := True;

  if GetSpaceOnDisk64(ExpandConstant('{sd}\'), True, False) < Int64(600) * 1024 * 1024 then
  begin
    MsgBox('Insufficient disk space. Please ensure at least 600 MB is available.', mbError, MB_OK);
    Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    RegWriteStringValue(HKEY_LOCAL_MACHINE, 'Software\EhsanTrader', 'Version', '1.0.0');
    RegWriteStringValue(HKEY_LOCAL_MACHINE, 'Software\EhsanTrader', 'InstallPath', ExpandConstant('{app}'));

    if MySqlServerDetected() then
      MsgBox('A MySQL server (Laragon/XAMPP) was detected.' #13#10#13#10
             'The application will connect to it on first start and create its'
             ' database and tables automatically.' #13#10#13#10
             'Please make sure the MySQL service is running before opening the application.',
             mbInformation, MB_OK)
    else
      MsgBox('No MySQL server (Laragon/XAMPP) was detected on this computer.' #13#10#13#10
             'The application will run using a built-in local database, stored in'
             ' your user profile. No further setup is required.' #13#10#13#10
             'If you install Laragon or XAMPP later, the application will use it'
             ' automatically the next time it starts.',
             mbInformation, MB_OK);
  end;
end;
