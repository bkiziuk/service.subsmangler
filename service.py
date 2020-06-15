import os, xbmc
from resources.lib import globals
from resources.lib import smangler


# supplementary code to be run periodically from main loop
def SupplementaryServices():
    """Supplementary services that have to run periodically
    """

    # set definitions file location
    # dir is local, no need to use xbmcvfs()
    if os.path.isfile(globals.localdeffilename):
        # downloaded file is available
        deffilename = globals.localdeffilename
    else:
        # use sample file from addon's dir
        deffilename = globals.sampledeffilename

    # housekeeping services
    if globals.ClockTick <= 0 and not xbmc.getCondVisibility('Player.HasMedia'):
        # check if auto-update is enabled and player does not play any content
        if globals.setting_AutoUpdateDef:
            # update regexdef file
            smangler.UpdateDefFile()

        if globals.setting_AutoRemoveOldSubs:
            # clear old subtitle files
            smangler.RemoveOldSubs()

        # reset timer to 6 hours
        # 1 tick per 5 sec * 60 min * 6 hrs = 4320 ticks
        globals.ClockTick = 4320

    # decrease timer if player is idle
    # avoid decreasing the timer to infinity
    if globals.ClockTick > 0 and not xbmc.getCondVisibility('Player.HasMedia'):
        globals.ClockTick -= 1



# SubsMangler's service entry point
if __name__ == '__main__':
    # prepare plugin environment
    smangler.PreparePlugin()

    # monitor whether Kodi is running
    # http://kodi.wiki/view/Service_add-ons
    while not globals.monitor.abortRequested():
        # wait for about 5 seconds
        if globals.monitor.waitForAbort(5):
            # Abort was requested while waiting. The addon should exit
            globals.rt.stop()
            xbmc.log("SubsMangler: Abort requested. Exiting.", level=xbmc.LOGINFO)
            break

        # run supplementary code periodically
        SupplementaryServices()