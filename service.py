import codecs
import os
import errno
import filecmp
import logging
import re
import stat
import string
import time
import urllib2
import xbmc
import xbmcgui
import xbmcaddon
import xbmcplugin
import xbmcvfs

from datetime import datetime
from json import loads
from logging.handlers import RotatingFileHandler
from shutil import copyfile
from threading import Timer
from resources.lib import pysubs2



# timer class
# from: https://stackoverflow.com/questions/3393612/run-certain-code-every-n-seconds/13151299
class RepeatedTimer(object):
    def __init__(self, interval, function, *args, **kwargs):
        self._timer = None
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.is_running = False
        #self.start()  #do not start automatically

    def _run(self):
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self):
        if not self.is_running:
            self._timer = Timer(self.interval, self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        if self.is_running:
            self._timer.cancel()
            self.is_running = False



# Player class
# https://forum.kodi.tv/showthread.php?tid=130923
# all Player() events are asynchronous to addon script, so we need to wait for event to be triggered (to actually happen) before reading any data
# instead of monitoring player in loop with xbmc.Player().isPlayingVideo() and then launching action
class XBMCPlayer(xbmc.Player):

    def __init__( self, *args ):
        pass

    def onPlayBackStarted( self ):
        # Will be called when xbmc starts playing a file
        global subtitlePath
        global playingFilename
        global playingFilenamePath
        global playingFps
        global SubExtList
        global SubsSearchWasOpened
        global setting_AutoInvokeSubsDialog

        # detect if Player is running by checking xbmc.Player().isPlayingVideo() or xbmc.getCondVisibility('Player.HasVideo')
        # use ConditionalVisibility checks: http://kodi.wiki/view/List_of_boolean_conditions
        #Log("xbmc.Player().isPlayingVideo(): " + str(xbmc.Player().isPlayingVideo()), xbmc.LOGINFO)
        #if xbmc.Player().isPlayingVideo():
        if xbmc.getCondVisibility('Player.HasVideo'):
            # player has just been started, check what contents does it play and from
            Log("VideoPlayer START detected.", xbmc.LOGINFO)
            # get info on file being played
            subtitlePath, playingFilename, playingFilenamePath, playingFps, playingSubs = GetPlayingInfo()

            # ignore all streaming videos
            # http://xion.io/post/code/python-startswith-tuple.html
            protocols = ("http", "https", "mms", "rtsp", "pvr")
            if playingFilenamePath.lower().startswith(tuple(p + '://' for p in protocols)):
                Log("Video stream detected. Ignoring it.", xbmc.LOGINFO)
                return
            elif not playingFilenamePath:
                # string is empty, may happen when playing buffered streams
                Log("Empty string detected. Ignoring it.", xbmc.LOGWARNING)
                return

            # clear temp dir from subtitle files
            tempfilelist = os.listdir(xbmc.translatePath("special://temp"))
            Log("Clearing temporary files.", xbmc.LOGINFO)
            for item in tempfilelist:
                filebase, fileext = os.path.splitext(item)
                if (fileext.lower() in SubExtList) or fileext.lower().endswith("ass"):
                    os.remove(os.path.join(tempfilelist, item))
                    Log("       File: " + os.path.join(tempfilelist, item) + "  removed.", xbmc.LOGINFO)


            #FIXME - compare languages with internal forced subtitles to check if search dialog should be opened

            # check if there are subtitle files already on disk matching video being played
            # if not, automatically open subtitlesearch dialog
            #FIXME - check if Kodi settings on auto subtitles download infuence the process
            # set initial setting for SubsSearchWasOpened flag
            SubsSearchWasOpened = False
            # check if Subtitles Search window should be opened at player start
            if setting_AutoInvokeSubsDialog:
                # get all files matching name of file being played and extension '.ass'
                # also includes 'noautosubs' file and file with '.noautosubs' extension
                localsubs = GetSubtitleFiles(subtitlePath, '.ass')

                # check if there is 'noautosubs' file or extension on returned file list
                noautosubs = False
                for item in localsubs:
                    if "noautosubs" in item[-10:]:
                        # set noautosubs flag informing that subtitles search window should not be invoked
                        noautosubs = True
                        # delete this item from list to not falsely trigger enabling subtitles below
                        del localsubs[item]
                        break

                if not noautosubs:
                    # noautosubs file or extension not found
                    # possible to invoke SubsSearch dialog or enable locally found subtitles
                    #
                    # check if list is empty
                    # https://stackoverflow.com/questions/53513/how-do-i-check-if-a-list-is-empty/53522#53522
                    if not localsubs:
                        Log("No local subtitles matching video being played. Opening search dialog.", xbmc.LOGINFO)
                        # set flag to remember that subtitles search dialog was opened
                        SubsSearchWasOpened = True
                        # invoke subtitles search dialog
                        xbmc.executebuiltin('ActivateWindow(10153)')  # subtitles search
                        # hold further execution until window is closed
                        # wait for window to appear
                        while not xbmc.getCondVisibility("Window.IsVisible(10153)"):
                            xbmc.sleep(1000)
                        # wait for window to disappear
                        while xbmc.getCondVisibility("Window.IsVisible(10153)"):
                            xbmc.sleep(500)
                    else:
                        Log("Local subtitles matching video being played detected. Enabling subtitles.", xbmc.LOGINFO)
                else:
                    Log("'noautosubs' file or extension detected. Not opening subtitles search dialog.", xbmc.LOGINFO)

            # enable subtitles if there are any
            xbmc.Player().showSubtitles(True)

            # check periodically if there are any files changed in monitored subdir that match file being played
            if setting_ConversionServiceEnabled:
                rt.start()

    def onPlayBackEnded( self ):
        # Will be called when xbmc stops playing a file
        # player finished playing video
        Log("VideoPlayer END detected.", xbmc.LOGINFO)

        # stop monitoring dir for changed files
        rt.stop()

    def onPlayBackStopped( self ):
        # Will be called when user stops xbmc playing a file
        # player has just been stopped
        Log("VideoPlayer STOP detected.", xbmc.LOGINFO)

        # stop monitoring dir for changed files
        rt.stop()



# Monitor class
# https://forum.kodi.tv/showthread.php?tid=198911&pid=1750890#pid1750890
class XBMCMonitor(xbmc.Monitor):

    def __init__(self, *args, **kwargs):
        xbmc.Monitor.__init__(self)

    def onAbortRequested(self):
        # Will be called when XBMC requests Abort
        rt.stop()
        Log("Abort requested in Monitor class.")

    def onSettingsChanged(self):
        # Will be called when addon settings are changed
        Log("Addon settings changed.")
        GetSettings()

        # if service is not enabled any more, stop timer
        if not setting_ConversionServiceEnabled:
            rt.stop()



# function matches input string for language designation
# and outputs ISO 639-2 equivalent
# https://stackoverflow.com/questions/2879856/get-system-language-in-iso-639-3-letter-codes-in-python
# http://www.loc.gov/standards/iso639-2/ISO-639-2_utf-8.txt
def GetIsoCode(lang):
    # "bibliographic" iso codes are derived from English word for the language
    # "terminologic" iso codes are derived from the pronunciation in the target
    # language (if different to the bibliographic code)

    Log("Looking for language code for: " + lang)
    f = codecs.open(os.path.join(__addondir__, 'resources', 'ISO-639-2_utf-8.txt'), 'rb', 'utf-8')
    outlang = ''
    for line in f:
        iD = {}
        iD['bibliographic'], iD['terminologic'], iD['alpha2'], iD['english'], iD['french'] = line.strip().split('|')

        if iD['bibliographic'].lower() == lang.lower() or iD['alpha2'].lower() == lang.lower() or iD['english'].lower() == lang.lower():
            outlang = iD['bibliographic']
            break
    f.close()

    if outlang:
        Log("Language code found: " + outlang, xbmc.LOGINFO)
    else:
        Log("Language code not found.", xbmc.LOGINFO)

    return outlang



# function parses input value and determines if it should be True or False value
# this is because Kodi .getSetting function returns string type instead of bool value
def GetBool(stringvalue):
    if stringvalue in ["1", "true", "True", "TRUE"]:
        return True
    else:
        return False



# read settings from configuration file
# settings are read only during addon's start - so for service type addon we need to re-read them after they are altered
# https://forum.kodi.tv/showthread.php?tid=201423&pid=1766246#pid1766246
def GetSettings():
    global setting_LogLevel
    global setting_ConversionServiceEnabled
    global setting_SubsFontSize
    global setting_ForegroundColor
    global setting_BackgroundColor
    global setting_BackgroundTransparency
    global setting_RemoveCCmarks
    global setting_RemoveAds
    global setting_PauseOnConversion
    global setting_AutoInvokeSubsDialog
    global setting_AutoUpdateDef
    global setting_SeparateLogFile
    global setting_AutoRemoveOldSubs
    global setting_BackupOldSubs
    global setting_RemoveSubsBackup
    global setting_SimulateRemovalOnly
    global setting_AdjustSubDisplayTime

    setting_ConversionServiceEnabled = GetBool(__addon__.getSetting("ConversionServiceEnabled"))
    setting_SubsFontSize = int(__addon__.getSetting("SubsFontSize"))
    setting_ForegroundColor = int(__addon__.getSetting("ForegroundColor"))
    setting_BackgroundColor = int(__addon__.getSetting("BackgroundColor"))
    setting_BackgroundTransparency = int(__addon__.getSetting("BackgroundTransparency"))
    setting_RemoveCCmarks = GetBool(__addon__.getSetting("RemoveCCmarks"))
    setting_RemoveAds = GetBool(__addon__.getSetting("RemoveAdds"))
    setting_PauseOnConversion = GetBool(__addon__.getSetting("PauseOnConversion"))
    setting_AutoInvokeSubsDialog = GetBool(__addon__.getSetting("AutoInvokeSubsDialog"))
    setting_AutoRemoveOldSubs = GetBool(__addon__.getSetting("AutoRemoveOldSubs"))
    setting_BackupOldSubs = GetBool(__addon__.getSetting("BackupOldSubs"))
    setting_RemoveSubsBackup = GetBool(__addon__.getSetting("RemoveSubsBackup"))
    setting_SimulateRemovalOnly = GetBool(__addon__.getSetting("SimulateRemovalOnly"))
    setting_AdjustSubDisplayTime = GetBool(__addon__.getSetting("AdjustSubDisplayTime"))
    setting_AutoUpdateDef = GetBool(__addon__.getSetting("AutoUpdateDef"))
    setting_LogLevel = int(__addon__.getSetting("LogLevel"))
    setting_SeparateLogFile = int(__addon__.getSetting("SeparateLogFile"))

    Log("Reading settings.", xbmc.LOGINFO)
    Log("Setting: ConversionServiceEnabled = " + str(setting_ConversionServiceEnabled), xbmc.LOGINFO)
    Log("                     SubsFontSize = " + str(setting_SubsFontSize), xbmc.LOGINFO)
    Log("           BackgroundTransparency = " + str(setting_BackgroundTransparency), xbmc.LOGINFO)
    Log("                    RemoveCCmarks = " + str(setting_RemoveCCmarks), xbmc.LOGINFO)
    Log("                        RemoveAds = " + str(setting_RemoveAds), xbmc.LOGINFO)
    Log("             AdjustSubDisplayTime = " + str(setting_AdjustSubDisplayTime), xbmc.LOGINFO)
    Log("             AutoInvokeSubsDialog = " + str(setting_AutoInvokeSubsDialog), xbmc.LOGINFO)
    Log("                    BackupOldSubs = " + str(setting_BackupOldSubs), xbmc.LOGINFO)
    Log("                AutoRemoveOldSubs = " + str(setting_AutoRemoveOldSubs), xbmc.LOGINFO)
    Log("                 RemoveSubsBackup = " + str(setting_RemoveSubsBackup), xbmc.LOGINFO)
    Log("              SimulateRemovalOnly = " + str(setting_SimulateRemovalOnly), xbmc.LOGINFO)
    Log("                    AutoUpdateDef = " + str(setting_AutoUpdateDef), xbmc.LOGINFO)
    Log("                         LogLevel = " + str(setting_LogLevel), xbmc.LOGINFO)
    Log("                  SeparateLogFile = " + str(setting_SeparateLogFile), xbmc.LOGINFO)



# parses log events based on internal logging level
# xbmc loglevels: https://forum.kodi.tv/showthread.php?tid=324570&pid=2671926#pid2671926
# 0 = LOGDEBUG
# 1 = LOGINFO
# 2 = LOGNOTICE
# 3 = LOGWARNING
# 4 = LOGERROR
# 5 = LOGSEVERE
# 6 = LOGFATAL
# 7 = LOGNONE
def Log(message, severity=xbmc.LOGDEBUG):
    global setting_LogLevel

    if severity >= setting_LogLevel:
        # log the message to Log
        if setting_SeparateLogFile == 0:
            # use kodi.log for logging
            xbmc.log("SubsMangler: " + message, level=xbmc.LOGNONE)
        else:
            # use own log file located in addon's datadir

            # konstruct log text
            # cut last 3 trailing zero's from timestamp
            logtext = str(datetime.now())[:-3]
            if severity == xbmc.LOGDEBUG:
                logtext += "   DEBUG: "
            elif severity == xbmc.LOGINFO:
                logtext += "    INFO: "
            elif severity == xbmc.LOGNOTICE:
                logtext += "  NOTICE: "
            elif severity == xbmc.LOGWARNING:
                logtext += " WARNING: "
            elif severity == xbmc.LOGSEVERE:
                logtext += "  SEVERE: "
            elif severity == xbmc.LOGFATAL:
                logtext += "   FATAL: "
            else:
                logtext += "    NONE: "
            logtext += message
            # append line to external log file, logging via warning level to prevent
            # filtering messages by default filtering level of ROOT logger
            logger.warning(logtext)



# parse a list of definitions from file
# load only a particular section
def GetDefinitions(section):
    global deffilename
    importedlist = list()

    # check if definitions file exists
    if os.path.isfile(deffilename):
        # open file
        with open(deffilename, "rt") as f:
            thissection = False
            for line in f:
                # truncate any comment at the end of line
                # https://stackoverflow.com/questions/509211/understanding-pythons-slice-notation
                pos = line.find("#")
                # if there is no comment, pos==-1
                if pos >= 0:
                    # take only part before comment
                    line = line[:pos]
                # remove whitespaces at the beginning and end
                line = line.strip()

                # patterns for finding sections
                thissectionpattern = "\[" + section + "\]"    # matches: [SeCtIoNnAmE]
                othersectionpattern = "^\[.*?\]"    # matches: <BEGINLINE>[anything]
                if re.search(thissectionpattern, line, re.IGNORECASE):
                    # beginning of our section
                    thissection = True
                elif re.search(othersectionpattern, line):   # matches: <BEGINLINE>[anything]
                    # beginning of other section
                    thissection = False
                elif thissection:
                    # contents of our section - import to list
                    # check if line is not empty, empty line is "falsy"
                    # https://stackoverflow.com/questions/9573244/most-elegant-way-to-check-if-the-string-is-empty-in-python
                    if line:
                        # add to list
                        importedlist.append(line)

        Log("Definitions imported. Section: " + section, xbmc.LOGINFO)
        # dump imported list
        for entry in importedlist:
            Log("       " + entry, xbmc.LOGDEBUG)
    else:
        Log("Definitions file does not exist: " + deffilename, xbmc.LOGINFO)

    return importedlist



# remove all strings from line that match regex deflist
def RemoveStrings(line, deflist):
    # iterate over every entry on the list
    for pattern in deflist:
        if re.search(pattern, line, re.IGNORECASE):
            Log("RemoveStrings: Subtitles line: " + line, xbmc.LOGDEBUG)
            Log("                matches regex: " + pattern, xbmc.LOGDEBUG)
            line = re.sub(pattern, '', line, flags=re.I)
            Log("             Resulting string: " + line, xbmc.LOGDEBUG)
    return line



# get subtitle location setting
# https://forum.kodi.tv/showthread.php?tid=209587&pid=1844182#pid1844182
def GetKodiSetting(name):
    # Uses XBMC/Kodi JSON-RPC API to retrieve subtitles location settings values.
    command = '''{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "Settings.GetSettingValue",
    "params": {
        "setting": "%s"
    }
}'''
    result = xbmc.executeJSONRPC(command % name)
    py = loads(result)
    if 'result' in py and 'value' in py['result']:
        return py['result']['value']
    else:
        raise ValueError



# converts subtitles using pysubs2 library
# pysubs2 code is written by Tomas Karabela - https://github.com/tkarabela/pysubs2
def MangleSubtitles(originalinputfile):

    # tempfilename
    tempfile = "processed_subtitles"

    if not xbmcvfs.exists(originalinputfile):
        Log("File does not exist: " + originalinputfile)
        return

    # get subtitles language by splitting it from filename
    # split file and extension
    subfilebase, subfileext = os.path.splitext(originalinputfile)
    # from filename split language designation
    subfilecore, subfilelang = os.path.splitext(subfilebase)

    Log("Read subtitle language designation: " + subfilelang,xbmc.LOGINFO)
    # try to find ISO639-2 designation
    # remove dot from language code ('.en')
    subslang = GetIsoCode(subfilelang.lower()[1:]).lower()

    # as pysubs2 library doesn't support Kodi's virtual file system and file can not be processed remotely on smb:// share,
    # file must be copied to temp folder for local processing
    # construct input_file name
    tempinputfile = os.path.join(xbmc.translatePath("special://temp"), tempfile + "_in.txt")
    # construct output_file name
    tempoutputfile = os.path.join(xbmc.translatePath("special://temp"), tempfile + "_out.ass")
    # copy file to temp
    copy_file(originalinputfile, tempinputfile)

    Log("subtitle file processing started.", xbmc.LOGNOTICE)

    # record start time of processing
    MangleStartTime = time.time()

    # list of encodings to try
    # the last position should be "NO_MATCH" to detect end of list
    # https://msdn.microsoft.com/en-us/library/windows/desktop/dd317756(v=vs.85).aspx
    encodings = [ "utf-8", "cp1250", "cp1251", "cp1252", "cp1253", "cp1254", "cp1255", "cp1256", "cp1257", "cp1258", "NO_MATCH" ]

    # try to detect proper encoding
    # https://stackoverflow.com/questions/436220/determine-the-encoding-of-text-in-python
    for enc in encodings:
        try:
            with codecs.open(tempinputfile, mode="rb", encoding=enc) as reader:
                temp = reader.read()
                break
        except Exception as e:
            # no encoding fits the file
            if enc == "NO_MATCH":
                break
            # encoding does not match
            Log("Input file test for: " + enc + " failed.", xbmc.LOGINFO)
            continue

    # no encodings match
    if enc == "NO_MATCH":
        Log("No tried encodings match input file.", xbmc.LOGNOTICE)
        return

    Log("Input encoding used: " + enc, xbmc.LOGINFO)
    Log("          Input FPS: " + str(playingFps), xbmc.LOGINFO)

    # load input_file into pysubs2 library
    subs = pysubs2.load(tempinputfile, encoding=enc, fps=float(playingFps))

    # translate foreground color to RGB
    if setting_ForegroundColor == 0:
        # black
        Foreground_R = 0
        Foreground_G = 0
        Foreground_B = 0
    elif setting_ForegroundColor == 1:
        # grey
        Foreground_R = 128
        Foreground_G = 128
        Foreground_B = 128
    elif setting_ForegroundColor == 2:
        # purple
        Foreground_R = 255
        Foreground_G = 0
        Foreground_B = 255
    elif setting_ForegroundColor == 3:
        # blue
        Foreground_R = 0
        Foreground_G = 0
        Foreground_B = 255
    elif setting_ForegroundColor == 4:
        # green
        Foreground_R = 0
        Foreground_G = 255
        Foreground_B = 0
    elif setting_ForegroundColor == 5:
        # red
        Foreground_R = 255
        Foreground_G = 0
        Foreground_B = 0
    elif setting_ForegroundColor == 6:
        # light blue
        Foreground_R = 0
        Foreground_G = 255
        Foreground_B = 255
    elif setting_ForegroundColor == 7:
        # yellow
        Foreground_R = 255
        Foreground_G = 255
        Foreground_B = 0
    elif setting_ForegroundColor == 8:
        # white
        Foreground_R = 255
        Foreground_G = 255
        Foreground_B = 255

    # translate background color to RGB
    if setting_BackgroundColor == 0:
        # black
        Background_R = 0
        Background_G = 0
        Background_B = 0
    elif setting_BackgroundColor == 1:
        # grey
        Background_R = 128
        Background_G = 128
        Background_B = 128
    elif setting_BackgroundColor == 2:
        # purple
        Background_R = 255
        Background_G = 0
        Background_B = 255
    elif setting_BackgroundColor == 3:
        # blue
        Background_R = 0
        Background_G = 0
        Background_B = 255
    elif setting_BackgroundColor == 4:
        # green
        Background_R = 0
        Background_G = 255
        Background_B = 0
    elif setting_BackgroundColor == 5:
        # red
        Background_R = 255
        Background_G = 0
        Background_B = 0
    elif setting_BackgroundColor == 6:
        # light blue
        Background_R = 0
        Background_G = 255
        Background_B = 255
    elif setting_BackgroundColor == 7:
        # yellow
        Background_R = 255
        Background_G = 255
        Background_B = 0
    elif setting_BackgroundColor == 8:
        # white
        Background_R = 255
        Background_G = 255
        Background_B = 255

    # calculate transparency
    # division of integers always gives integer
    Background_T = int((setting_BackgroundTransparency * 255) / 100)

    # change subs style
    subs.styles["Default"].primarycolor = pysubs2.Color(Foreground_R, Foreground_G, Foreground_B, 0)
    subs.styles["Default"].secondarycolor = pysubs2.Color(Foreground_R, Foreground_G, Foreground_B, 0)
    subs.styles["Default"].outlinecolor = pysubs2.Color(Background_R, Background_G, Background_B, Background_T)
    subs.styles["Default"].backcolor = pysubs2.Color(0, 0, 0, 0)
    subs.styles["Default"].fontsize = setting_SubsFontSize
    subs.styles["Default"].bold = -1
    subs.styles["Default"].borderstyle = 3
    subs.styles["Default"].shadow = 0

    # process subs contents
    # iterate over every sub line and process its text
    # http://pythonhosted.org/pysubs2/api-reference.html#ssafile-a-subtitle-file
    if setting_RemoveCCmarks or setting_RemoveAds:
        # load definitions from file
        Log("Definitions file used: " + deffilename, xbmc.LOGINFO)
        CCmarksList = GetDefinitions("CCmarks")
        AdsList = GetDefinitions("Ads")
        # load country specific definitions only if language was detected
        if subslang:
            AdsList += GetDefinitions("Ads_" + subslang)

        # iterate over every line of subtitles and process each subtitle line
        Log("Applying filtering lists.", xbmc.LOGINFO)
        # get number of subs objects to not try to check beyond last item
        subslength = len(subs)
        for index, line in enumerate(subs):
            # load single line to temp variable for processing
            subsline = line.text.encode('utf-8')
            # process subtitle line

            if setting_RemoveCCmarks:
                # remove CC texts from subsline
                subsline = RemoveStrings(subsline, CCmarksList)

            if setting_RemoveAds:
                # remove Advertisement strings from subsline
                subsline = RemoveStrings(subsline, AdsList)

            # remove orphan whitespaces from beginning and end of line
            subsline = subsline.strip()
            # convert double or more whitespaces to single ones
            subsline = re.sub(' {2,}', ' ', subsline)
            # if line is empty after processing, remove line from subtitles file
            # https://stackoverflow.com/questions/9573244/most-elegant-way-to-check-if-the-string-is-empty-in-python
            if not subsline:
                # remove empty line
                subs.remove(line)
                Log("Resulting line is empty. Removing from file.", xbmc.LOGDEBUG)
            else:
                # adjust minimum subtitle display time
                # if calculated time is longer than actual time and if it does not overlap next sub time
                if setting_AdjustSubDisplayTime:
                    # minimum calculated length
                    # 500 ms for line + 400 ms per each word
                    minCalcLength = 500 + int(subsline.count(' ')) * 400

                    Log("Subtitle line " + str(index) + ": " + subsline, xbmc.LOGDEBUG)
                    Log("  Min. calculated length: " + str(minCalcLength) + " ms")
                    Log("  Actual length: " + str(line.duration) + " ms")

                    # check next subtitle start time
                    # https://stackoverflow.com/questions/1011938/python-previous-and-next-values-inside-a-loop
                    if index < (subslength - 1):
                        nextline = subs[index + 1]
                        # get next line start time and compare it to this subtitle end time
                        Log(  "  Clearance to next sub: " + str(nextline.start - line.end) + " ms")
                        if nextline.start - line.end > 10 and minCalcLength > line.duration:
                            # adjust line.duration as much as possible towards minCalcLength
                            #FIXME
                            pass  # not implemented



                # save changed line
                line.plaintext = subsline.decode('utf-8')
        Log("Filtering lists applied.", xbmc.LOGINFO)

    #save subs
    subs.save(tempoutputfile)

    # wait until file is saved
    wait_for_file(tempoutputfile, True)

    # record end time of processing
    MangleEndTime = time.time()

    # truncating seconds: https://stackoverflow.com/questions/8595973/truncate-to-3-decimals-in-python/8595991#8595991
    Log("subtitle file processing finished. Processing took: " + '%.3f'%(MangleEndTime - MangleStartTime) + " seconds.", xbmc.LOGNOTICE)

    # fixme - debug check if file is already released
    try:
        fp = open(tempoutputfile)
        fp.close()
    except Exception as e:
        Log("tempoutputfile NOT released.", xbmc.LOGERROR)
        Log("Exception: " + str(e.message), xbmc.LOGERROR)

    # copy new file back to its original location changing only its extension
    filebase, fileext = os.path.splitext(originalinputfile)
    originaloutputfile = filebase + '.ass'
    copy_file(tempoutputfile, originaloutputfile)

    # make a backup copy of subtitle file or remove file
    if setting_BackupOldSubs:
        rename_file(originalinputfile, originalinputfile + '_backup')
    else:
        delete_file(originalinputfile)

    return originaloutputfile



# copy function
def copy_file(srcFile, dstFile):
    try:
        Log("copy_file: srcFile: " + srcFile, xbmc.LOGINFO)
        Log("           dstFile: " + dstFile, xbmc.LOGINFO)
        if xbmcvfs.exists(dstFile):
            Log("copy_file: dstFile exists. Trying to remove.", xbmc.LOGINFO)
            delete_file(dstFile)
        else:
            Log("copy_file: dstFile does not exist.", xbmc.LOGINFO)
        Log("copy_file: Copy started.", xbmc.LOGINFO)
        success = xbmcvfs.copy(srcFile, dstFile)
        Log("copy_file: SuccessStatus: " + str(success), xbmc.LOGINFO)
    except Exception as e:
        Log("copy_file: Copy failed.", xbmc.LOGERROR)
        Log("Exception: " + str(e.message), xbmc.LOGERROR)

    wait_for_file(dstFile, True)



# rename function
def rename_file(oldfilepath, newfilepath):
    try:
        Log("rename_file: srcFile: " + oldfilepath, xbmc.LOGINFO)
        Log("             dstFile: " + newfilepath, xbmc.LOGINFO)
        # check if new file already exists as in this case rename will fail
        if xbmcvfs.exists(newfilepath):
            Log("rename_file: dstFile exists. Trying to remove.", xbmc.LOGINFO)
            delete_file(newfilepath)
        else:
            Log("rename_file: dstFile does not exist.", xbmc.LOGINFO)
        # rename file
        success = xbmcvfs.rename(oldfilepath, newfilepath)
        Log("rename_file: SuccessStatus: " + str(success), xbmc.LOGINFO)
    except Exception as e:
        Log("Can't rename file: " + oldfilepath, xbmc.LOGERROR)
        Log("Exception: " + str(e.message), xbmc.LOGERROR)



# delete function
def delete_file(filepath):
    try:
        xbmcvfs.delete(filepath)
        Log("delete_file: File deleted: " + filepath, xbmc.LOGINFO)
    except Exception as e:
        Log("delete_file: Delete failed: " + filepath, xbmc.LOGERROR)
        Log("Exception: " + str(e.message), xbmc.LOGERROR)

    wait_for_file(filepath, False)



# function waits for file to appear or disappear, test purpose
def wait_for_file(file, exists):
    success = False
    if exists:
        Log("wait_for_file: if file exists: " + file, xbmc.LOGINFO)
    else:
        Log("wait_for_file: if file doesn't exist: " + file, xbmc.LOGINFO)

    count = 10
    while count:
        xbmc.sleep(500)  # this first sleep is intentional
        if exists:
            if xbmcvfs.exists(file):
                Log("wait_for_file: file appeared.", xbmc.LOGINFO)
                success = True
                break
        else:
            if not xbmcvfs.exists(file):
                Log("wait_for_file: file vanished.", xbmc.LOGINFO)
                success = True
                break
        count -= 1
    if not success:
        if exists:
            Log("wait_for_file: file DID NOT appear.", xbmc.LOGERROR)
        else:
            Log("wait_for_file: file DID NOT vanish.", xbmc.LOGERROR)
        return False
    else:
        return True



# get all subtitle file names in current directory contents for those matching video being played
# get 'noautosubs' file or extension in order to match per directory or per file behaviour
def GetSubtitleFiles(subspath, substypelist):
    # use dictionary solution - load all files to dictionary and remove those not fulfiling criteria
    # Python doesn't support smb:// paths. Use xbmcvfs: https://forum.kodi.tv/showthread.php?tid=211821
    dirs, files = xbmcvfs.listdir(subtitlePath)
    SubsFiles = dict ([(f, None) for f in files])
    # filter dictionary, leaving only subtitle files matching played video
    # https://stackoverflow.com/questions/5384914/how-to-delete-items-from-a-dictionary-while-iterating-over-it
    playingFilenameBase, playingFilenameExt = os.path.splitext(playingFilename)

    for item in SubsFiles.keys():
        # split file and extension
        subfilebase, subfileext = os.path.splitext(item)
        # from filename split language designation
        subfilecore, subfilelang = os.path.splitext(subfilebase)
        # remove files that do not meet criteria
        if not ((((subfilebase.lower() == playingFilenameBase.lower() or subfilecore.lower() == playingFilenameBase.lower()) and (subfileext.lower() in substypelist)) \
            or ((subfilebase.lower() == playingFilenameBase.lower()) and (subfileext.lower() == ".noautosubs"))) \
            or (subfilebase.lower() == "noautosubs")):
            # NOT
            # subfilename matches video name AND fileext is on the list of supported extensions
            # OR subfilename matches video name AND fileext matches '.noautosubs'
            # OR subfilename matches 'noautosubs'
            # FIXME - now we assume that .ass subtitle will not be processed
            del SubsFiles[item]

    return SubsFiles



# pause playback
def PlaybackPause():
    # pause playback
    if not xbmc.getCondVisibility("player.paused"):
        xbmc.Player().pause()
        Log("Playback PAUSED.", xbmc.LOGINFO)
    else:
        Log("Playback already PAUSED.", xbmc.LOGINFO)



# resume playback
def PlaybackResume():
    # resume playback
    if xbmc.getCondVisibility("player.paused"):
        Log("Playback is paused. Resuming.", xbmc.LOGINFO)
        xbmc.Player().pause()
        Log("Playback RESUMED.", xbmc.LOGINFO)
    else:
        Log("Playback not paused. No need to resume.", xbmc.LOGINFO)



# check if any files matching video being played are changed
# http://timgolden.me.uk/python/win32_how_do_i/watch_directory_for_changes.html
def DetectNewSubs():
    global DetectionIsRunning
    global SubsSearchWasOpened

    # if function is already running, exit this instance
    if DetectionIsRunning:
        #Log("Duplicate DetectNewSubs call.", LogWARNING)
        return

    # setting process flag, process starts to run
    DetectionIsRunning = True

    global subtitlePath

    # stop timer in order to not duplicate threads
    #rt.stop()

    # check current directory contents for files touched no later than a few seconds ago
    # load all subtitle files matching video being played
    RecentSubsFiles = GetSubtitleFiles(subtitlePath, SubExtList)

    # check all remaining subtitle files for changed timestamp
    for f in RecentSubsFiles:
        # ignore 'noautosubs' file/extension to not trigger detection of subtitles
        if f[-10:].lower() == "noautosubs":
            continue

        pathfile = os.path.join(subtitlePath, f)
        epoch_file = xbmcvfs.Stat(pathfile).st_mtime()
        epoch_now = time.time()

        if  epoch_file > epoch_now - 6:
            # Video filename matches subtitle filename and it was created/modified no later than 6 secods ago
            Log("New subtitle file detected: " + pathfile, xbmc.LOGNOTICE)

            # record start time of processing
            RoutineStartTime = time.time()

            # hide subtitles
            xbmc.Player().showSubtitles(False)

            if setting_PauseOnConversion:
                # show busy animation
                # https://forum.kodi.tv/showthread.php?tid=280621&pid=2363462#pid2363462
                # https://kodi.wiki/view/Window_IDs
                xbmc.executebuiltin('ActivateWindow(10138)')  # Busy dialog on
                # pause playback
                PlaybackPause()

            # process subtitle file
            ResultFile = MangleSubtitles(pathfile)
            Log("Output subtitle file: " + ResultFile, xbmc.LOGNOTICE)

            # check if destination file exists
            if xbmcvfs.exists(ResultFile):
                Log("Subtitles available.", xbmc.LOGNOTICE)

                # load new subtitles and turn them on
                xbmc.Player().setSubtitles(ResultFile)

                # resume playback
                PlaybackResume()
            else:
                Log("Subtitles NOT available.", xbmc.LOGNOTICE)

            # hide busy animation
            # https://forum.kodi.tv/showthread.php?tid=280621&pid=2363462#pid2363462
            xbmc.executebuiltin('Dialog.Close(10138)')  # Busy dialog off

            # record end time of processing
            RoutineEndTime = time.time()

            # truncating seconds: https://stackoverflow.com/questions/8595973/truncate-to-3-decimals-in-python/8595991#8595991
            Log("Subtitles processing routine finished. Processing took: " + '%.3f'%(RoutineEndTime - RoutineStartTime) + " seconds.", xbmc.LOGNOTICE)

            # clear subtitles search dialog flag to make sure that YesNo dialog will not be triggered
            SubsSearchWasOpened = False

            # sleep for 10 seconds to avoid processing newly added subititle file
            #this should not be needed since we do not support .ass as input file at the moment
            #xbmc.sleep(10000)

    # check if subtitles search window was opened but there were no new subtitles processed
    if SubsSearchWasOpened:
        Log("Subtitles search window was opened but no new subtitles were detected. Opening YesNo dialog.", xbmc.LOGINFO)

        # pause playbcak
        PlaybackPause()

        # display YesNo dialog
        # http://mirrors.xbmc.org/docs/python-docs/13.0-gotham/xbmcgui.html#Dialog-yesno
        YesNoDialog = xbmcgui.Dialog().yesno("Subtitles Mangler", __addonlang__(32040).encode("utf-8"), line2=__addonlang__(32041).encode("utf-8"), nolabel=__addonlang__(32042).encode("utf-8"), yeslabel=__addonlang__(32043).encode("utf-8"))
        if YesNoDialog:
            # user does not want the dialog to appear again
            Log("Answer is Yes. Setting .noautosubs extension flag for file: " + playingFilenamePath.encode("utf-8"), xbmc.LOGINFO)
            # set '.noautosubs' extension for file being played
            try:
                filebase, fileext = os.path.splitext(playingFilenamePath)
                f = xbmcvfs.File (filebase + ".noautosubs", 'w')
                result = f.write("# This file was created by Subtitles Mangler.\n# Presence of this file prevents automatical opening of subtitles search dialog.")
                f.close()
            except Exception as e:
                Log("Can not create noautosubs file.", xbmc.LOGERROR)
                Log("Exception: " + str(e.message), xbmc.LOGERROR)

        else:
            # user wants the dialog to appear again
            Log("Answer is No. Doing nothing.", xbmc.LOGINFO)

        # resume playback
        PlaybackResume()

        # clear the flag to prevent opening dialog on next call of DetectNewSubs()
        SubsSearchWasOpened = False


    # clearing process flag, process is not running any more
    DetectionIsRunning = False

    # restart timer
    #rt.start()



# get information on file currently being played
# http://kodi.wiki/view/InfoLabels
def GetPlayingInfo():

    # get settings from Kodi configuration on assumed subtitles location
    storagemode = GetKodiSetting("subtitles.storagemode") # 1=location defined by custompath; 0=location in movie dir
    custompath = GetKodiSetting("subtitles.custompath")   # path to non-standard dir with subtitles

    if storagemode == 1:    # location == custompath
        if xbmcvfs.exists(custompath):
            subspath = custompath
        else:    # location == movie dir
            subspath = xbmc.translatePath("special://temp")
    else:
        subspath = xbmc.getInfoLabel('Player.Folderpath')

    filename = xbmc.getInfoLabel('Player.Filename')
    filepathname = xbmc.getInfoLabel('Player.Filenameandpath')
    filefps = xbmc.getInfoLabel('Player.Process(VideoFPS)')
    filelang = xbmc.getInfoLabel('VideoPlayer.SubtitlesLanguage')

    Log("File currently played: " + filepathname, xbmc.LOGINFO)
    Log("Subtitles download path: " + subspath, xbmc.LOGINFO)
    Log("Subtitles language: " + filelang, xbmc.LOGINFO)

    return subspath, filename, filepathname, filefps, filelang



# updates regexdef file from server
def UpdateDefFile():
    Log("Trying to update regexp definitions from: " + deffileurl, xbmc.LOGINFO)
    # download file from server
    #http://stackabuse.com/download-files-with-python/
    try:
        filedata = urllib2.urlopen(deffileurl)
        datatowrite = filedata.read()
        with open(tempdeffilename, 'wb') as f:
            f.write(datatowrite)

        # check if target file path exists
        if os.path.isfile(localdeffilename):
            # compare if downloaded temp file and current local file are identical
            if filecmp.cmp(tempdeffilename, localdeffilename, shallow=0):
                Log("Definitions file is up-to-date. Skipping update.", xbmc.LOGINFO)
            else:
                # remove current target file
                Log("Removing current file: " + localdeffilename)
                os.remove(localdeffilename)
                # copy temp file to target file
                copyfile(tempdeffilename, localdeffilename)
                Log("Regex definitions updated.", xbmc.LOGINFO)
        else:
            # copy temp file to target file
            copyfile(tempdeffilename, localdeffilename)
            Log("Regex definitions updated.", xbmc.LOGINFO)

        # remove temp file
        os.remove(tempdeffilename)

    except urllib2.URLError as e:
        Log("Can not download definitions: " + deffileurl, xbmc.LOGERROR)
        Log("Exception: " + str(e.reason), xbmc.LOGERROR)
    except IOError as e:
        Log("Can not copy definitions file to: " + localdeffilename, xbmc.LOGERROR)
    except OSError as e:
        Log("Can not remove temporary definitions file: " + tempdeffilename, xbmc.LOGERROR)



# walk through video sources and remove any subtitle files that do not acompany its own video any more
# also remove '.noautosubs' files
def RemoveOldSubs():

    global SubExtList

    # Uses XBMC/Kodi JSON-RPC API to retrieve video sources location
    # https://kodi.wiki/view/JSON-RPC_API/v8#Files.GetSources
    command = '''{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "Files.GetSources",
    "params": {
        "media": "video"
    }
}'''
    result = xbmc.executeJSONRPC(command)
    sources = loads(result).get('result').get('sources')

    Log("Scanning video sources for orphaned subtitle files.", xbmc.LOGNOTICE)
    # record start time
    ClearStartTime = time.time()

    # create background dialog
    #http://mirrors.kodi.tv/docs/python-docs/13.0-gotham/xbmcgui.html#DialogProgressBG
    pDialog = xbmcgui.DialogProgressBG()
    pDialog.create('Subtitles Mangler', 'Scanning for subtitle files')

    # initiate empty lists
    videofiles = list()
    subfiles = list()

    # construct target list for file candidate extensions to be removed
    extRemovalList = [ '.ass', '.noautosubs' ]
    if setting_RemoveSubsBackup:
        for ext in SubExtList:
            extRemovalList.append(ext + '_backup')

    # process every source path
    for source in sources:
        startdir = source.get('file')
        Log("Processing source path: " + startdir, xbmc.LOGINFO)

        # http://code.activestate.com/recipes/435875-a-simple-non-recursive-directory-walker/
        directories = [startdir]
        while len(directories)>0:
            # take one element from directories list and process it
            directory = directories.pop()
            dirs, files = xbmcvfs.listdir(directory)
            # add every subdir to the list for checking
            for subdir in dirs:
                Log("Adding subpath: " + os.path.join(directory, subdir.decode('utf-8')), xbmc.LOGDEBUG)
                directories.append(os.path.join(directory, subdir.decode('utf-8')))
            # check every file in the current subdir and add it to appropriate list
            for thisfile in files:
                fullfilepath = os.path.join(directory, thisfile.decode('utf-8'))
                filebase, fileext = os.path.splitext(fullfilepath)
                if fileext in VideoExtList:
                    # this file is video - add to video list
                    Log("Adding to video list: " + fullfilepath.encode('utf-8'),xbmc.LOGDEBUG)
                    videofiles.append(fullfilepath)
                elif fileext in extRemovalList:
                    # this file is subs related - add to subs list
                    Log("Adding to subs list: " + fullfilepath.encode('utf-8'),xbmc.LOGDEBUG)
                    subfiles.append(fullfilepath)

    # process custom subtitle path if it is set in Kodi configuration
    # get settings from Kodi configuration on assumed subtitles location
    storagemode = GetKodiSetting("subtitles.storagemode") # 1=location defined by custompath; 0=location in movie dir
    custompath = GetKodiSetting("subtitles.custompath")   # path to non-standard dir with subtitles

    if storagemode == 1:    # location == custompath
        if xbmcvfs.exists(custompath):
            subspath = custompath
        else:
            subspath = ""
    else:
        subspath = ""

    if subspath:
        Log("Scanning for orphaned subtitle files on custom path: " + subspath, xbmc.LOGNOTICE)
        dirs, files = xbmcvfs.listdir(subspath)
        for thisfile in files:
            fullfilepath = os.path.join(subspath, thisfile.decode('utf-8'))
            filebase, fileext = os.path.splitext(fullfilepath)
            if fileext in extRemovalList:
                # this file is subs related - add to subs list
                Log("Adding to subs list: " + fullfilepath,xbmc.LOGDEBUG)
                subfiles.append(fullfilepath)


    # record scan time
    ClearScanTime = time.time()
    Log("Scanning for orphaned subtitle files finished. Processing took: " + '%.3f'%(ClearScanTime - ClearStartTime) + " seconds.", xbmc.LOGNOTICE)

    Log("Clearing orphaned subtitle files.", xbmc.LOGNOTICE)
    # update background dialog
    pDialog.update(50, message='Clearing orphaned subtitle files')

    # lists filled, compare subs list with video list
    for subfile in subfiles:
        # split filename from full path
        subfilename = os.path.basename(subfile)
        # split filename and extension
        subfilebase, subfileext = os.path.splitext(subfilename)
        # from filename split language designation
        subfilecore, subfilelang = os.path.splitext(subfilebase)

        # check if there is a video matching subfile
        videoexists = False
        for videofile in videofiles:
            # split filename from full path
            videofilename = os.path.basename(videofile)
            # split filename and extension
            videofilebase, videofileext = os.path.splitext(videofilename)

            # check if subfile basename or corename equals videofile basename
            if subfilebase.lower() == videofilebase.lower() or subfilecore.lower() == videofilebase.lower():
                videoexists = True
                break

        if not videoexists:
            if setting_SimulateRemovalOnly:
                Log("There is no video file matching: " + subfile.encode('utf-8') + "  File would have been deleted if Simulate option had been off.", xbmc.LOGDEBUG)
            else:
                Log("There is no video file matching: " + subfile.encode('utf-8') + "  Deleting it.", xbmc.LOGDEBUG)
                delete_file(subfile)
        else:
            Log("Video file matching: " + subfile.encode('utf-8'), xbmc.LOGDEBUG)
            Log("              found: " + videofile.encode('utf-8'), xbmc.LOGDEBUG)

    # record end time
    ClearEndTime = time.time()
    Log("Clearing orphaned subtitle files finished. Processing took: " + '%.3f'%(ClearEndTime - ClearScanTime) + " seconds.", xbmc.LOGNOTICE)

    # close background dialog
    pDialog.close()







#
# execution starts here
#
# watch out for encodings
# https://forum.kodi.tv/showthread.php?tid=144677
# https://nedbatchelder.com/text/unipain.html
# https://www.joelonsoftware.com/2003/10/08/the-absolute-minimum-every-software-developer-absolutely-positively-must-know-about-unicode-and-character-sets-no-excuses/

__addon__ = xbmcaddon.Addon(id='service.subsmangler')
__addondir__ = xbmc.translatePath(__addon__.getAddonInfo('path').decode("utf-8"))
__addonworkdir__ = xbmc.translatePath(__addon__.getAddonInfo('profile').decode('utf-8'))
__version__ = __addon__.getAddonInfo('version')
__addonlang__ = __addon__.getLocalizedString


# path and file name of public definitions
global deffilename
deffileurl = "http://bkiziuk.github.io/kodi-repo/regexdef.txt"
localdeffilename = os.path.join(__addonworkdir__, 'regexdef.txt')
sampledeffilename = os.path.join(__addondir__, 'resources', 'regexdef.txt')
tempdeffilename = os.path.join(xbmc.translatePath("special://temp"), 'deffile.txt')

# list of input file extensions
# extensions in lowercase with leading dot
# FIXME - we do not include output extension .ass as conversion routine is sometimes wrongly triggered on converted subtitle file
SubExtList = [ '.txt', '.srt', '.sub', '.subrip', '.microdvd', '.mpl', '.tmp' ]

# list of video file extensions
# extensions in lowercase with leading dot
VideoExtList = [ '.mkv', '.avi', '.mp4', '.mpg', '.mpeg' ]


if __name__ == '__main__':
    monitor = XBMCMonitor()
    player = XBMCPlayer()

    xbmc.log("SubsMangler: started. Version: %s" % (__version__), level=xbmc.LOGNOTICE)

    # prepare timer to launch
    rt = RepeatedTimer(2.0, DetectNewSubs)

    # set initial values
    DetectionIsRunning = False
    ClockTick = 0

    # prepare datadir
    # directory and file is local to the filesystem
    # no need to use xbmcvfs
    if not os.path.isdir(__addonworkdir__):
        xbmc.log("SubsMangler: profile directory doesn't exist: " + __addonworkdir__.encode('utf-8') + "   Trying to create.", level=xbmc.LOGNOTICE)
        try:
            os.mkdir(__addonworkdir__)
            xbmc.log("SubsMangler: profile directory created: " + __addonworkdir__.encode('utf-8'), level=xbmc.LOGNOTICE)
        except OSError as e:
            xbmc.log("SubsMangler: Log: can't create directory: " +__addonworkdir__.encode('utf-8'), level=xbmc.LOGERROR)
            xbmc.Log("Exception: " + str(e.message).encode('utf-8'), xbmc.LOGERROR)

    # prepare external log handler
    # https://docs.python.org/2/library/logging.handlers.html
    logger = logging.getLogger(__name__)
    loghandler = logging.handlers.TimedRotatingFileHandler(os.path.join(__addonworkdir__, 'smangler.log',), when="midnight", interval=1, backupCount=7)
    logger.addHandler(loghandler)

    # load settings
    GetSettings()

    # check if external log is configured
    if setting_SeparateLogFile == 1:
        xbmc.log("SubsMangler: External log enabled: " + os.path.join(__addonworkdir__, 'smangler.log').encode('utf-8'), level=xbmc.LOGNOTICE)

    # monitor whether Kodi is running
    # http://kodi.wiki/view/Service_add-ons
    while not monitor.abortRequested():
        # wait for about 5 seconds
        if monitor.waitForAbort(5):
            # Abort was requested while waiting. The addon should exit
            rt.stop()
            xbmc.log("SubsMangler: Abort requested. Exiting.", level=xbmc.LOGNOTICE)
            break


        #
        # any code that must be executed periodically
        #
        # set definitions file location
        # dir is local, no need to use xbmcvfs()
        if os.path.isfile(os.path.join(__addonworkdir__, 'regexdef.txt')):
            # downloaded file is available
            deffilename = os.path.join(__addonworkdir__, 'regexdef.txt')
        else:
            # use sample file from addon's dir
            deffilename = os.path.join(__addondir__, 'resources', 'regexdef.txt')

        # housekeeping services
        if ClockTick <=0 and not xbmc.getCondVisibility('Player.HasMedia'):
            # check if auto-update is enabled and player does not play any content
            if setting_AutoUpdateDef:
                # update regexdef file
                UpdateDefFile()

            # check if auto-update is enabled and player does not play any content
            if setting_AutoRemoveOldSubs:
                # clear old subtitle files
                RemoveOldSubs()

            # reset timer to 6 hours
            # 1 tick per 5 sec * 60 min * 6 hrs = 4320 ticks
            ClockTick = 4320

        # decrease timer
        # avoid decreasing the timer to infinity
        if ClockTick > 0:
            ClockTick -= 1
