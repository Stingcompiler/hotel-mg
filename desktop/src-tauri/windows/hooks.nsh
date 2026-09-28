; Sky Towers installer hooks (spec §11), included by the Tauri NSIS template.
;   install:   config.json once (no question; the default owner account is created on first start) → ACLs on %ProgramData%\SkyTowers → Defender exclusion
;              → Windows service «SkyTowersServer» (auto start, restart on failure or error) → start
;   upgrade:   stop the service; copy the database files to backups\pre-upgrade-<version> (whichever update path is
;              chosen); the new build migrates on start
;   uninstall: stop and remove the service; %ProgramData%\SkyTowers (database, backups, keys) is never deleted

!define SKYT_SERVICE "SkyTowersServer"
!define SKYT_EXE "$INSTDIR\server\skytowers-server.exe"
!define SKYT_DATA "$COMMONAPPDATA\SkyTowers"

!macro SKYT_STOP_SERVICE
  ; No automatic restart while files are replaced or the service removed: the recovery actions (set again after
  ; install) would bring an ended build back within 5 s and it would lock its files.
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

!macro NSIS_HOOK_PREINSTALL
  SetShellVarContext all
  IfFileExists "${SKYT_EXE}" 0 skyt_stopped
    DetailPrint "إيقاف خادم البرنامج قبل التحديث…"
    !insertmacro SKYT_STOP_SERVICE
  skyt_stopped:
  ; The database files themselves, before the new build migrates them — on every path, including «إزالة الإصدار
  ; الحالي ثم التثبيت» where the old uninstaller already ran. Plain file copies: no program has to open the key.
  IfFileExists "${SKYT_DATA}\data\hotel.db" 0 skyt_no_db
    DetailPrint "حفظ نسخة من قاعدة البيانات قبل التحديث…"
    CreateDirectory "${SKYT_DATA}\backups\pre-upgrade-${VERSION}"
    CopyFiles /SILENT "${SKYT_DATA}\data\hotel.db*" "${SKYT_DATA}\backups\pre-upgrade-${VERSION}"
  skyt_no_db:
!macroend

!macro NSIS_HOOK_POSTINSTALL
  SetShellVarContext all
  DetailPrint "تجهيز خادم البرنامج…"
  ; No question (owner decision 2026-09-27): every PC installs the same way and opens on the login page with the
  ; default owner account. init writes config.json once; an upgrade keeps the existing file (and its role).
  nsExec::Exec '"${SKYT_EXE}" init'
  Pop $0

  ; Hotel data (guests, ID numbers, password hashes, keys) is for Administrators and SYSTEM (the service) only;
  ; other Windows accounts may read the service log (the app window's «فتح سجل الأخطاء»).
  CreateDirectory "${SKYT_DATA}\logs"
  nsExec::Exec 'icacls "${SKYT_DATA}" /inheritance:r /grant:r *S-1-5-32-544:(OI)(CI)F *S-1-5-18:(OI)(CI)F /T /C /Q'
  Pop $0
  nsExec::Exec 'icacls "${SKYT_DATA}\logs" /grant *S-1-5-32-545:(OI)(CI)RX /T /C /Q'
  Pop $0

  ; Defender: skip real-time scanning of the program and data folders (SQLite WAL writes; docs/windows.md).
  nsExec::Exec 'powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-MpPreference -ExclusionPath $\'$INSTDIR$\', $\'${SKYT_DATA}$\'"'
  Pop $0

  ; Service: install, or point an existing one at this build; start with Windows; restart after a crash AND after
  ; an error stop (failureflag), so a start that fails once (e.g. the database busy) is retried by Windows.
  nsExec::Exec '"${SKYT_EXE}" --startup auto install'
  Pop $0
  nsExec::Exec '"${SKYT_EXE}" --startup auto update'
  Pop $0
  nsExec::Exec 'sc failure ${SKYT_SERVICE} reset= 86400 actions= restart/5000/restart/5000/restart/30000'
  Pop $0
  nsExec::Exec 'sc failureflag ${SKYT_SERVICE} 1'
  Pop $0
  ; 127.0.0.1:8471 belongs to the service: a server left running from a source checkout would otherwise answer
  ; in its place («واجهة البرنامج غير مبنية بعد»). Our own executable is never ended.
  nsExec::Exec '"${SKYT_EXE}" free-port'
  Pop $0
  nsExec::Exec 'sc start ${SKYT_SERVICE}'
  Pop $0
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  DetailPrint "إيقاف خادم البرنامج…"
  !insertmacro SKYT_STOP_SERVICE
  nsExec::Exec '"${SKYT_EXE}" remove'
  Pop $0
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; Data stays in %ProgramData%\SkyTowers on purpose (spec §11).
!macroend
