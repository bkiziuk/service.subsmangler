# this file includes all global variables used across the plugin

import os
import xbmc
import xbmcaddon

# addon globals
__addon__ = xbmcaddon.Addon(id='service.subsmangler')
__addondir__ = xbmc.translatePath(__addon__.getAddonInfo('path'))
__addonworkdir__ = xbmc.translatePath(__addon__.getAddonInfo('profile'))
__version__ = __addon__.getAddonInfo('version')
__addonlang__ = __addon__.getLocalizedString
__kodiversion__ = xbmc.getInfoLabel('System.BuildVersion')[:4]

# definitions file
deffileurl = "https://raw.githubusercontent.com/bkiziuk/service.subsmangler/master/resources/regexdef.def"
localdeffilename = os.path.join(__addonworkdir__, 'regexdef.def')
sampledeffilename = os.path.join(__addondir__, 'resources', 'regexdef.def')
tempdeffilename = os.path.join(__addonworkdir__, 'tempdef.def')
deffilename = None

# path and file name of public definitions
# list of input file extensions
# extensions in lowercase with leading dot
# note: we do not include output extension .utf
SubExtList = ['.txt', '.srt', '.sub', '.subrip', '.microdvd', '.mpl', '.tmp', '.ass']

# list of video file extensions
# extensions in lowercase with leading dot
VideoExtList = ['.mkv', '.avi', '.mp4', '.mpg', '.mpeg']

# detection of new subtitles
DetectionIsRunning = False
ClockTick = 1  # FIXME - should be 180

# player
player = None
monitor = None

# subtitles
subtitlePath = None
playingFilename = None
playingFilenamePath = None
playingFps = None
SubsSearchWasOpened = None

# timers
rt = None
ClockTick = 180

# user settings
# declare initial values to be able to import variables to other files
setting_ConversionServiceEnabled = False
setting_AlsoConvertExistingSubtitles = False
setting_SubsOutputFormat = 0
setting_SubsFontSize = 0
setting_ForegroundColor = 0
setting_BackgroundColor = 0
setting_BackgroundTransparency = 0
setting_MaintainBiggerLineSpacing = False
setting_RemoveCCmarks = False
setting_RemoveAds = False
setting_PauseOnConversion = False
setting_AutoInvokeSubsDialog = False
setting_AutoInvokeSubsDialogOnStream = False
setting_NoAutoInvokeIfLocalUnprocSubsFound = False
setting_NoConfirmationInvokeIfDownloadedSubsNotFound = False
setting_AutoUpdateDef = False
setting_SeparateLogFile = False
setting_AutoRemoveOldSubs = False
setting_BackupOldSubs = False
setting_RemoveSubsBackup = False
setting_RemoveUnprocessedSubs = False
setting_SimulateRemovalOnly = False
setting_AdjustSubDisplayTime = False
setting_FixOverlappingSubDisplayTime = False

# subtitle detection
DetectionIsRunning = False
SubsSearchWasOpened = False
subtitlePath = None