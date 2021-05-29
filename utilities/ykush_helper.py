import os
import time
from typing import Callable, Optional


def restart_connected_devices():
    success: bool = False
    try:
        from pykush.pykush import YKUSH, YKUSHNotFound
        ykush: Optional[YKUSH] = None
        try:
            ykush = YKUSH()
            print("Ykush going down.")
            ykush.set_allports_state_down()
            time.sleep(3)
            print("Ykush coming up.")
            ykush.set_allports_state_up()
            time.sleep(6)
            success = True

        except YKUSHNotFound:
            print("Could not find Ykush. If you have one make sure you have it set up")
        except OSError:
            print("Failed to open the Ykush. If you have one set up, make sure the user has access (plugdev?)")
        finally:
            if ykush is not None:
                del ykush
    except ImportError:
        success = False
        # noinspection PyUnusedLocal,PyPep8Naming
        YKUSH = None
        # noinspection PyUnusedLocal,PyPep8Naming
        YKUSHNotFound = None
        print("Could not import the Ykush library, if you want to use it, make sure to install it.")

    if not success:
        input("Disconnect and reconnect the device under test and hit [enter] to continue.")
    print("Restart completed.")
