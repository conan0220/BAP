#define MyAppName "BAP"
#define MyAppFullName "Boxing Analysis Platform"
#define MyAppVersion "0.1.0"
#define MyAppExeName "BAP.exe"

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
Source: "..\..\dist\BAP\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\BAP"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\BAP"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "建立桌面捷徑"; GroupDescription: "其他捷徑："; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "啟動 BAP"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\BAP\temp\imu-diagnostics"
