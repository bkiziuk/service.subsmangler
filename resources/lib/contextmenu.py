import os
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

# check if .noautosubs extension flag should be set or cleared
def main():
    """check if .noautosubs extension flag should be set or cleared
    """

    __addon__ = xbmcaddon.Addon(id='service.subsmangler')
    __addonlang__ = __addon__.getLocalizedString


    # get the path and name of file clicked onto
    filepathname = xbmc.getInfoLabel('ListItem.FileNameAndPath')
    # get the path of file clicked onto
    filepath = xbmc.getInfoLabel('ListItem.Path')

    # check if noautosubs file exists
    if (xbmcvfs.exists(os.path.join(filepath, "noautosubs"))):
        xbmcgui.Dialog().ok("Subtitles Mangler", __addonlang__(32101).encode('utf-8'), line2=filepath.encode('utf-8'), line3=__addonlang__(32102).encode('utf-8'))
    else:
        # check if .noautosubs extension exists
        filebase, fileext = os.path.splitext(filepathname)
        if (xbmcvfs.exists(os.path.join(filebase, ".noautosubs"))):
            # extension flag is set for this file
            YesNoDialog = xbmcgui.Dialog().yesno("Subtitles Mangler", __addonlang__(32103).encode('utf-8'), line2=filepathname.encode('utf-8'), line3=__addonlang__(32104).encode('utf-8'), nolabel=__addonlang__(32042).encode('utf-8'), yeslabel=__addonlang__(32043).encode('utf-8'))
            # answering Yes clears the flag
            if YesNoDialog:
                # delete .noautosubs file
                try:
                    xbmcvfs.delete(filebase + ".noautosubs")
                except Exception as e:
                    xbmc.log("SubsMangler: Delete failed: " + os.path.join(filebase, ".noautosubs").encode('utf-8'), xbmc.LOGERROR)
                    xbmc.log("  Exception: " + str(e.message), xbmc.LOGERROR)
        else:
            # extension flag is not set for this file
            YesNoDialog = xbmcgui.Dialog().yesno("Subtitles Mangler", __addonlang__(32105).encode('utf-8'), line2=filepathname.encode('utf-8'), line3=__addonlang__(32106).encode('utf-8'), nolabel=__addonlang__(32042).encode('utf-8'), yeslabel=__addonlang__(32043).encode('utf-8'))
            # answering Yes sets the flag
            if YesNoDialog:
                # create .noautosubs file
                try:
                    f = xbmcvfs.File (filebase + ".noautosubs", 'w')
                    result = f.write("# This file was created by Subtitles Mangler.\n# Presence of this file prevents automatical opening of subtitles search dialog.")
                    f.close()
                except Exception as e:
                    xbmc.log("SubsMangler: Can not create noautosubs file.", xbmc.LOGERROR)
                    xbmc.log("  Exception: " + str(e.message), xbmc.LOGERROR)








if __name__ == '__main__':
    main()