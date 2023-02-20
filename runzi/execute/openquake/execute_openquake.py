"""Execute the openquake pin an external process."""
#!python3

import io
import subprocess
import logging
import shutil

from pathlib import Path
from openquake.commonlib.datastore import get_datadir

from runzi.automation.scaling.local_config import (WORK_PATH, SPOOF_HAZARD)


from runzi.util import archive
# from runzi.util.aws import decompress_config
# from runzi.execute.openquake.util import ( OpenquakeConfig, SourceModelLoader, build_sources_xml,
#     get_logic_tree_file_ids, get_logic_tree_branches, single_permutation )

log = logging.getLogger(__name__)


def execute_openquake(configfile, task_no, toshi_task_id):
    """Do the actusal openquake work."""
    toshi_task_id = toshi_task_id or "DUMMY_toshi_TASK_ID"
    output_path = Path(WORK_PATH, f"output_{task_no}")
    logfile = Path(output_path, f'openquake.{task_no}.log')

    if output_path.exists():
        shutil.rmtree(output_path)
    output_path.mkdir()

    oq_result = dict()

    if SPOOF_HAZARD:
        print("execute_openquake skipping SPOOF=True")
        oq_result['csv_archive']=Path(WORK_PATH, f"spoof-{task_no}.csv_archive.zip")
        oq_result['hdf5_archive']=Path(WORK_PATH, f"spoof-{task_no}.hdf5_archive.zip")
        oq_result['csv_archive'].touch()
        oq_result['hdf5_archive'].touch()
        return oq_result

    try:
        #
        #  oq engine --run /WORKING/examples/18_SWRG_INIT/4-sites_many-periods_vs30-475.ini -L /WORKING/examples/18_SWRG_INIT/jobs/BG_unscaled.log
        #
        cmd = ['oq', 'engine', '--run', f'{configfile}', '-L',  f'{logfile}']
        log.info(f'cmd 1: {cmd}')
        # oq_out = subprocess.run(cmd, capture_output=True)
        oq_out = subprocess.run(cmd)
        # log.info(oq_out.stdout.decode('UTF-8'))
        # log.info(oq_out.stderr.decode('UTF-8'))
        # if 'Filtered away all ruptures??' in oq_out.stderr.decode('UTF-8'):
        if False:
            # oq_result['csv_archive']=Path(WORK_PATH, f"spoof-{task_no}.csv_archive.zip")
            # oq_result['hdf5_archive']=Path(WORK_PATH, f"spoof-{task_no}.hdf5_archive.zip")
            # oq_result['csv_archive'].touch()
            # oq_result['hdf5_archive'].touch()
            oq_result['no_ruptures'] = True
        else:

            def get_last_task():
                """
                root@tryharder-ubuntu:/app# oq engine --lhc
                job_id |     status |          start_time |         description
                    6 |   complete | 2022-03-29 01:12:16 | 35 sites, few periods
                """

                cmd = ['oq', 'engine', '--lhc']
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
                out, err = p.communicate()

                fileish = io.StringIO()
                fileish.write(out.decode())
                fileish.seek(0)

                fileish.readline() #consume header
                #lines = fileish.readlines()
                for line in fileish.readlines():
                    print(line)
                    task = int(line.split("|")[0])

                return task

            #get the job ID
            last_task = get_last_task()
            oq_result['oq_calc_id'] = last_task


            #
            #  oq engine --export-outputs 12 /WORKING/examples/output/PROD/34-sites-few-CRU+BG
            #  cp /home/openquake/oqdata/calc_12.hdf5 /WORKING/examples/output/PROD
            #
            cmd = ['oq', 'engine', '--export-outputs', str(last_task), str(output_path)]
            log.info(f'cmd 2: {cmd}')
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL)
            oq_result['csv_archive'] = archive(output_path, Path(WORK_PATH, f'openquake_csv_archive-{toshi_task_id}.zip'))

            #clean up export outputs
            shutil.rmtree(output_path)

            OQDATA = Path(get_datadir())

            hdf5_file = f"calc_{last_task}.hdf5"
            oq_result['hdf5_archive'] = archive(Path(OQDATA, hdf5_file), Path(WORK_PATH, f'openquake_hdf5_archive-{toshi_task_id}.zip'))
      

    except Exception as err:
        log.error(f"err: {err}")

    log.info(f"oq_result {oq_result}")
    return oq_result

