[Setup]
AppName=DODNI Portföy Yönetimi
AppVersion=1.2
DefaultDirName={localappdata}\Programs\DODNI Portfoy Yonetimi
DefaultGroupName=DODNI Portföy Yönetimi
PrivilegesRequired=lowest
SetupIconFile=dodni.ico
UninstallDisplayIcon={app}\dodni.exe
InfoBeforeFile=yasal_uyari.txt
OutputDir=Kurulum_Ciktisi
OutputBaseFilename=DODNI_Portfoy_Yonetimi_Kurulum_v1.2
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "Masaüstüne kısayol oluştur"; GroupDescription: "Ek simgeler:"

[Files]
Source: "dist\dodni\*"; DestDir: "{app}"; Excludes: "data\*"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\DODNI Portföy Yönetimi"; Filename: "{app}\dodni.exe"; IconFilename: "{app}\dodni.exe"
Name: "{userdesktop}\DODNI Portföy Yönetimi"; Filename: "{app}\dodni.exe"; IconFilename: "{app}\dodni.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\dodni.exe"; Description: "DODNI Portföy Yönetimi uygulamasını şimdi çalıştır"; Flags: nowait postinstall skipifsilent