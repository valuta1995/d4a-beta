import time
from typing import Callable


def flush_input():
    # try:
    #     import msvcrt
    #     while msvcrt.kbhit():
    #         msvcrt.getch()
    # except ImportError:
    #     import sys
    #     import termios  # for linux/unix
    #     termios.tcflush(sys.stdin, termios.TCIOFLUSH)
    pass


def get_restart_function() -> Callable:
    def restart_request():
        flush_input()
        input("Disconnect and reconnect the device under test and hit [enter] to continue.")
        print("Moving on...")

    try:  # Try to test import
        from pykush.pykush import YKUSH, YKUSHNotFound

        try:  # Try to open YKUSH device
            ykush = YKUSH()

            def restart_ykush():
                ykush.set_allports_state_down()
                time.sleep(1.5)
                ykush.set_allports_state_up()
                time.sleep(3.0)

            return restart_ykush

        except YKUSHNotFound:
            return restart_request

    except ImportError:
        return restart_request


__restart_connected_devices: Callable[[], None] = get_restart_function()


def restart_connected_devices():
    __restart_connected_devices()
