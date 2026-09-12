; =============================================================================
; AIKA OPTIMIZER V4.1 — INNO SETUP SCRIPT
; =============================================================================
; Requer Inno Setup 6.6+ (WizardStyle=modern dark polar usa dark mode/custom
; styles, adicionados no Inno Setup 6.6). O x64compatible usados abaixo
; requerem Inno Setup 6.3+.
; Build esperado (PyInstaller onedir):
;   {#SourcePath}\dist\Aika_Optimizer_V4.1\
; Instalador gerado em:
;   {#SourcePath}\installer\
; =============================================================================

#define MyAppName "AIKA Optimizer"
#define MyAppVersion "4.1.0.0"
#define MyAppPublisher "@diegobfr07"
#define MyAppURL "https://github.com/diegobfr07/AikaOptimizer"
#define MyAppExeName "Aika_Optimizer_V4.1.exe"
; EXE legado REAL e conhecido do produto (confirmado no historico do repositorio:
; Projeto Brutal.iss da V4.0 -> MyAppExeName "Aika_Optimizer_V4.0.exe").
; Usado APENAS para encerramento por nome exato em upgrade/reinstalacao e no
; uninstall. Nunca usar wildcard (ex.: Aika*.exe).
#define MyAppExeNameLegado "Aika_Optimizer_V4.0.exe"

[Setup]
; AppId PRESERVADO da V3 — a V4 e atualizacao do mesmo produto.
AppId={{2F4C311D-A712-433E-9AA7-C03E9ABE914D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} V4.1
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
OutputBaseFilename=AIKA_Optimizer_V4.1_Setup
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
Source: "{#SourcePath}\dist\Aika_Optimizer_V4.1\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Documentacao/licencas do produto distribuido (fora do bundle PyInstaller)
Source: "{#SourcePath}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourcePath}\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

; =============================================================================
; UNINSTALL — encerra o processo do produto ANTES de remover arquivos
; =============================================================================
; CAUSA RAIZ DO BUG (processo vivo na bandeja + {app} "em uso"):
;   1. main.py -> closeEvent(): com close_to_tray ativo, WM_CLOSE vira
;      event.ignore() + esconder_para_bandeja() (hide-to-tray), ou seja, o
;      processo NAO encerra;
;   2. a diretiva CloseApplications (Windows Restart Manager) vale apenas para
;      o Setup — o uninstaller do Inno NAO usa Restart Manager;
;   3. sem ninguem encerrando o processo, {app}\Aika_Optimizer_V4.1.exe e
;      {app}\_internal\*.dll permanecem bloqueados e a pasta nao pode ser
;      removida.
;
; [UninstallRun] e executado "as the first step of uninstallation", isto e,
; ANTES de qualquer remocao de arquivo (documentacao oficial do Inno Setup,
; topico "[Run] & [UninstallRun] sections"). Somente nomes EXATOS de
; executaveis conhecidos do produto sao encerrados: nunca ha wildcard, nunca
; python.exe, nunca o cliente AIKA, nunca terceiros.
;   - /F: obrigatorio, pois o encerramento gracioso e convertido em
;         hide-to-tray pelo aplicativo;
;   - /T: garante que nao reste processo filho do proprio Optimizer;
;   - runhidden + waituntilterminated: execucao oculta e conclusao garantida
;         antes de prosseguir com o uninstall;
;   - processo ausente NAO e erro: o Inno apenas registra o codigo de saida
;         do taskkill e continua a desinstalacao.
; =============================================================================

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /T /IM ""{#MyAppExeName}"""; Flags: runhidden waituntilterminated; RunOnceId: "EncerrarAikaOptimizerV41"
Filename: "{sys}\taskkill.exe"; Parameters: "/F /T /IM ""{#MyAppExeNameLegado}"""; Flags: runhidden waituntilterminated; RunOnceId: "EncerrarAikaOptimizerV40"

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

; --- RegisteredApplications (remove apenas nossos valores: V4.1 atual e V4.0 legado) ---
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueName: "AIKA Optimizer V4.1"; ValueType: none; Flags: uninsdeletevalue dontcreatekey
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueName: "AIKA Optimizer V4.0"; ValueType: none; Flags: uninsdeletevalue dontcreatekey

; =============================================================================
; CODE — encerramento no upgrade/reinstalacao + limpeza condicional de .jit
; =============================================================================
; PrepareToInstall: encerra instancias conhecidas do produto (nomes exatos)
; ANTES de copiar/substituir arquivos. Necessario porque o fechamento via
; Restart Manager (CloseApplications=yes) pode ser convertido em
; hide-to-tray pelo aplicativo (main.py -> closeEvent + close_to_tray).
;
; CurUninstallStepChanged: o valor default de HKCU\Software\Classes\.jit so e
; removido se ainda apontar para nosso ProgID (AIKAOptimizer.JIT). Nunca
; apagamos a associacao de outro programa.

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  CodigoSaida: Integer;
begin
  Result := '';
  NeedsRestart := False;
  // Upgrade V4.0 -> V4.1 / reinstalacao: encerra o processo antigo e/ou o atual
  // pelos nomes EXATOS. Sem wildcard, sem python.exe, sem cliente AIKA.
  // Processo ausente nao e erro (o codigo de saida do taskkill e ignorado).
  Exec(
    ExpandConstant('{sys}\taskkill.exe'),
    '/F /T /IM "' + '{#MyAppExeName}' + '"',
    '', SW_HIDE, ewWaitUntilTerminated, CodigoSaida
  );
  Exec(
    ExpandConstant('{sys}\taskkill.exe'),
    '/F /T /IM "' + '{#MyAppExeNameLegado}' + '"',
    '', SW_HIDE, ewWaitUntilTerminated, CodigoSaida
  );
end;

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

