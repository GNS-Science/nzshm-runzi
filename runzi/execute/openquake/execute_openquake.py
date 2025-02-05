"""Execute the openquake pin an external process."""

import io
import logging
import shutil
import subprocess
from pathlib import Path

from runzi.automation.scaling.toshi_api.openquake_hazard.openquake_hazard_task import HazardTaskType

try:
    from openquake.commonlib.datastore import get_datadir
except ImportError:
    print("openquake not installed, not importing")

from runzi.automation.scaling.local_config import SPOOF_HAZARD, WORK_PATH
from runzi.util import archive

log = logging.getLogger(__name__)


def execute_openquake(configfile, task_no, toshi_task_id, hazard_task_type):
    """Do the actusal openquake work."""
    toshi_task_id = toshi_task_id or f"DUMMY{task_no}_toshi_TASK_ID"
    # if not toshi_task_id:
    #     toshi_task_id = f"DUMMY{task_no}_toshi_TASK_ID"
    output_path = Path(WORK_PATH, f"output_{task_no}")
    logfile = Path(output_path, f'openquake.{task_no}.log')

    if output_path.exists():
        shutil.rmtree(output_path)
    output_path.mkdir()

    oq_result = dict()

    if SPOOF_HAZARD:
        print("execute_openquake skipping SPOOF=True")
        oq_result['csv_archive'] = Path(WORK_PATH, f"spoof-{task_no}.csv_archive.zip")
        oq_result['hdf5_archive'] = Path(WORK_PATH, f"spoof-{task_no}.hdf5_archive.zip")
        oq_result['csv_archive'].touch()
        oq_result['hdf5_archive'].touch()
        return oq_result

    try:
        #
        #  oq engine --run /WORKING/examples/18_SWRG_INIT/4-sites_many-periods_vs30-475.ini
        # -L /WORKING/examples/18_SWRG_INIT/jobs/BG_unscaled.log
        #
        cmd = ['oq', 'engine', '--run', f'{configfile}', '-L', f'{logfile}']
        log.info(f'cmd 1: {cmd}')
        subprocess.run(cmd)

        with open(logfile, 'r') as logf:
            oq_out = logf.read()

        filtered_txt1 = 'Filtered away all ruptures??'
        filtered_txt2 = 'There are no ruptures close to the site'
        filtered_txt3 = 'The site is far from all seismic sources'
        if (
            'error' in oq_out.lower()
            and (filtered_txt1 not in oq_out)
            and (filtered_txt2 not in oq_out)
            and (filtered_txt3 not in oq_out)
        ):
            raise Exception("Unknown error encountered by openquake")
        if hazard_task_type is HazardTaskType.DISAGG:
            # filtered = (filtered_txt1 in /q_out) or (filtered_txt2 in oq_out) or (filtered_txt3 in oq_out) or
            # (re.findall('No \[.*\] contributions for site', oq_out))
            filtered = filtered_txt3 in oq_out
        else:
            filtered = (filtered_txt1 in oq_out) or (filtered_txt2 in oq_out) or (filtered_txt3 in oq_out)

        if filtered:
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

                fileish.readline()  # consume header
                # lines = fileish.readlines()
                for line in fileish.readlines():
                    print(line)
                    task = int(line.split("|")[0])

                return task

            # get the job ID
            last_task = get_last_task()
            oq_result['oq_calc_id'] = last_task

            #
            #  oq engine --export-outputs 12 /WORKING/examples/output/PROD/34-sites-few-CRU+BG
            #  cp /home/openquake/oqdata/calc_12.hdf5 /WORKING/examples/output/PROD
            #
            cmd = ['oq', 'engine', '--export-outputs', str(last_task), str(output_path)]
            log.info(f'cmd 2: {cmd}')
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL)
            oq_result['csv_archive'] = archive(
                output_path, Path(WORK_PATH, f'openquake_csv_archive-{toshi_task_id}.zip')
            )

            # clean up export outputs
            shutil.rmtree(output_path)

            OQDATA = Path(get_datadir())

            hdf5_file = f"calc_{last_task}.hdf5"
            oq_result['hdf5_archive'] = archive(
                Path(OQDATA, hdf5_file), Path(WORK_PATH, f'openquake_hdf5_archive-{toshi_task_id}.zip')
            )

    except Exception as err:
        log.error(f"err: {err}")

    log.info(f"oq_result {oq_result}")
    return oq_result
