import csv
from pathlib import Path

from runzi.runners.run_save_file_archive import process_one_file


def run_save_bg_file_archives(search_dir, archive_table_fn, dry_run):

    with open(archive_table_fn, 'w') as csvfile:
        writer = csv.writer(csvfile, delimiter=',')
        writer.writerow(('regime', 'seismicity_model', 'bvalue', 'Nvalue', 'file name', 'file ID'))
        for child in search_dir.iterdir():
            if 'B' in str(child):
                tag = child.name
                for file_name in child.iterdir():
                    if file_name.suffix == '.xml':
                        if 'INT_puy' in file_name.name:
                            regime = 'interface_puysegur'
                        elif 'CRU' in file_name.name:
                            regime = 'crust'
                            if 'plyadj' in file_name.name:
                                regime += '_poly_adjusted'
                            if 'ratestapered' in file_name.name:
                                regime += '_rates_tapered'
                        b = str(file_name).split('_')[-2][1:]
                        N = str(file_name).split('_')[-1][1:-4]
                        target = str(file_name)
                        print(tag, file_name.name, target)
                        file_id = process_one_file(dry_run, target, tag)
                        writer.writerow([regime, tag, b, N, file_name.name, file_id])


def single_directory_crawl(search_dir, archive_table_fn, dry_run):

    with open(archive_table_fn, 'w') as csvfile:
        writer = csv.writer(csvfile, delimiter=',')
        writer.writerow(('tag', 'file name', 'file ID'))
        for file_path in search_dir.iterdir():
            if 'polygon' in str(file_path):
                tag = file_path.name
                target = str(file_path)
                print(tag, file_path.name, target)
                file_id = process_one_file(dry_run, target, tag)
                writer.writerow([tag, file_path.name, file_id])


if __name__ == "__main__":

    dry_run = False

    archive_table_fn = 'noNB_dist_seis.csv'
    root_dir = Path('/home/chrisdc/NSHM/DEV/nz-oq-distrseis/distseis')
    poi_dir = Path(root_dir, 'version3')
    CRU_dir = Path(root_dir, 'version3/Floor_MULTOT1346GruEEPAScomb')
    run_save_bg_file_archives(CRU_dir, archive_table_fn, dry_run)

    # archive_table_fn = 'zero_poly_dist_seis_PROD.csv'
    # poly_zero_dir =
    # Path('/home/chrisdc/NSHM/DEV/nz-oq-distrseis/distseis/version1/Floor_AddoptiEEPAScomb/polyadjusted2zero')
    # single_directory_crawl(poly_zero_dir, archive_table_fn, dry_run)
