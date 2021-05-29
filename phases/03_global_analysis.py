import argparse
import os

from phases.analyzer import ClusteringAnalyzer
from phases.recorder import ExecutionTrace, trace_logging
from utilities import auto_int


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('recording_dir', type=str, help="Path to the directory with the full recording data.")
    parser.add_argument('ram_base', type=auto_int, help="Base address (offset) of the start of the dump snapshots.")
    parser.add_argument(
        'epsilon',
        type=auto_int,
        help="Specify a minimal size criterion for peripheral clustering. Use 75% of the actual peripheral size for "
             "best results. (example: 0x300 based on 0x400)."
    )
    parser.add_argument('work_dir', type=str, help="Working directory.")

    args = parser.parse_args()
    # dump_dir = os.path.join(args.recording_dir, naming_things.MEMORY_SNAPSHOT_DIRECTORY)
    recording_json_path = os.path.join(args.recording_dir, trace_logging.RECORDING_JSON)
    entries: ExecutionTrace = ExecutionTrace.from_file(recording_json_path)

    if not os.path.exists(args.work_dir):
        os.mkdir(args.work_dir)

    if not os.path.isdir(args.work_dir):
        raise Exception("%s is not a directory." % args.work_dir)

    a = ClusteringAnalyzer(entries, args.ram_base, work_dir=args.work_dir)
    a.start(epsilon=args.epsilon)


if __name__ == '__main__':
    main()
