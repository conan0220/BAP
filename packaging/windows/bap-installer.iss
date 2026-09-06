#define MyAppName "BAP"
#define MyAppFullName "Boxing Analysis Platform"
#define MyAppVersion "__BAP_VERSION__"
#define MyAppExeName "BAPLauncher.exe"

[Setup]
AppId={{93D88F6E-ED3A-4DB3-AB0B-4A5AA309C0BA}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppFullName} {#MyAppVersion}
AppPublisher=BAP
UninstallDisplayName={#MyAppFullName}
DefaultDirName={localappdata}\Programs\BAP
DefaultGroupName=BAP
OutputBaseFilename=BAP-Setup-{#MyAppVersion}
OutputDir=..\..\dist
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription={#MyAppFullName}

[Files]
Source: "..\..\dist\BAP\*"; DestDir: "{app}\releases\{#MyAppVersion}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\dist\BAPLauncher.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\dist\BAPUpdater.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\dist\launcher_runtime\*"; DestDir: "{app}\launcher_runtime"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\dist\updater_runtime\*"; DestDir: "{app}\updater_runtime"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{localappdata}\BAP\temp\imu-diagnostics"

[Icons]
Name: "{group}\BAP"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\BAP"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "建立桌面捷徑"; GroupDescription: "其他捷徑："; Flags: unchecked

[Run]
Filename: "{app}\BAPUpdater.exe"; Parameters: "finalize --version {#MyAppVersion} --operation-id install-{#MyAppVersion} --program-root ""{app}"" --user-data-root ""{param:BAPDATADIR|{localappdata}\BAP}"""; Flags: runhidden waituntilterminated; Check: not IsManagedUpdate
Filename: "{app}\{#MyAppExeName}"; Description: "啟動 BAP"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#MyAppExeName}"; Flags: nowait; Check: IsAutomaticUpdate

[Code]
function IsManagedUpdate: Boolean;
begin
  Result := ExpandConstant('{param:BAPMANAGED|0}') = '1';
end;

function IsAutomaticUpdate: Boolean;
begin
  Result := ExpandConstant('{param:BAPAUTOSTART|0}') = '1';
end;
