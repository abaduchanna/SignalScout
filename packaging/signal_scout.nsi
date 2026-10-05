; SignalScout — single-exe Windows installer (NSIS)
; -------------------------------------------------
; Why an installer instead of a one-file exe:
;   Nuitka --onefile bootstraps extract the compiled program DLL
;   (run_gui.dll) into %TEMP%\onefile_*\ at every launch. Endpoint
;   security products (SentinelOne et al.) reliably treat a freshly
;   dropped unsigned DLL in Temp as malicious and quarantine it.
;   A NSIS setup installs the standalone build ONCE into a fixed
;   folder — no self-extract step, no Temp payload, nothing to flag.
; Developed by www.3SVerse.com (c) 2026 — MIT licensed.

Unicode true
ManifestDPIAware true

!define APPNAME      "SignalScout"
!define COMPANY      "3SVerse"
!define DESCRIPTION  "Wireless Retail Lead Scout (www.3sverse.com)"
!define VERSION      "0.3.5.0"
!define HELPURL      "https://github.com/abaduchanna/SignalScout"
!define UNINSTKEY    "SignalScout"

Name            "${APPNAME}"
BrandingText    "3SVerse — www.3sverse.com"
OutFile         "SignalScout-Setup.exe"
InstallDir      "$LOCALAPPDATA\Programs\SignalScout"
InstallDirRegKey HKCU "Software\${COMPANY}\${APPNAME}" "InstallDir"
RequestExecutionLevel user
SetCompressor   /SOLID lzma
ShowInstDetails nevershow
ShowUninstDetails nevershow

Icon        "..\assets\3sverse_icon.ico"
UninstallIcon "..\assets\3sverse_icon.ico"

VIProductVersion "${VERSION}"
VIAddVersionKey /LANG=1033 "CompanyName"      "3SVerse"
VIAddVersionKey /LANG=1033 "ProductName"      "SignalScout"
VIAddVersionKey /LANG=1033 "FileDescription"  "SignalScout Setup - Wireless Retail Lead Scout (www.3sverse.com)"
VIAddVersionKey /LANG=1033 "ProductVersion"   "${VERSION}"
VIAddVersionKey /LANG=1033 "FileVersion"      "${VERSION}"
VIAddVersionKey /LANG=1033 "LegalCopyright"   "(c) 2026 3SVerse - www.3sverse.com"
VIAddVersionKey /LANG=1033 "OriginalFilename" "SignalScout-Setup.exe"

Page directory
Page instfiles
UninstPage confirm
UninstPage instfiles

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "dist\SignalScout\*.*"

  ; Start Menu + Desktop shortcuts
  CreateDirectory "$SMPROGRAMS\3SVerse"
  CreateShortcut  "$SMPROGRAMS\3SVerse\SignalScout.lnk" "$INSTDIR\SignalScout.exe"
  CreateShortcut  "$DESKTOP\SignalScout.lnk" "$INSTDIR\SignalScout.exe"

  ; Uninstaller + Add/Remove Programs entry (per-user)
  WriteUninstaller "$INSTDIR\Uninstall SignalScout.exe"
  WriteRegStr   HKCU "Software\${COMPANY}\${APPNAME}" "InstallDir" "$INSTDIR"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${UNINSTKEY}" "DisplayName"     "SignalScout (3SVerse)"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${UNINSTKEY}" "DisplayVersion" "0.3.5"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${UNINSTKEY}" "Publisher"      "3SVerse"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${UNINSTKEY}" "DisplayIcon"    "$INSTDIR\SignalScout.exe"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${UNINSTKEY}" "HelpLink"       "${HELPURL}"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${UNINSTKEY}" "URLInfoAbout"   "https://www.3sverse.com"
  WriteRegStr   HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${UNINSTKEY}" "UninstallString" '"$INSTDIR\Uninstall SignalScout.exe"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${UNINSTKEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  RMDir /r "$INSTDIR"
  Delete "$SMPROGRAMS\3SVerse\SignalScout.lnk"
  RMDir  "$SMPROGRAMS\3SVerse"
  Delete "$DESKTOP\SignalScout.lnk"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${UNINSTKEY}"
  DeleteRegKey HKCU "Software\${COMPANY}\${APPNAME}"
SectionEnd
