# This file includes code for SubsMangler's context menu functionality

import os
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import common

# check if .noautosubs extension flag should be set or cleared
def main():
    """check if .noautosubs extension flag should be set or cleared
    """

    # get the path and name of file clicked onto
    filepathname = xbmc.getInfoLabel('ListItem.FileNameAndPath')
    # get the path of file clicked onto
    filepath = xbmc.getInfoLabel('ListItem.Path')

    common.Log("Context menu invoked on: " + filepathname.encode('utf-8'), xbmc.LOGINFO)
    # check if noautosubs file exists
    #TODO: fix clicking on collection
    #TODO: recognize clicking on the folder and then check the contents for 'noautosubs' file

    # do nothing if cliecked item is not a real file
    if not os.path.isfile(filepathname):
        return

    if (xbmcvfs.exists(os.path.join(filepath, "noautosubs"))):
        common.Log("'noautosubs' file exists: " + os.path.join(filepath, "noautosubs").encode('utf-8'), xbmc.LOGDEBUG)
        xbmcgui.Dialog().ok("Subtitles Mangler", common.__addonlang__(32101).encode('utf-8'), line2=filepath.encode('utf-8'), line3=common.__addonlang__(32102).encode('utf-8'))
    else:
        common.Log("'noautosubs' file does not exist in: " + filepath.encode('utf-8'), xbmc.LOGDEBUG)
        # check if .noautosubs extension exists
        filebase, fileext = os.path.splitext(filepathname)
        if (xbmcvfs.exists(filebase + ".noautosubs")):
            # extension flag is set for this file
            common.Log("'.noautosubs' file exists: " + filebase.encode('utf-8') + ".noautosubs   Opening YesNoDialog.", xbmc.LOGDEBUG)
            YesNoDialog = xbmcgui.Dialog().yesno("Subtitles Mangler", common.__addonlang__(32103).encode('utf-8'), line2=filepathname.encode('utf-8'), line3=common.__addonlang__(32104).encode('utf-8'), nolabel=common.__addonlang__(32042).encode('utf-8'), yeslabel=common.__addonlang__(32043).encode('utf-8'))
            # answering Yes clears the flag
            if YesNoDialog:
                common.Log("Answer is Yes. Deleting file: " + filebase.encode('utf-8') + ".noautosubs", xbmc.LOGDEBUG)
                # delete .noautosubs file
                try:
                    xbmcvfs.delete(filebase + ".noautosubs")
                except Exception as e:
                    common.Log("Delete failed: " + os.path.join(filebase, ".noautosubs").encode('utf-8'), xbmc.LOGERROR)
                    common.Log("  Exception: " + str(e.message), xbmc.LOGERROR)
            else:
                common.Log("Answer is No. Doing nothing.", xbmc.LOGDEBUG)
        else:
            # extension flag is not set for this file
            common.Log("'.noautosubs' file does not exist. Opening YesNoDialog.", xbmc.LOGDEBUG)
            YesNoDialog = xbmcgui.Dialog().yesno("Subtitles Mangler", common.__addonlang__(32105).encode('utf-8'), line2=filepathname.encode('utf-8'), line3=common.__addonlang__(32106).encode('utf-8'), nolabel=common.__addonlang__(32042).encode('utf-8'), yeslabel=common.__addonlang__(32043).encode('utf-8'))
            # answering Yes sets the flag
            if YesNoDialog:
                common.Log("Answer is Yes. Creating file: " + filebase.encode('utf-8') + ".noautosubs", xbmc.LOGDEBUG)
                # create .noautosubs file
                common.CreateNoAutoSubsFile(filebase)
            else:
                common.Log("Answer is No. Doing nothing.", xbmc.LOGDEBUG)



if __name__ == '__main__':
    main()