# This file includes code for SubsMangler's context menu functionality

import os
import xbmc
import xbmcgui
import xbmcvfs
from . import common # FIXME: error importing module, just infuriating

# check if .noautosubs extension flag or 'noautosubs' file should be set or cleared
def main():
    """check if .noautosubs extension flag or 'noautosubs' file should be set or cleared
    """

    # get the path and name of file clicked onto
    filepathname = xbmc.getInfoLabel('ListItem.FileNameAndPath')
    # get the path of file clicked onto
    filepath = xbmc.getInfoLabel('ListItem.Path')

    common.Log("Context menu invoked on: " + filepathname, xbmc.LOGINFO)

    # check if noautosubs file exists
    # do nothing if clicked item is not a real file
    protocols = ("videodb", "plugin")
    if filepathname.lower().startswith(tuple(p + '://' for p in protocols)):
        common.Log("Source not supported. Ignoring it.", xbmc.LOGINFO)
        return

    # check if clicked item is a folder
    if xbmc.getCondVisibility('ListItem.IsFolder'):
        # clicked item is a folder
        # check if folder contains noautosubs file
        if (xbmcvfs.exists(os.path.join(filepathname, "noautosubs"))):
            common.Log("'noautosubs' file exists: " + os.path.join(filepathname, "noautosubs   Opening YesNoDialog."), xbmc.LOGDEBUG)
            YesNoDialog = xbmcgui.Dialog().yesno("Subtitles Mangler", globals.__addonlang__(32107), line2=filepathname, line3=globals.__addonlang__(32104), nolabel=globals.__addonlang__(32042), yeslabel=globals.__addonlang__(32043))
            # answering Yes deletes the file
            if YesNoDialog:
                common.Log("Answer is Yes. Deleting file: " + os.path.join(filepathname, "noautosubs"), xbmc.LOGDEBUG)
                # delete noautosubs file
                common.DeleteFile(os.path.join(filepathname, "noautosubs"))
            else:
                common.Log("Answer is No. Doing nothing.", xbmc.LOGDEBUG)

        else:
            common.Log("'noautosubs' file does not exist in: " + filepathname + "   Opening YesNoDialog.", xbmc.LOGDEBUG)
            YesNoDialog = xbmcgui.Dialog().yesno("Subtitles Mangler", globals.__addonlang__(32108), line2=filepathname, line3=globals.__addonlang__(32106), nolabel=globals.__addonlang__(32042), yeslabel=globals.__addonlang__(32043))
            # answering Yes creates the file
            if YesNoDialog:
                common.Log("Answer is Yes. Creating file: " + os.path.join(filepathname, "noautosubs"), xbmc.LOGDEBUG)
                # create .noautosubs file
                common.CreateNoAutoSubsFile(os.path.join(filepathname, "noautosubs"))
            else:
                common.Log("Answer is No. Doing nothing.", xbmc.LOGDEBUG)

    else:
        # clicked item is a file
        # check if folder contains .noautosubs file
        if (xbmcvfs.exists(os.path.join(filepath, "noautosubs"))):
            common.Log("'noautosubs' file exists: " + os.path.join(filepath, "noautosubs   Opening Ok dialog."), xbmc.LOGDEBUG)
            xbmcgui.Dialog().ok("Subtitles Mangler", globals.__addonlang__(32101), line2=filepath, line3=globals.__addonlang__(32102))
        else:
            common.Log("'noautosubs' file does not exist in: " + filepath, xbmc.LOGDEBUG)
            # check if .noautosubs extension exists
            filebase, _fileext = os.path.splitext(filepathname)
            if (xbmcvfs.exists(filebase + ".noautosubs")):
                # extension flag is set for this file
                common.Log("'.noautosubs' file exists: " + filebase + ".noautosubs   Opening YesNoDialog.", xbmc.LOGDEBUG)
                YesNoDialog = xbmcgui.Dialog().yesno("Subtitles Mangler", globals.__addonlang__(32103), line2=filepathname, line3=globals.__addonlang__(32104), nolabel=globals.__addonlang__(32042), yeslabel=globals.__addonlang__(32043))
                # answering Yes clears the flag
                if YesNoDialog:
                    common.Log("Answer is Yes. Deleting file: " + filebase + ".noautosubs", xbmc.LOGDEBUG)
                    # delete .noautosubs file
                    common.DeleteFile(filebase + ".noautosubs")
                else:
                    common.Log("Answer is No. Doing nothing.", xbmc.LOGDEBUG)

            else:
                # extension flag is not set for this file
                common.Log("'.noautosubs' file does not exist. Opening YesNoDialog.", xbmc.LOGDEBUG)
                YesNoDialog = xbmcgui.Dialog().yesno("Subtitles Mangler", globals.__addonlang__(32105), line2=filepathname, line3=globals.__addonlang__(32106), nolabel=globals.__addonlang__(32042), yeslabel=globals.__addonlang__(32043))
                # answering Yes sets the flag
                if YesNoDialog:
                    common.Log("Answer is Yes. Creating file: " + filebase + ".noautosubs", xbmc.LOGDEBUG)
                    # create .noautosubs file
                    common.CreateNoAutoSubsFile(filebase + ".noautosubs")
                else:
                    common.Log("Answer is No. Doing nothing.", xbmc.LOGDEBUG)


if __name__ == '__main__':
    main()