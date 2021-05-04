import argparse
import os

from phases.analyzer import ClusteringAnalyzer
from phases.recorder import ExecutionTrace
from utilities import auto_int, naming_things, logging


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
    dump_dir = os.path.join(args.recording_dir, naming_things.MEMORY_SNAPSHOT_DIRECTORY)
    recording_csv = os.path.join(args.recording_dir, logging.RECORDING_CSV)
    entries: ExecutionTrace = ExecutionTrace.from_csv(recording_csv, dumps_dir=dump_dir)

    if not os.path.exists(args.work_dir):
        os.mkdir(args.work_dir)

    if not os.path.isdir(args.work_dir):
        raise Exception("%s is not a directory." % args.work_dir)

    a = ClusteringAnalyzer(entries, args.ram_base, work_dir=args.work_dir)
    a.start(epsilon=args.epsilon)


if __name__ == '__main__':
    main()
