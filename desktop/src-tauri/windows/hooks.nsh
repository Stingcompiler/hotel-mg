; Sky Towers installer hooks (spec §11), included by the Tauri NSIS template.
;   install:   config.json once (no question; the default owner account is created on first start) → ACLs on %ProgramData%\SkyTowers → Defender exclusion
;              → Windows service «SkyTowersServer» (auto start, restart on failure or error) → start → wait until it answers
;   upgrade:   stop the service; copy the database files to backups\pre-upgrade-<version>-<time> (checked; the newest 3
;              kept) and keep the previous server as server.prev; the database is updated by the installer itself
;              (upgrade-db) and, if that fails, the copy and the previous server are put back (review 2026-09-29, E-4…E-7)
;   uninstall: stop and remove the service, remove the Defender exclusions; %ProgramData%\SkyTowers (database,
;              backups, keys) is never deleted

!define SKYT_SERVICE "SkyTowersServer"
!define SKYT_EXE "$INSTDIR\server\skytowers-server.exe"
; $APPDATA is C:\ProgramData under SetShellVarContext all (every hook sets it first). NSIS has no $COMMONAPPDATA: up
; to 1.1.8 that name stayed literal text, so the pre-upgrade copy, the ACLs and the data exclusion never applied.
!define SKYT_DATA "$APPDATA\SkyTowers"
; Oldest WebView2 the interface is tested with (CSS logical properties, :has, color-mix); E-10.
!define SKYT_MIN_WEBVIEW2 "111.0.1661.41"

Var SkytPre   ; the pre-upgrade copy of this run ("" on a first install)
Var SkytPrev  ; 1 when the previous server was kept as server.prev

!macro SKYT_STOP_SERVICE
  ; No automatic restart while files are replaced or the service removed: the recovery actions (set again after
  ; install, or by .onInstFailed) would bring an ended build back within 5 s and it would lock its files.
  nsExec::Exec 'sc failure ${SKYT_SERVICE} reset= 0 actions= ""'
  Pop $0
  nsExec::Exec 'sc stop ${SKYT_SERVICE}'
  Pop $0
  ; 1.0.5 and later stop at once; older builds could hang while the app window was connected: end the process
  ; after a short wait (SQLite keeps every committed write). Nothing to end is not an error.
  Sleep 3000
  nsExec::Exec 'taskkill /F /IM skytowers-server.exe'
  Pop $0
  Sleep 500
!macroend

!macro SKYT_START_SERVICE
  nsExec::Exec 'sc failure ${SKYT_SERVICE} reset= 86400 actions= restart/5000/restart/5000/restart/30000'
  Pop $0
  nsExec::Exec 'sc failureflag ${SKYT_SERVICE} 1'
  Pop $0
  nsExec::Exec 'sc start ${SKYT_SERVICE}'
  Pop $0
!macroend

; An install that stops half way (a cancelled «close the app» question, a failed copy) must not leave the hotel
; without its server: put the previous build back and start it (E-6).
Function .onInstFailed
  SetShellVarContext all
  ${If} $SkytPrev == 1
  ${AndIfNot} ${FileExists} "${SKYT_EXE}"
    Rename "$INSTDIR\server.prev" "$INSTDIR\server"
  ${EndIf}
  !insertmacro SKYT_START_SERVICE
FunctionEnd

!macro NSIS_HOOK_PREINSTALL
  SetShellVarContext all
  StrCpy $SkytPre ""
  StrCpy $SkytPrev 0
  IfFileExists "${SKYT_EXE}" 0 skyt_stopped
    DetailPrint "إيقاف خادم البرنامج قبل التحديث…"
    !insertmacro SKYT_STOP_SERVICE
  skyt_stopped:

  ; WebView2 older than the interface needs: the bundled offline runtime updates it (no internet needed, E-10).
  !if "${INSTALLWEBVIEW2MODE}" == "offlineInstaller"
    ReadRegStr $1 HKLM "SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\${WEBVIEW2APPGUID}" "pv"
    ${If} $1 == ""
      ReadRegStr $1 HKLM "SOFTWARE\Microsoft\EdgeUpdate\Clients\${WEBVIEW2APPGUID}" "pv"
    ${EndIf}
    ${If} $1 != ""
      ${VersionCompare} "${SKYT_MIN_WEBVIEW2}" "$1" $2
      ${If} $2 = 1
        DetailPrint "تحديث مكوّن WebView2…"
        File "/oname=$TEMP\MicrosoftEdgeWebView2RuntimeInstaller.exe" "${WEBVIEW2INSTALLERPATH}"
        ExecWait '"$TEMP\MicrosoftEdgeWebView2RuntimeInstaller.exe" /silent /install' $2
        Delete "$TEMP\MicrosoftEdgeWebView2RuntimeInstaller.exe"
      ${EndIf}
    ${EndIf}
  !endif

  ; The database files themselves, before the new build updates them — on every path, including «إزالة الإصدار
  ; الحالي ثم التثبيت» where the old uninstaller already ran. Plain file copies: no program has to open the key.
  ; A new folder per run (a reinstall no longer overwrites the copy of the first attempt), checked (E-7).
  IfFileExists "${SKYT_DATA}\data\hotel.db" 0 skyt_no_db
    DetailPrint "حفظ نسخة من قاعدة البيانات قبل التحديث…"
    ${GetTime} "" "L" $1 $2 $3 $4 $5 $6 $7
    StrCpy $SkytPre "${SKYT_DATA}\backups\pre-upgrade-${VERSION}-$3$2$1-$5$6$7"
    ClearErrors
    CreateDirectory "$SkytPre"
    CopyFiles /SILENT "${SKYT_DATA}\data\hotel.db*" "$SkytPre"
    IfErrors 0 skyt_copied
      MessageBox MB_ICONSTOP "تعذّر حفظ نسخة من قاعدة البيانات قبل التحديث (قد يكون القرص ممتلئًا).$\r$\nلم يُغيَّر شيء؛ أفرغ مساحة على القرص ثم أعد تشغيل المثبِّت." /SD IDOK
      Abort
    skyt_copied:
    ; The newest three copies stay; older ones are removed (every copy is a whole database).
    nsExec::Exec 'powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath $\'${SKYT_DATA}\backups$\' -Directory -Filter pre-upgrade-* | Sort-Object CreationTime -Descending | Select-Object -Skip 3 | Remove-Item -Recurse -Force"'
    Pop $0
  skyt_no_db:

  ; The previous server is kept until the new one has updated the database (E-4). A rename, so the new build is
  ; written into a clean folder; if it fails (a file still locked) the update goes on without the way back.
  RMDir /r "$INSTDIR\server.prev"
  IfFileExists "${SKYT_EXE}" 0 skyt_no_prev
    ClearErrors
    Rename "$INSTDIR\server" "$INSTDIR\server.prev"
    IfErrors skyt_no_prev
    StrCpy $SkytPrev 1
  skyt_no_prev:
!macroend

!macro NSIS_HOOK_POSTINSTALL
  SetShellVarContext all
  StrCpy $9 ""
  DetailPrint "تجهيز خادم البرنامج…"
  ; No question (owner decision 2026-09-27): every PC installs the same way and opens on the login page with the
  ; default owner account. init writes config.json once; an upgrade keeps the existing file (and its role).
  nsExec::Exec '"${SKYT_EXE}" init'
  Pop $0

  ; Hotel data (guests, ID numbers, password hashes, keys) is for Administrators and SYSTEM (the service) only;
  ; other Windows accounts may read the service log (the app window's «فتح سجل الأخطاء»).
  ; Only the top folder gets explicit rights; everything inside is reset to inherit them. «/inheritance:r … /T» on
  ; the whole tree left every existing file with an empty ACL (the service could not open its log), tried on a real
  ; PC with 1.1.9 before release.
  CreateDirectory "${SKYT_DATA}\logs"
  nsExec::Exec 'icacls "${SKYT_DATA}" /inheritance:r /grant:r *S-1-5-32-544:(OI)(CI)F *S-1-5-18:(OI)(CI)F /C /Q'
  Pop $0
  nsExec::Exec 'icacls "${SKYT_DATA}\*" /reset /T /C /Q'
  Pop $0
  nsExec::Exec 'icacls "${SKYT_DATA}\logs" /grant *S-1-5-32-545:(OI)(CI)RX /C /Q'
  Pop $0

  ; Defender: skip real-time scanning of the program and data folders (SQLite WAL writes; docs/windows.md).
  nsExec::Exec 'powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-MpPreference -ExclusionPath $\'$INSTDIR$\', $\'${SKYT_DATA}$\'"'
  Pop $0

  ; The database is updated here, where a failure can be undone, not by a service that would retry for ever (E-4).
  ; 0 = updated, 4 = the database belongs to a newer version (E-5), anything else = the update failed.
  DetailPrint "تحديث بنية قاعدة البيانات…"
  nsExec::ExecToLog '"${SKYT_EXE}" upgrade-db'
  Pop $0
  StrCmp $0 "0" skyt_db_ok
  StrCmp $0 "4" 0 skyt_db_failed
    MessageBox MB_ICONSTOP "قاعدة البيانات على هذا الجهاز من إصدار أحدث من هذا المثبِّت.$\r$\nثبّت الإصدار الأحدث من البرنامج؛ لن يعمل هذا الإصدار عليها." /SD IDOK
    StrCpy $9 "newer"
    Goto skyt_db_ok
  skyt_db_failed:
    DetailPrint "فشل تحديث قاعدة البيانات ($0)؛ إرجاع النسخة السابقة…"
    StrCmp $SkytPre "" skyt_db_program
      Delete "${SKYT_DATA}\data\hotel.db-wal"
      Delete "${SKYT_DATA}\data\hotel.db-shm"
      CopyFiles /SILENT "$SkytPre\hotel.db*" "${SKYT_DATA}\data"
    skyt_db_program:
    StrCmp $SkytPrev 1 0 skyt_db_message
      RMDir /r "$INSTDIR\server"
      Rename "$INSTDIR\server.prev" "$INSTDIR\server"
      StrCpy $SkytPrev 0
    skyt_db_message:
    MessageBox MB_ICONEXCLAMATION "تعذّر تحديث قاعدة البيانات إلى الإصدار ${VERSION}.$\r$\nأُعيدت البيانات والإصدار السابق كما كانا، ويعمل البرنامج كالمعتاد.$\r$\nتواصل مع الدعم وأرسل سجل الأخطاء من:$\r$\n${SKYT_DATA}\logs" /SD IDOK
  skyt_db_ok:
  StrCmp $SkytPrev 1 0 +2
    RMDir /r "$INSTDIR\server.prev"

  ; Service: install, or point an existing one at this build; start with Windows; restart after a crash AND after
  ; an error stop (failureflag), so a start that fails once (e.g. the database busy) is retried by Windows.
  nsExec::Exec '"${SKYT_EXE}" --startup auto install'
  Pop $0
  nsExec::Exec '"${SKYT_EXE}" --startup auto update'
  Pop $0
  ; 127.0.0.1:8471 belongs to the service: a development server left running from a source checkout would
  ; otherwise answer in its place. Only that one is ended; another program is reported in the log (E-13).
  nsExec::Exec '"${SKYT_EXE}" free-port'
  Pop $0
  !insertmacro SKYT_START_SERVICE

  ; Wait until the server answers (at most 2 minutes), so the app window opens on the login page (E-6).
  StrCmp $9 "newer" skyt_up
  DetailPrint "انتظار تشغيل خادم البرنامج…"
  nsExec::Exec 'powershell -NoProfile -ExecutionPolicy Bypass -Command "$$end = (Get-Date).AddSeconds(120); while ((Get-Date) -lt $$end) { try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 http://127.0.0.1:8471/api/v1/system/status | Out-Null; exit 0 } catch { Start-Sleep -Seconds 2 } }; exit 1"'
  Pop $0
  StrCmp $0 "0" skyt_up
    MessageBox MB_ICONEXCLAMATION "ثُبِّت البرنامج لكن خادمه لم يبدأ بعد.$\r$\nأعد تشغيل الجهاز ثم افتح البرنامج. إن استمرت المشكلة فتواصل مع الدعم وأرسل سجل الأخطاء من:$\r$\n${SKYT_DATA}\logs" /SD IDOK
  skyt_up:
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  DetailPrint "إيقاف خادم البرنامج…"
  !insertmacro SKYT_STOP_SERVICE
  nsExec::Exec '"${SKYT_EXE}" remove'
  Pop $0
  SetShellVarContext all
  ; The Defender exclusions were for this program; they do not outlive it (E-18).
  nsExec::Exec 'powershell -NoProfile -ExecutionPolicy Bypass -Command "Remove-MpPreference -ExclusionPath $\'$INSTDIR$\', $\'${SKYT_DATA}$\'"'
  Pop $0
  RMDir /r "$INSTDIR\server.prev"
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; Data stays in %ProgramData%\SkyTowers on purpose (spec §11).
!macroend
