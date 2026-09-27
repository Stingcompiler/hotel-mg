; Sky Towers installer hooks (spec §11), included by the Tauri NSIS template.
;   install:   role (استقبال / مالك) → config.json once → ACLs on %ProgramData%\SkyTowers → Defender exclusion
;              → Windows service «SkyTowersServer» (auto start, restart on failure) → start
;   upgrade:   stop the service and take a pre-upgrade backup with the old build; the new build migrates on start
;   uninstall: stop and remove the service; %ProgramData%\SkyTowers (database, backups, keys) is never deleted

!define SKYT_SERVICE "SkyTowersServer"
!define SKYT_EXE "$INSTDIR\server\skytowers-server.exe"

!macro NSIS_HOOK_PREINSTALL
  SetShellVarContext all
  IfFileExists "${SKYT_EXE}" 0 skyt_fresh
    DetailPrint "Stopping ${SKYT_SERVICE} and taking a pre-upgrade backup…"
    nsExec::ExecToLog 'sc stop ${SKYT_SERVICE}'
    ; Builds before 1.0.5 hang in STOP_PENDING while the app window is connected: give the stop time, then end the
    ; process so its files can be replaced (SQLite keeps committed data). A stopped service makes this a no-op.
    Sleep 8000
    nsExec::ExecToLog 'taskkill /F /IM skytowers-server.exe'
    Sleep 1000
    nsExec::ExecToLog '"${SKYT_EXE}" manage backup_now'
  skyt_fresh:
!macroend

!macro NSIS_HOOK_POSTINSTALL
  SetShellVarContext all
  ; Role: asked once; an existing config.json (upgrade) is kept as it is.
  IfFileExists "$COMMONAPPDATA\SkyTowers\config.json" skyt_config_done 0
    ; The buttons follow the language of Windows (Yes/No on an English Windows), so the text names both.
    MessageBox MB_YESNO|MB_ICONQUESTION "هل هذا جهاز الاستقبال؟$\r$\n$\r$\n• اضغط «نعم» (Yes) إذا كان هذا الجهاز في مكتب الاستقبال: عليه يسجّل الموظفون الحجوزات والدفعات.$\r$\n$\r$\n• اضغط «لا» (No) إذا كان هذا جهاز المالك: لمتابعة الأرقام والتقارير فقط.$\r$\n$\r$\nإذا لم تكن متأكدًا فاضغط «نعم»." /SD IDYES IDYES skyt_reception
      nsExec::ExecToLog '"${SKYT_EXE}" init --role owner'
      Goto skyt_config_done
    skyt_reception:
      nsExec::ExecToLog '"${SKYT_EXE}" init --role reception'
  skyt_config_done:

  ; Only Administrators and SYSTEM (the service account) write the data folder; users may read.
  nsExec::ExecToLog 'icacls "$COMMONAPPDATA\SkyTowers" /inheritance:r /grant:r *S-1-5-32-544:(OI)(CI)F *S-1-5-18:(OI)(CI)F *S-1-5-32-545:(OI)(CI)RX /T /C /Q'

  ; Defender: skip real-time scanning of the program and data folders (SQLite WAL writes; docs/windows.md).
  nsExec::ExecToLog 'powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-MpPreference -ExclusionPath $\'$INSTDIR$\', $\'$COMMONAPPDATA\SkyTowers$\'"'

  ; Service: install, or point an existing one at this build; start with Windows; restart on failure.
  nsExec::ExecToLog '"${SKYT_EXE}" --startup auto install'
  nsExec::ExecToLog '"${SKYT_EXE}" --startup auto update'
  nsExec::ExecToLog 'sc failure ${SKYT_SERVICE} reset= 86400 actions= restart/5000/restart/5000/restart/30000'
  ; 127.0.0.1:8471 belongs to the service: a server left running from a source checkout would otherwise answer
  ; in its place («واجهة البرنامج غير مبنية بعد»). Our own executable is never ended.
  nsExec::ExecToLog '"${SKYT_EXE}" free-port'
  nsExec::ExecToLog 'sc start ${SKYT_SERVICE}'
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  nsExec::ExecToLog 'sc stop ${SKYT_SERVICE}'
  Sleep 8000
  nsExec::ExecToLog 'taskkill /F /IM skytowers-server.exe'
  Sleep 1000
  nsExec::ExecToLog '"${SKYT_EXE}" remove'
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; Data stays in %ProgramData%\SkyTowers on purpose (spec §11).
!macroend
