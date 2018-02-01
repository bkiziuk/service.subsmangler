import os
import re
import string
import time
import xbmc
import xbmcgui
import xbmcaddon
import xbmcplugin
import xbmcvfs
import urllib
import codecs

from json import loads
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

        # detect if Player is running by checking xbmc.Player().isPlayingVideo() or xbmc.getCondVisibility('Player.HasVideo')
        # use ConditionalVisibility checks: http://kodi.wiki/view/List_of_boolean_conditions
        #Log("xbmc.Player().isPlayingVideo(): " + str(xbmc.Player().isPlayingVideo()), xbmc.LOGINFO)
        #if xbmc.Player().isPlayingVideo():
        if xbmc.getCondVisibility('Player.HasVideo'):
            # player has just been started, check what contents does it play and from
            Log("VideoPlayer START detected", xbmc.LOGINFO)
            # get info on file being played
            subtitlePath, playingFilename, playingFilenamePath, playingFps = GetPlayingInfo()

            # clear temp dir from subtitle files
            tempfilelist = os.listdir(xbmc.translatePath("special://temp"))
            for item in tempfilelist:
                if (item[-4:].lower() in SubExtList) or item.lower().endswith(".ass"):
                    os.remove(os.path.join(tempfilelist, item))
            
            # check periodically if there are any files changed in monitored subdir that match file being played
            if setting_ServiceEnabled:
                rt.start()

    def onPlayBackEnded( self ):
        # Will be called when xbmc stops playing a file
        # player finished playing video
        Log("VideoPlayer END detected", xbmc.LOGINFO)

        # stop monitoring dir for changed files
        rt.stop()

    def onPlayBackStopped( self ):
        # Will be called when user stops xbmc playing a file
        # player has just been stopped
        Log("VideoPlayer STOP detected", xbmc.LOGINFO)

        # stop monitoring dir for changed files
        rt.stop()



# Monitor class
# https://forum.kodi.tv/showthread.php?tid=198911&pid=1750890#pid1750890
class XBMCMonitor(xbmc.Monitor):

    def __init__(self, *args, **kwargs):
        xbmc.Monitor.__init__(self)

    def onAbortRequested(self):
        # Will be called when XBMC requests Abort
        Log("Abort requested in Monitor class.")

    def onSettingsChanged(self):
        # Will be called when addon settings are changed
        Log("Addon settings changed.")
        GetSettings()

        # if service is not enabled any more, stop timer
        if not setting_ServiceEnabled:
            rt.stop()



# read settings from configuration file
# settings are read only during addon's start - so for service type addon we need to re-read them after they are altered
# https://forum.kodi.tv/showthread.php?tid=201423&pid=1766246#pid1766246
def GetSettings():
    global setting_LogLevel
    global setting_SubsFontSize
    global setting_ServiceEnabled
    global setting_RemoveCCmarks
    global setting_RemoveAds
    global setting_AutoUpdateDef

    setting_LogLevel = __addon__.getSetting("LogLevel")
    setting_ServiceEnabled = __addon__.getSetting("ServiceEnabled")
    setting_SubsFontSize = int(float(__addon__.getSetting("SubsFontSize")))
    setting_RemoveCCmarks = __addon__.getSetting("RemoveCCmarks")
    setting_RemoveAds = __addon__.getSetting("RemoveAdds")
    setting_AutoUpdateDef = __addon__.getSetting("AutoUpdateDef")

    Log("Reading settings.", xbmc.LOGINFO)
    Log("Setting: ServiceEnabled = " + setting_ServiceEnabled, xbmc.LOGINFO)
    Log("           SubsFontSize = " + str(setting_SubsFontSize), xbmc.LOGINFO)
    Log("          RemoveCCmarks = " + setting_RemoveCCmarks, xbmc.LOGINFO)
    Log("              RemoveAds = " + setting_RemoveAds, xbmc.LOGINFO)
    Log("          AutoUpdateDef = " + setting_AutoUpdateDef, xbmc.LOGINFO)
    Log("               LogLevel = " + setting_LogLevel, xbmc.LOGINFO)



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

    if setting_LogLevel >= severity:
        # log the message to Log
        xbmc.log("SubsMangler: " + message, level=xbmc.LOGNONE)



# parse a list of definitions from file
# load only a particular section
def GetDefinitions(section):
    global deffilename
    importedlist = list()

    # check if file exists
    if xbmcvfs.exists(deffilename):
        # open file
        with open(deffilename, "rt") as f:
            thissection = False
            for line in f:
                # remove whitespaces at the beginning and end
                line = string.strip(line)
                # patterns for finding sections
                thissectionpattern = "^\[" + section + "\]"    # matches: <BEGINLINE>[SeCtIoNnAmE]
                othersectionpattern = "^\[.*?\]"    # matches: <BEGINLINE>[anything]
                if re.search(thissectionpattern, line, re.IGNORECASE):   
                    # beginning of our section
                    thissection = True
                elif re.search(othersectionpattern, line):   # matches: <BEGINLINE>[anything]
                    # beginning of other section
                    thissection = False
                elif thissection:
                    # contents of our section
                    # import to list
                    # truncate any comment at the end of line
                    # https://stackoverflow.com/questions/509211/understanding-pythons-slice-notation
                    pos = line.find("#")
                    line = line[:pos].strip()
                    # check if line is not empty, empty line is "falsy"
                    # https://stackoverflow.com/questions/9573244/most-elegant-way-to-check-if-the-string-is-empty-in-python
                    if line:
                        # add to list
                        importedlist.append(line)

        Log("Definitions imported. Section: " + section, xbmc.LOGINFO)
        # dump imported list
        for entry in importedlist:
            Log("Entry: " + entry, xbmc.LOGDEBUG)
    else:
        Log("Definitions file does not exist: " + deffilename, xbmc.LOGINFO)
    
    return importedlist



# remove all strings from line that match deflist
def RemoveStrings(line, deflist):    
    # iterate over every entry on the list
    for pattern in deflist:
        if re.match(pattern, line):
            Log("RemoveStrings: Subtitles line: " + line, xbmc.LOGDEBUG)
            Log("                matches regex: " + pattern, xbmc.LOGDEBUG)
            line = re.sub(pattern, line, '')
            Log("          Resulting string is: " + line, xbmc.LOGDEBUG)
    return line



# get subtitle location setting
# https://forum.kodi.tv/showthread.php?tid=209587&pid=1844182#pid1844182
def GetSubtitleSetting(name):
    # Uses XBMC/Kodi JSON-RPC API to retrieve subtitles location settings values.
    command = '''{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "Settings.GetSettingValue",
    "params": {
        "setting": "subtitles.%s"
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
    
    global playingFps
    
    # tempfilename
    tempfile = "processed_subtitles"

    if not xbmcvfs.exists(originalinputfile):
        Log("File does not exist: " + originalinputfile)
        return

    # as pysubs2 library doesn't support Kodi's virtual file system and file can not be processed remotely on smb:// share,
    # file must be copied to temp folder for local processing
    # construct input_file name
    tempinputfile = os.path.join(xbmc.translatePath("special://temp"), tempfile + "_in.txt")
    # construct output_file name
    tempoutputfile = os.path.join(xbmc.translatePath("special://temp"), tempfile + "_out.ass")
    # copy file to temp
    copy_file(originalinputfile, tempinputfile)

    Log("Subtitles file processing started.", xbmc.LOGNOTICE)

    # record start time of processing
    MangleStartTime = time.time()

    # list of encodings to try
    # the last position should be "NO_MATCH" to detect end of list
    encodings = [ "utf-8", "cp1252", "cp1250", "NO_MATCH" ]

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

    # change subs style
    subs.styles["Default"].primarycolor = pysubs2.Color(255, 255, 255, 0)
    subs.styles["Default"].secondarycolor = pysubs2.Color(255, 255, 255, 0)
    subs.styles["Default"].outlinecolor = pysubs2.Color(0, 0, 0, 0)
    subs.styles["Default"].backcolor = pysubs2.Color(0, 0, 0, 0)
    subs.styles["Default"].fontsize = setting_SubsFontSize
    subs.styles["Default"].bold = -1
    subs.styles["Default"].borderstyle = 3
    subs.styles["Default"].shadow = 0

    # process subs contents
    # iterate over every sub and process its text
    # http://pythonhosted.org/pysubs2/api-reference.html#ssafile-a-subtitle-file
    if setting_RemoveCCmarks or setting_RemoveAds:
        # load definitions from file
        Log("Definitions file used: " + deffilename, xbmc.LOGINFO)
        CCmarksList = GetDefinitions("CCmarks")
        AdsList = GetDefinitions("Ads")

        # iterate over every line of subtitles and try to match  Regular Expressions filters
        Log("Applying filtering lists.", xbmc.LOGINFO)
        for line in subs:
            # load single line to temp variable for processing
            subsline = line.text.encode('utf-8')
            # process subtitle line

            if setting_RemoveCCmarks:
                # remove CC texts from subsline 
                subsline = RemoveStrings(subsline, CCmarksList)

            if setting_RemoveAds:
                # remove Advertisement strings
                subsline = RemoveStrings(subsline, AdsList)

            # remove orphan whitespaces
            subsline = subsline.strip()
            # if line is empty after processing, remove line from subtitles file
            # https://stackoverflow.com/questions/9573244/most-elegant-way-to-check-if-the-string-is-empty-in-python
            if not subsline:
                # remove empty line
                subs.remove(line)
                Log("Resulting line is empty. Removing from file.", xbmc.LOGDEBUG)
            else:
                # save changed line
                line.plaintext = subsline.decode('utf-8')

    #save subs
    subs.save(tempoutputfile)

    # wait until file is saved
    wait_for_file(tempoutputfile, True)

    # record end time of processing
    MangleEndTime = time.time()
    
    # truncating seconds: https://stackoverflow.com/questions/8595973/truncate-to-3-decimals-in-python/8595991#8595991
    Log("Subtitles file processing finished. Processing took: " + '%.3f'%(MangleEndTime - MangleStartTime) + " seconds.", xbmc.LOGNOTICE)

    # fixme - debug check if file is already released
    try:
        fp = open(tempoutputfile)
        fp.close()
    except Exception as e:
        Log("tempoutputfile NOT released.", xbmc.LOGERROR)
        Log("Exception: " + e.errno + " - " + e.message, xbmc.LOGERROR)

    # copy new file back to its original location changing only its extension
    originaloutputfile = originalinputfile[:-4] + '.ass'
    copy_file(tempoutputfile, originaloutputfile)

    # rename old file to file_ for further debugging
    rename_file(originalinputfile, originalinputfile + '_')

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
        Log("Exception: " + e.errno + " - " + e.message, xbmc.LOGERROR)

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
        Log("Can't rename file: " + originalinputfile, xbmc.LOGERROR)
        Log("Exception: " + e.errno + " - " + e.message, xbmc.LOGERROR)



# delete function
def delete_file(filepath):
    try:
        xbmcvfs.delete(filepath)
        Log("delete_file: File deleted: " + filepath, xbmc.LOGINFO)
    except Exception as e:
        Log("delete_file: Delete failed: " + filepath, xbmc.LOGERROR)
        Log("Exception: " + e.errno + " - " + e.message, xbmc.LOGERROR)
    
    wait_for_file(filepath, False)



# function waits for file to appear or disappear, test purpose
def wait_for_file(file, exists):
    success = False
    if exists:
        Log("wait_for_file: if file exists: " + file, xbmc.LOGINFO)
    else:
        Log("wait_for_file: if file doesn't exist: " + file, xbmc.LOGINFO)

    count = 20
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



# check if any files matching video being played are changed
# http://timgolden.me.uk/python/win32_how_do_i/watch_directory_for_changes.html
def DetectNewSubs():
    global DetectionIsRunning

    # if function is already running, exit this instance
    if DetectionIsRunning:
        #Log("Duplicate DetectNewSubs call.", LogWARNING)
        return

    # setting process flag, process starts to run
    DetectionIsRunning = True
    
    global subtitlePath
    global SubExtList
    
    # stop timer in order to not duplicate threads
    #rt.stop()
    
    # check current directory contents for files touched no later than a few seconds ago
    # listing and checking all files is too much time consuming for HTPC
    # use dictionary solution - load all files to dictionary and remove those not fulfiling criteria
    # Python doesn't support smb:// paths. Use xbmcvfs: https://forum.kodi.tv/showthread.php?tid=211821
    dirs, files = xbmcvfs.listdir(subtitlePath)
    RecentSubsFiles = dict ([(f, None) for f in files])
    # filter dictionary, leaving only subtitle files matching played video
    # https://stackoverflow.com/questions/5384914/how-to-delete-items-from-a-dictionary-while-iterating-over-it
    for item in RecentSubsFiles.keys():
        if not ((item.lower()[:-7] == playingFilename.lower()[:-4]) and (item.lower()[-4:] in SubExtList)):
            # subtitle name does not match video name
            # or subtitle does not have supported extension - this is because function is sometimes triggered on converted file copied into that dir
            # FIXME - now we assume that .ass subtitle will not be processed
            del RecentSubsFiles[item]
    
    # check all remaining subtitle files for changed timestamp
    for f in RecentSubsFiles:
        pathfile = os.path.join(subtitlePath, f)
        epoch_file = xbmcvfs.Stat(pathfile).st_mtime()
        epoch_now = time.time()
        #Log("filename: " + pathfile)
        #Log("fileepoch: " + str(epoch_file))
        #Log("nowepoch:  " + str(epoch_now))

        if  epoch_file > epoch_now - 6:
            # Video filename matches subtitle filename and it was created/modified no later than 6 secods ago
            Log("New subtitle file detected: " + pathfile, xbmc.LOGNOTICE)

            # record start time of processing
            RoutineStartTime = time.time()

            # show busy animation
            # https://forum.kodi.tv/showthread.php?tid=280621&pid=2363462#pid2363462
            xbmc.executebuiltin('ActivateWindow(10138)')  # Busy dialog on

            # log time
            #Log("File time:    " + str(epoch_file))
            #Log("Current time: " + str(epoch_now))

            # hide subtitles
            xbmc.Player().showSubtitles(False)
            # pause playback
            if not xbmc.getCondVisibility("player.paused"):
                xbmc.Player().pause()
                Log("Playback PAUSED for subtitles conversion.", xbmc.LOGINFO)
            else:    
                Log("Playback already PAUSED.", xbmc.LOGINFO)

            # process subtitles file
            ResultFile = MangleSubtitles(pathfile) 
            Log("Output subtitles file: " + ResultFile, xbmc.LOGNOTICE) 

            # check if destination file exists
            if xbmcvfs.exists(ResultFile):
                Log("Subtitles available.", xbmc.LOGNOTICE)

                # load new subtitles and turn them on
                xbmc.Player().setSubtitles(ResultFile)
                    
                # resume playback
                if xbmc.getCondVisibility("player.paused"):
                    Log("Playback is paused. Resuming.", xbmc.LOGINFO)
                    xbmc.Player().pause()
                    Log("Playback RESUMED.", xbmc.LOGINFO)
                else:
                    Log("Playback not paused. No need to resume.", xbmc.LOGINFO)
            else:
                Log("Subtitles NOT available.", xbmc.LOGNOTICE)

            # hide busy animation
            # https://forum.kodi.tv/showthread.php?tid=280621&pid=2363462#pid2363462
            xbmc.executebuiltin('Dialog.Close(10138)')  # Busy dialog off

            # record end time of processing
            RoutineEndTime = time.time()
            
            # truncating seconds: https://stackoverflow.com/questions/8595973/truncate-to-3-decimals-in-python/8595991#8595991
            Log("Subtitles processing routine finished. Processing took: " + '%.3f'%(RoutineEndTime - RoutineStartTime) + " seconds.", xbmc.LOGNOTICE)
            
            # sleep for 10 seconds to avoid processing newly added subititle file
            xbmc.sleep(10000)

    # clearing process flag, process is not running any more
    DetectionIsRunning = False

    # restart timer
    #rt.start()



# get information on file currently being played
# http://kodi.wiki/view/InfoLabels
def GetPlayingInfo():

    # get seetings from Kodi configuration on assumed subtitles location
    storagemode = GetSubtitleSetting("storagemode") # 1=location defined by custompath; 0=location in movie dir
    custompath = GetSubtitleSetting("custompath")   # path to non-standard dir with subtitles

    if storagemode == 1:    # location == custompath
        if xbmcvfs.exists(custompath):
            subspath = custompath
        else:    # location == movie dir
            path = xbmc.translatePath("special://temp")
    else:   
        subspath = xbmc.getInfoLabel('Player.Folderpath')

    filefps = xbmc.getInfoLabel('Player.Process(VideoFPS)')
    filename = xbmc.getInfoLabel('Player.Filename')
    filepathname = xbmc.getInfoLabel('Player.Filenameandpath')

    Log("file currently played: " + filepathname, xbmc.LOGINFO)
    Log("subtitles download path: " + subspath, xbmc.LOGINFO)
    
    return subspath, filename, filepathname, filefps



#
# execution starts here
#
__addon__ = xbmcaddon.Addon(id='service.subsmangler')
__addondir__ = xbmc.translatePath(__addon__.getAddonInfo('path').decode("utf-8"))
__addonworkdir__ = xbmc.translatePath(__addon__.getAddonInfo('profile').decode('utf-8'))
__version__ = __addon__.getAddonInfo('version')


# path and file name of public definitions
global deffilename
deffileurl = "http://"


# list of input file extensions
# extensions in lowercase with leading dot
# FIXME - we do not include output extension .ass as conversion routine is sometimes wrongly triggered on converted subtitle file
SubExtList = [ '.txt', '.srt', '.sub' ]


if __name__ == '__main__':
    monitor = XBMCMonitor()
    player = XBMCPlayer()

    xbmc.log("SubsMangler: started. Version: %s" % (__version__), level=xbmc.LOGNOTICE)

    # prepare timer to launch
    rt = RepeatedTimer(3.0, DetectNewSubs)

    # set initial values
    DetectionIsRunning = False
    ClockTick = 0

    # load settings
    GetSettings()

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
        # check if auto-update is enabled and player does not play any content
        if setting_AutoUpdateDef and not xbmc.getCondVisibility('Player.HasMedia'):
            # autoupdate regexp definitions every 6 hours
            if ClockTick <=0:
                # download file from server

                # check if target path exists

                # delete old file, keep backup of 1 file

                # copy new file

                # reset timer to 6 hours
                # 1 tick per 5 sec * 60 min * 6 hrs = 4320 ticks
                ClockTick = 4320
        # decrease timer
        # avoid decreasing the timer to infinity
        if ClockTick > 0:
            ClockTick -= 1

        # set definitions file location
        if xbmcvfs.exists(os.path.join(__addonworkdir__, 'regexdef.txt')):
            # downloaded file is available
            deffilename = os.path.join(__addonworkdir__, 'regexdef.txt')
        else:
            # use sample file from addon's dir
            deffilename = os.path.join(__addondir__, 'resources', 'regexdef.txt')

