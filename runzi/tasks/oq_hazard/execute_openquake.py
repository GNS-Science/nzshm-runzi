"""Execute the openquake pin an external process."""

import configparser
import io
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from runzi.automation.local_config import OQ_DATADIR, OQ_VENV, SPOOF, WORK_PATH
from runzi.automation.toshi_api.openquake_hazard.openquake_hazard_task import HazardTaskType
from runzi.utils import archive

log = logging.getLogger(__name__)


def _parse_winning_cfg_path(oq_info_cfg_output: str) -> Path | None:
    """Return the config file OpenQuake reads last (and so wins) from ``oq info cfg`` output.

    ``oq info cfg`` prints ``Looking at the following paths (the last wins)`` then one path per line
    (a config dump may follow). We take the last line ending in ``openquake.cfg``; ``None`` if none.
    """
    paths = [line.strip() for line in oq_info_cfg_output.splitlines() if line.strip().endswith('openquake.cfg')]
    return Path(paths[-1]) if paths else None


def _set_oq_num_cores(cfg_path: Path, num_cores: int) -> None:
    """Set ``[distribution] num_cores`` in ``cfg_path`` (merge-safe), creating the file/dir if needed.

    OpenQuake merges its config search path last-wins, so writing ``num_cores`` into the winning file caps
    the processpool regardless of the installed defaults. Existing sections/keys are preserved.
    """
    parser = configparser.ConfigParser()
    if cfg_path.exists():
        parser.read(cfg_path)
    if not parser.has_section('distribution'):
        parser.add_section('distribution')
    parser.set('distribution', 'num_cores', str(num_cores))
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg_path.open('w') as handle:
        parser.write(handle)


def _num_cores_cap(num_cores: int | None) -> int | None:
    """The core cap to actually apply, or ``None`` to leave OpenQuake to auto-detect.

    Cap **only inside AWS Batch** (``AWS_BATCH_JOB_ID`` set): there the container can see the host's cores
    (CPU shares, not cpuset) and its openquake.cfg is ephemeral, so pinning is both needed and safe. On a
    local/dev host we must NOT cap — OQ already detects the machine's cores correctly, and writing
    ``num_cores`` would throttle the user *and* persistently rewrite their real openquake.cfg.
    """
    if num_cores is None or not os.environ.get('AWS_BATCH_JOB_ID'):
        return None
    return num_cores


def _cap_oq_num_cores(num_cores: int, oq_bin: str, env: dict[str, str]) -> None:
    """Cap OpenQuake's processpool to ``num_cores`` in the config file it reads last.

    On AWS Batch EC2 the container sees the host's cores (CPU shares, not cpuset), so OQ would otherwise
    size its pool to the whole instance and OOM a memory-capped container (#344). We discover the winning
    cfg path from ``oq info cfg`` (adapts to the container's HOME) and patch ``num_cores`` into it, falling
    back to ``{OQ_VENV}/openquake.cfg`` (always in the search path) if the path can't be parsed.
    """
    cfg_path: Path | None = None
    try:
        out = subprocess.run([oq_bin, 'info', 'cfg'], env=env, capture_output=True, text=True, check=True).stdout
        cfg_path = _parse_winning_cfg_path(out)
    except (subprocess.SubprocessError, OSError) as err:
        log.warning('could not run `oq info cfg` to find the config path: %s', err)
    if cfg_path is None:
        cfg_path = Path(f'{OQ_VENV}/openquake.cfg')
    log.info('capping OpenQuake num_cores=%d in %s', num_cores, cfg_path)
    _set_oq_num_cores(cfg_path, num_cores)


def execute_openquake(
    configfile: str | Path,
    task_no: int,
    toshi_task_id: str | None,
    hazard_task_type: HazardTaskType,
    num_cores: int | None = None,
):
    """Do the actual openquake work.

    Args:
        configfile: path to the OpenQuake job ini file
        task_no: the task number
        toshi_task_id: the Toshi API task ID
        hazard_task_type: Classical or Disaggregation
        num_cores: cap OpenQuake's processpool to this many cores, but **only inside AWS Batch** (see
            ``_num_cores_cap``). Needed on Batch EC2, where the container sees the host's cores and would
            otherwise OOM. Ignored on a local host, so a local run never has its cores throttled or its
            openquake.cfg rewritten. ``None`` always leaves OQ to auto-detect.
    """
    if not OQ_VENV:
        raise RuntimeError('NZSHM22_OQ_VENV must be set for OQ tasks')
    if not OQ_DATADIR:
        raise RuntimeError('NZSHM22_OQ_DATADIR must be set for OQ tasks')
    oq_bin = f'{OQ_VENV}/bin/oq'
    toshi_task_id = toshi_task_id or f"DUMMY{task_no}_toshi_TASK_ID"
    # if not toshi_task_id:
    #     toshi_task_id = f"DUMMY{task_no}_toshi_TASK_ID"
    output_path = Path(WORK_PATH, f"output_{task_no}")
    logfile = Path(output_path, f'openquake.{task_no}.log')

    if output_path.exists():
        shutil.rmtree(output_path)
    output_path.mkdir()

    oq_result: dict[str, Any] = dict()

    if SPOOF:
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
        env = {**os.environ, 'OQ_DATADIR': str(OQ_DATADIR)}
        cap = _num_cores_cap(num_cores)  # Batch-only; never touch a local host's cores or openquake.cfg
        if cap is not None:
            _cap_oq_num_cores(cap, oq_bin, env)
        cmd = [oq_bin, 'engine', '--run', f'{configfile}', '-L', f'{logfile}']
        log.info('executing with subprocess: %s', cmd)
        result = subprocess.run(cmd, env=env)
        if result.returncode != 0:
            raise RuntimeError(f'oq engine --run exited {result.returncode} for task {task_no}; see {logfile}')

        with open(logfile) as logf:
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

                cmd = [oq_bin, 'engine', '--lhc']
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, env=env)
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
            cmd = [oq_bin, 'engine', '--export-outputs', str(last_task), str(output_path)]
            log.info('executing with subprocess: %s', cmd)
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL, env=env)
            oq_result['csv_archive'] = archive(
                output_path, Path(WORK_PATH, f'openquake_csv_archive-{toshi_task_id}.zip')
            )

            # clean up export outputs
            shutil.rmtree(output_path)

            OQDATA = Path(OQ_DATADIR)  # type: ignore[arg-type]  # guarded by module-level RuntimeError

            hdf5_file = f"calc_{last_task}.hdf5"
            oq_result['hdf5_archive'] = archive(
                Path(OQDATA, hdf5_file), Path(WORK_PATH, f'openquake_hdf5_archive-{toshi_task_id}.zip')
            )
            oq_result['hdf5_filepath'] = Path(OQDATA, hdf5_file)

    except Exception as err:
        log.error('err: %s', err)

    log.info('oq_result %s', oq_result)
    return oq_result
