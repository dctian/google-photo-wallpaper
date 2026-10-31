Unicode True
!include "MUI2.nsh"
!include "x64.nsh"
!include "WinVer.nsh"
!ifndef VERSION
  !error "Pass /DVERSION=x.y.z"
!endif
!ifndef PAYLOAD
  !error "Pass /DPAYLOAD=absolute payload directory"
!endif
!ifndef OUTPUT
  !error "Pass /DOUTPUT=absolute installer file"
!endif
Name "Google Photos Wallpaper"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\GooglePhotoWallpaper"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetOverwrite on
ShowInstDetails show
ShowUninstDetails show
BrandingText "Unofficial, free and open source"
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "Google Photos Wallpaper"
VIAddVersionKey "FileDescription" "Google Photos Wallpaper Setup"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "David Tian"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\GooglePhotoWallpaper.exe"
!define MUI_FINISHPAGE_RUN_NOTCHECKED
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "This release requires 64-bit Windows."
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "This release requires Windows 10 or 11."
    Abort
  ${EndIf}
  SetShellVarContext current
FunctionEnd
Function .onVerifyInstDir
  # Never adopt a folder containing somebody else's application or data.
  IfFileExists "$INSTDIR\.google-photo-wallpaper-install" done
  FindFirst $0 $1 "$INSTDIR\*"
  loop:
    StrCmp $1 "" finish
    StrCmp $1 "." next
    StrCmp $1 ".." next
    FindClose $0
    SetErrors
    Return
  next:
    FindNext $0 $1
    Goto loop
  finish:
    FindClose $0
  done:
    ClearErrors
FunctionEnd
Section "Application"
  ClearErrors
  Call .onVerifyInstDir
  IfErrors 0 +3
    MessageBox MB_ICONSTOP "Choose an empty folder or this app's existing installation folder."
    Abort
  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD}\*"
  FileOpen $0 "$INSTDIR\.google-photo-wallpaper-install" w
  FileWrite $0 "GooglePhotoWallpaper installer v1"
  FileClose $0
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\Google Photos Wallpaper"
  CreateShortCut "$SMPROGRAMS\Google Photos Wallpaper\Google Photos Wallpaper.lnk" "$INSTDIR\GooglePhotoWallpaper.exe" "" "$INSTDIR\GooglePhotoWallpaper.exe"
  CreateShortCut "$SMPROGRAMS\Google Photos Wallpaper\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GooglePhotoWallpaper" "DisplayName" "Google Photos Wallpaper"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GooglePhotoWallpaper" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GooglePhotoWallpaper" "Publisher" "David Tian"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GooglePhotoWallpaper" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GooglePhotoWallpaper" "DisplayIcon" "$INSTDIR\GooglePhotoWallpaper.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GooglePhotoWallpaper" "URLInfoAbout" "https://github.com/dctian/google-photo-wallpaper"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GooglePhotoWallpaper" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GooglePhotoWallpaper" "NoRepair" 1
SectionEnd
Section "Uninstall"
  SetShellVarContext current
  IfFileExists "$INSTDIR\.google-photo-wallpaper-install" +3
    MessageBox MB_ICONSTOP "Installation marker missing; no application files were removed."
    Abort
  nsExec::ExecToLog '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\_internal\scripts\Remove-Integration.ps1"'
  Pop $0
  StrCmp $0 "0" +3
    MessageBox MB_ICONSTOP "Could not remove scheduled jobs. No application files were removed."
    Abort
  Delete "$INSTDIR\GooglePhotoWallpaper.exe"
  IfErrors 0 +3
    MessageBox MB_ICONSTOP "Close Google Photos Wallpaper and run uninstall again."
    Abort
  Delete "$INSTDIR\GooglePhotoWallpaper-cli.exe"
  IfErrors 0 +3
    MessageBox MB_ICONSTOP "A wallpaper job is still running. Run uninstall again when it finishes."
    Abort
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\.google-photo-wallpaper-install"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  Delete "$SMPROGRAMS\Google Photos Wallpaper\Google Photos Wallpaper.lnk"
  Delete "$SMPROGRAMS\Google Photos Wallpaper\Uninstall.lnk"
  RMDir "$SMPROGRAMS\Google Photos Wallpaper"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\GooglePhotoWallpaper"
  # Config, browser session, downloaded photos and wallpapers are outside INSTDIR.
SectionEnd
