import argparse
import json
import os.path
import signal
from subprocess import Popen
from typing import Dict

from utilities import auto_int, naming_things, logging, parse_dma_info, parse_peripherals, csv_reset


# noinspection DuplicatedCode
def main():
    # region Parse arguments
    parser = argparse.ArgumentParser()

    parser.add_argument('recording_dir', type=str, help="Path to the directory with the full recording data.")
    parser.add_argument('analysis_dir', type=str, help="Path to the directory with the global analysis results.")

    parser.add_argument('openocd_cfg', type=str, help="Path to the openocd configuration file for the DuT.")

    parser.add_argument('ram_start', type=auto_int, help="Start address of the device RAM.")
    parser.add_argument('ram_size', type=auto_int, help="Size of the device RAM.")

    parser.add_argument('intercept_start', type=auto_int, help="Start address of the device peripheral region.")
    parser.add_argument('intercept_size', type=auto_int, help="Size of the device peripheral region.")

    parser.add_argument('work_dir', type=str, help="Working directory.")

    parser.add_argument('--grace', dest='abort_grace_steps', type=int, default=5,
                        help="Keep recording this many steps after aborts.")

    # TODO perhaps make an argument
    limit_by_pc = False

    args = parser.parse_args()
    # endregion

    # region Handle sig-kill and sig-term to kill subprocesses
    subprocesses: Dict[str, Popen] = dict()

    def kill_subprocesses(sig, frame):
        print("\tAttempting to kill sub-runs")
        process: Popen
        for name, process in subprocesses.items():
            print("\t\tRequesting `%s` to terminate." % name)
            process.terminate()
        if len(subprocesses) == 0:
            print("\t\tNo children found")

        for name, process in subprocesses.items():
            if process.poll():
                print("\t\tForcibly killing `%s`" % name)
                process.kill()

    signal.signal(signal.SIGINT, kill_subprocesses)
    signal.signal(signal.SIGTERM, kill_subprocesses)
    # endregion handle subprocesses

    dma_info_file = os.path.join(args.analysis_dir, naming_things.DMA_INFO_JSON)
    dma_info = parse_dma_info(dma_info_file)

    trigger_instruction = dma_info['start_instruction']

    original_recording = os.path.join(args.recording_dir, logging.RECORDING_CSV)

    run_item = 'set_addr_instruction'
    set_addr_instr = dma_info[run_item]
    run_a_run(run_item, set_addr_instr, args, limit_by_pc, original_recording, subprocesses, trigger_instruction)

    run_item = 'set_size_instruction'
    set_size_instruction = dma_info[run_item]
    run_a_run(run_item, set_size_instruction, args, limit_by_pc, original_recording, subprocesses, trigger_instruction)

    run_item = 'start_instruction'
    start_instruction = dma_info[run_item]
    run_a_run(run_item, start_instruction, args, limit_by_pc, original_recording, subprocesses, trigger_instruction)


def run_a_run(run_item, p1, args, limit_by_pc, original_recording, subprocesses, trigger_instruction):
    run_name = "run_%s" % run_item
    run_dir = os.path.join(args.work_dir, run_name + "/")
    if not os.path.exists(run_dir):
        os.mkdir(run_dir)
    csv_reset(run_dir)
    mock_regions = json.dumps([])
    # TODO make sure 4 bytes is ok.
    shim_regions = json.dumps([(p1['address'], 4)])
    parameters = [
        'python', './phases/recorder/run_once_wrapper.py',
        args.openocd_cfg,  # OpenOCD configuration
        str(args.ram_start), str(args.ram_size),  # RAM definition (snapshotting)
        str(args.intercept_start), str(args.intercept_size),  # Peripheral area (for MPU protecting)
        mock_regions,  # Shadow ban this peripheral
        shim_regions,  # Shadow ban this peripheral
        original_recording,  # Path to the OG trace
        str(args.abort_grace_steps),  # Grace steps
        str(True),  # Abort after deviating from the trace
        str(False),  # Do not abort after DMA (pc covers this)
        str(-1),  # Do not abort after loops (pc covers this)

        # For the first iteration we assume the PC is only visited once by the triggering instruction.
        str(trigger_instruction['pc']) if limit_by_pc else str(-1),
        str(-1) if limit_by_pc else str(trigger_instruction['index']),

        # Alternatively abort at the index where we assume DMA to begin
        # -1,
        # trigger_instruction['index'],

        str(30),  # Wait for at most 30s per step
        run_dir,
    ]
    # TODO check if we need to reboot?
    current_proc = Popen(parameters)
    subprocesses[run_name] = current_proc
    current_proc.wait()
    del subprocesses[run_name]


if __name__ == '__main__':
    main()
