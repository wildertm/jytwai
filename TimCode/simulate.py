#################################################################################
#  This file is part of The AI Sandbox.
#
#  Copyright (c) 2007-2012, AiGameDev.com
#
#  Credits:         See the PEOPLE file in the base directory.
#  License:         This software may be used for your own personal research
#                   and education only.  For details, see the LICENSING file.
#################################################################################

import bootstrap, sys, os

from aisbx import platform
from aisbx import callstack

from game.application import CaptureTheFlag


# By default load these commanders.
defaults = ['autocmd.learning', 'autocmd.learning']


def main(PreferedRunner, args, **kwargs):
    """
        Setup our custom demo application, as well as a window-mode runner,
        and launch it.  This function returns once the demo is over.
            - If RCTRL+R is pressed, the application is restarted.
            - On RCTRL+F, the game code is dynamically refreshed.
    """
    
    while True:
        runner = PreferedRunner()

        if not args:
            args = defaults
        app = CaptureTheFlag(args, **kwargs)
        if not runner.run(app):
            break
        r = app.reset
        del runner
        del app

        if not r:
            break
        else:
            import gc
            gc.collect()

            from reload import reset
            reset()


# This is the entry point for the whole application.  The main function is
# called only when the module is first executed.  Subsequent resetting or
# refreshing cannot automatically update this __main__ module.
if __name__ == '__main__':
    import sys
    import argparse
    print 'BLUE TEAM BOT ID IN SIMULATE: ', os.environ['blue_team_bot_id']
          
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--console', action='store_true', default=False,            
                help='Run the simulation in headless mode without opening a graphical window, logging information to the console instead.')
    parser.add_argument('-m', '--map', default='map21',
                help='Specify which level map should be loaded, e.g. map00 or map21.  These are loaded from the .png and .ini file combination in #/assets/.')
    parser.add_argument('competitors', nargs='*',
                help='The name of a script and class (e.g. mybot.Placeholder) implementing the Commander interface.  Files are exact, but classes match by substring.')
    args, _ = parser.parse_known_args()

    try:
        if args.console:
            main(platform.ConsoleRunner, args.competitors, map=args.map)
        else:
            main(platform.WindowRunner, args.competitors, map=args.map)

    except Exception as e:
        print str(e)
        tb_list = callstack.format(sys.exc_info()[2])
        for s in tb_list:
            print s
        raise

