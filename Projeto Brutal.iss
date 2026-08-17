; =============================================================================
; AIKA OPTIMIZER V4.0 — INNO SETUP SCRIPT
; =============================================================================
; Build esperado (PyInstaller onedir):
;   {#SourcePath}\dist\Aika_Optimizer_V4.0\
; Instalador gerado em:
;   {#SourcePath}\installer\
; =============================================================================

#define MyAppName "AIKA Optimizer"
#define MyAppVersion "4.0.0.0"
#define MyAppPublisher "@diegobfr07"
#define MyAppURL "https://github.com/diegobfr07/AikaOptimizer"
#define MyAppExeName "Aika_Optimizer_V4.0.exe"

[Setup]
; AppId PRESERVADO da V3 — a V4 e atualizacao do mesmo produto.
AppId={{2F4C311D-A712-433E-9AA7-C03E9ABE914D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} V4.0
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
PrivilegesRequired=admin
MinVersion=10.0
OutputDir={#SourcePath}\installer
OutputBaseFilename=AIKA_Optimizer_V4.0_Setup
SetupIconFile={#SourcePath}\icone.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern dark polar
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Pasta completa do build onedir (gerado pelo PyInstaller)
Source: "{#SourcePath}\dist\Aika_Optimizer_V4.0\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

; =============================================================================
; INSTALL — limpeza de resquicios da V3 ANTES de copiar a V4
; =============================================================================
[InstallDelete]
; Remove executavel antigo se existir (atualizacao V3 -> V4)
Type: files; Name: "{app}\Aika_Optimizer_V3.0.exe"
; Remove runtime antigo (substituido pelo novo _internal da V4)
Type: filesandordirs; Name: "{app}\_internal"

; =============================================================================
; REGISTRY — cleanup somente no uninstall
; =============================================================================
; Cada entrada usa uninsdeletevalue (remove UM valor) ou uninsdeletekey
; (remove a chave inteira com subchaves, somente quando a arvore e
; exclusivamente nossa). NADA e criado na instalacao.
; =============================================================================

[Registry]
; --- Startup com Windows (remove apenas nosso valor) ---
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "AIKA_Optimizer"; ValueType: none; Flags: uninsdeletevalue dontcreatekey

; --- ProgID JIT (arvore exclusivamente nossa) ---
Root: HKCU; Subkey: "Software\Classes\AIKAOptimizer.JIT"; ValueType: none; Flags: uninsdeletekey dontcreatekey

; --- Verbo DDS de injecao (arvore exclusivamente nossa) ---
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.dds\shell\AIKAOptimizer.Inject"; ValueType: none; Flags: uninsdeletekey dontcreatekey

; --- Capabilities (arvore exclusivamente nossa) ---
Root: HKCU; Subkey: "Software\AIKAOptimizer\Capabilities"; ValueType: none; Flags: uninsdeletekey dontcreatekey

; --- OpenWithProgids (remove apenas nosso valor) ---
Root: HKCU; Subkey: "Software\Classes\.jit\OpenWithProgids"; ValueName: "AIKAOptimizer.JIT"; ValueType: none; Flags: uninsdeletevalue dontcreatekey

; --- RegisteredApplications (remove apenas nosso valor) ---
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueName: "AIKA Optimizer V4.0"; ValueType: none; Flags: uninsdeletevalue dontcreatekey

; =============================================================================
; CODE — limpeza condicional do default de .jit
; =============================================================================
; O valor default de HKCU\Software\Classes\.jit so e removido se ainda
; apontar para nosso ProgID (AIKAOptimizer.JIT). Nunca apagamos a
; associacao de outro programa.

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DefaultValue: string;
begin
  if CurUninstallStep = usUninstall then
  begin
    if RegQueryStringValue(
      HKEY_CURRENT_USER,
      'Software\Classes\.jit',
      '',
      DefaultValue
    ) and (CompareText(DefaultValue, 'AIKAOptimizer.JIT') = 0) then
    begin
      RegDeleteValue(
        HKEY_CURRENT_USER,
        'Software\Classes\.jit',
        ''
      );
    end;
  end;
end;

// NOTA: config.json do usuario em %LOCALAPPDATA%\AIKA Optimizer\
// NAO e removido — preferencias do usuario sao preservadas.
//
// Backups do jogo (AikaOptimizer_Backups) tambem NAO sao tocados.

