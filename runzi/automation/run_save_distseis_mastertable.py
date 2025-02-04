#! python run_save_file.py
"""
a utility script to zip and save a file (with optional tag metadata) as a ToshiAPI File object

inputs:-
 - a path to the source file
 - tag to include in meta data
 - For ToshiAPI pass the ENV settings for the intended environment (PROD,TEST LOCAL)
 - option to use csv list produced by nz-oq-distseis/list_nrmls.py script.

"""
import argparse
import collections
import csv
import logging
from pathlib import Path

from runzi.automation.run_save_file_archive import create_archive, is_valid, process_one_file

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

VALID_ROW = ['regime','seismicity_model','bvalue','Nvalue','xmlfile']
VALID_ROW_OUT = VALID_ROW + ['toshi_id']

InputDataRow = collections.namedtuple('InputDataRow', VALID_ROW)
OutputDataRow = collections.namedtuple('OutputDataRow', VALID_ROW_OUT)

def process_masterfile(args):

    distseis_parent = Path(args.masterfile).parent.parent.parent
    with open(args.masterfile, 'r') as csvfile:
        reader = csv.reader(csvfile)
        header = next(reader)
        header = list(map(lambda x: x.replace('-', '_'), header)) # deal with hyphens

        if not header == VALID_ROW:
            log.error(f'file {arg.masterfile} is not in the correct format.')

        for dr in map(lambda x: InputDataRow(*x), reader):
            filepath = Path(distseis_parent, dr.xmlfile)
            print(filepath)
            toshi_id = process_one_file(args.dry_run, filepath, tag=args.tag)
            yield OutputDataRow(*dr, toshi_id=toshi_id)

def parse_args():
    parser = argparse.ArgumentParser(description="""take masterfile frm nz-oq-disteis save each entry a ToshiAPI File object""")
    parser.add_argument("masterfile", help=f"the path for the input csv file, which must have header: {VALID_ROW}")
    parser.add_argument("-t", "--tag", help = "add tag to metadata")
    parser.add_argument("-D", "--dry-run", action="store_true", help = f"mock run")
    parser.add_argument("-o", "--output_csv_file",
        help = f"write out CSV, adding toshi_id to input csv")
    args = parser.parse_args()
    return args


def main():
    args = parse_args()

    processed =  process_masterfile(args)

    #write the output
    if args.output_csv_file:
        with open(args.output_csv_file, 'w', newline='') as csvfile:
            _writer = csv.writer(csvfile)
            _writer.writerow(VALID_ROW_OUT) #  header row
            for p in processed:
                _writer.writerow( list(p._asdict().values()))

if __name__ == "__main__":
    main()

