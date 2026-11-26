; Instalador de Windows (Inno Setup 6). Lo compila GitHub Actions: iscc build\installer.iss
#define AppName "DCS Radio Voices"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{7B1E8F2A-5C3D-4E8B-9A61-2F4D9C0B7E15}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Proyecto personal
DefaultDirName={localappdata}\Programs\DCSRadioVoices
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=DCSRadioVoices-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\DCSRadioVoices.exe
Compression=lzma2/normal
SolidCompression=yes
LZMANumBlockThreads=4
DiskSpanning=no
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
ShowLanguageDialog=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\dist\DCSRadioVoices\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\DCSRadioVoices.exe"
Name: "{group}\Guion de ejemplo"; Filename: "{app}\_internal\samples"
Name: "{group}\Licencias"; Filename: "{app}\_internal\LICENSES"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\DCSRadioVoices.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\DCSRadioVoices.exe"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent
