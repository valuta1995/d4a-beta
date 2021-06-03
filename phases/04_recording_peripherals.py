import argparse
import json
import os.path
import signal
from subprocess import Popen
from typing import Dict

from phases.analyzer.peripheral_row import PeripheralRow, Peripheral
from utilities import auto_int, naming_things
from phases.recorder import trace_logging, TraceEntry
from phases.analyzer.dma_info import DmaInfo

from utilities import restart_connected_devices


# noinspection DuplicatedCode
def main():
    # region Parse arguments
    parser = argparse.ArgumentParser()

    # parser.add_argument('recording_dir', type=str, help="Path to the directory with the full recording data.")
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
    dma_info: DmaInfo = DmaInfo.from_file(dma_info_file)
    if dma_info.index_of_first_incidence == -1:
        print("No DMA found, abandoning this step.")
        return

    instruction_with_first_incidence: TraceEntry = dma_info.execution_trace.entries[dma_info.index_of_first_incidence]
    first_incidence_pc = instruction_with_first_incidence.pc
    first_incidence_index = dma_info.index_of_first_incidence

    # original_recording = os.path.join(args.recording_dir, trace_logging.RECORDING_JSON)
    peripherals_path = os.path.join(args.analysis_dir, naming_things.PERIPHERAL_JSON_NAME)
    peripheral_row: PeripheralRow = PeripheralRow.from_file(peripherals_path)

    test_run_name = "test_run"
    test_proc = single_peripheral(args, first_incidence_index, first_incidence_pc, limit_by_pc, dma_info_file,
                                  Peripheral(-1, -1), test_run_name)
    subprocesses[test_run_name] = test_proc
    test_proc.wait()
    del subprocesses[test_run_name]

    for peripheral in peripheral_row.peripherals:
        peripheral_base = peripheral.start
        run_name = naming_things.create_peripheral_run_name(peripheral_base)
        current_proc = single_peripheral(args, first_incidence_index, first_incidence_pc, limit_by_pc, dma_info_file, peripheral, run_name)
        subprocesses[run_name] = current_proc
        current_proc.wait()
        del subprocesses[run_name]


def single_peripheral(
        args,
        first_incidence_index: int,
        first_incidence_pc: int,
        limit_by_pc: bool,
        dma_info_path: str,
        peripheral: Peripheral,
        run_name: str
):
    run_dir = os.path.join(args.work_dir, run_name + "/")
    if not os.path.exists(run_dir):
        os.mkdir(run_dir)
    # csv_reset(run_dir)
    mock_regions = json.dumps([(peripheral.start, peripheral.size)])
    shim_regions = json.dumps([])
    parameters = [
        'python', './phases/recorder/run_once_wrapper.py',
        args.openocd_cfg,  # OpenOCD configuration
        str(args.ram_start), str(args.ram_size),  # RAM definition (snapshotting)
        str(args.intercept_start), str(args.intercept_size),  # Peripheral area (for MPU protecting)
        mock_regions,  # Shadow ban this peripheral
        shim_regions,  # Shadow ban this peripheral
        dma_info_path,  # Path to the OG trace
        str(args.abort_grace_steps),  # Grace steps
        str(True),  # Abort after deviating from the trace
        str(False),  # Do not abort after DMA (pc covers this)
        str(-1),  # Do not abort after loops (pc covers this)

        # For the first iteration we assume the PC is only visited once by the triggering instruction.
        str(first_incidence_pc) if limit_by_pc else str(-1),
        str(-1) if limit_by_pc else str(first_incidence_index),

        # Alternatively abort at the index where we assume DMA to begin
        # -1,
        # trigger_instruction['index'],

        str(30),  # Wait for at most 30s per step
        run_dir,
        "--poison",
    ]
    restart_connected_devices()
    current_proc = Popen(parameters)
    return current_proc


if __name__ == '__main__':
    main()
