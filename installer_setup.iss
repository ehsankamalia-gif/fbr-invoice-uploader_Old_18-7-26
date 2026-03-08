; Inno Setup Script for Ehsan Trader FBR System
; Professional Windows Installer

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
Source: "dist\EhsanTraderFBR.exe"; DestDir: "{app}"; Flags: ignoreversion
; Include other required runtime files if not using --onefile
; Source: "README.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Ehsan Trader FBR System"; Filename: "{app}\EhsanTraderFBR.exe"
Name: "{group}\{cm:UninstallProgram,Ehsan Trader FBR System}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Ehsan Trader FBR System"; Filename: "{app}\EhsanTraderFBR.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\EhsanTraderFBR.exe"; Description: "{cm:LaunchProgram,Ehsan Trader FBR System}"; Flags: nowait postinstall skipifsilent

[Code]
// Pre-installation system requirements validation
function InitializeSetup(): Boolean;
var
  ErrorCode: Integer;
begin
  Result := True;
  
  // 1. Check for sufficient disk space (e.g., 200MB)
  if GetSpaceOnDisk(ExpandConstant('{app}'), True, False) < (200 * 1024 * 1024) then
  begin
    MsgBox('Insufficient disk space. Please ensure at least 200MB is available on the target drive.', mbError, MB_OK);
    Result := False;
  end;

  // 2. Check for conflicting software (optional)
  // Example: if IsAppRunning('EhsanTraderFBR.exe') then ...
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Create Registry keys if needed for file associations
    RegWriteStringValue(HKEY_CURRENT_USER, 'Software\EhsanTrader', 'Version', '1.0.0');
  end;
end;
