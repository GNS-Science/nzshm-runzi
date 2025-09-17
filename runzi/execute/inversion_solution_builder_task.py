import argparse
import datetime as dt
import json
import logging
import platform
import time
import urllib.parse
import uuid
from pathlib import PurePath

import git
from dateutil.tz import tzutc
from nshm_toshi_client.task_relation import TaskRelation
from py4j.java_gateway import GatewayParameters, JavaGateway

from runzi.automation.scaling.file_utils import download_files, get_output_file_id
from runzi.automation.scaling.local_config import API_KEY, API_URL, S3_URL, SPOOF_INVERSION, WORK_PATH
from runzi.automation.scaling.toshi_api import ToshiApi

logging.basicConfig(level=logging.INFO)

loglevel = logging.INFO
logging.getLogger('py4j.java_gateway').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_client_base').setLevel(loglevel)
logging.getLogger('nshm_toshi_client.toshi_file').setLevel(loglevel)
logging.getLogger('urllib3').setLevel(loglevel)
logging.getLogger('git.cmd').setLevel(loglevel)

log = logging.getLogger(__name__)


class BuilderTask:
    """
    Configure the python client for a InversionTask
    """

    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)

        # setup the java gateway binding
        self._gateway = JavaGateway(gateway_parameters=GatewayParameters(port=job_args['java_gateway_port']))
        # repos = ["opensha", "nzshm-opensha", "nzshm-runzi"]
        # self._repoheads = get_repo_heads(PurePath(job_args['root_folder']), repos)
        self._output_folder = PurePath(job_args.get('working_path'))

        if self.use_api:
            headers = {"x-api-key": API_KEY}
            self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)
            self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    def run(self, task_arguments, job_arguments):  # noqa: C901
    
        file_generator = get_output_file_id(toshi_api, rupture_set_id)  # for file by file ID
        rupture_sets = download_files(toshi_api, file_generator, str(work_path), overwrite=False)

        # Run the task....
        ta = task_arguments

        t0 = dt.datetime.utcnow()

        API_GitVersion = self._gateway.entry_point.getGitVersion()

        log.info(f"Running nzshm-opensha {API_GitVersion}")

        initial_solution_id = ta.get('initial_solution_id')
        if initial_solution_id:
            file_generator = get_output_file_id(self._toshi_api, initial_solution_id)
            initial_solution_info = download_files(self._toshi_api, file_generator, str(WORK_PATH), overwrite=False)

        environment = {"host": platform.node(), "nzshm-opensha.version": API_GitVersion}

        if self.use_api:
            # create new task in toshi_api
            task_id = self._toshi_api.automation_task.create_task(
                dict(
                    created=dt.datetime.now(tzutc()).isoformat(),
                    task_type="INVERSION",
                    model_type=ta['config_type'].upper(),
                ),
                arguments=task_arguments,
                environment=environment,
            )

            # link task to the parent task
            gt_conn = self._task_relation_api.create_task_relation(job_arguments['general_task_id'], task_id)
            log.info(
                f"created task_relationship: {gt_conn} for at: {task_id} on GT: {job_arguments['general_task_id']}"
            )

            # link task to the input datafiles
            input_file_id = task_arguments.get('rupture_set_file_id')
            if input_file_id:
                self._toshi_api.automation_task.link_task_file(task_id, input_file_id, 'READ')

            if initial_solution_id:
                self._toshi_api.automation_task.link_task_file(task_id, initial_solution_id, 'READ')

        else:
            task_id = str(uuid.uuid4())

        if ta['config_type'] == 'crustal':
            inversion_runner = self._gateway.entry_point.getCrustalInversionRunner()

            if ta.get('spatial_seis_pdf'):
                inversion_runner.setSpatialSeisPDF(str(ta.get('spatial_seis_pdf')))

            inversion_runner.setDeformationModel(ta['deformation_model'])
            inversion_runner.setGutenbergRichterMFD(
                float(ta['mfd_mag_gt_5_sans']),
                float(ta['mfd_mag_gt_5_tvz']),
                float(ta['mfd_b_value_sans']),
                float(ta['mfd_b_value_tvz']),
                float(ta['mfd_transition_mag']),
            )

            if ta.get('mfd_equality_weight') and ta.get('mfd_inequality_weight'):
                inversion_runner.setGutenbergRichterMFDWeights(
                    float(ta['mfd_equality_weight']), float(ta['mfd_inequality_weight'])
                )
            elif (ta.get('mfd_uncertainty_weight') and ta.get('mfd_uncertainty_power')) or (
                not ta.get('reweight') is None
            ):
                weight = 1 if ta.get('reweight') else ta.get('mfd_uncertainty_weight')
                inversion_runner.setUncertaintyWeightedMFDWeights(
                    float(weight),  # set default for reweighting
                    float(ta.get('mfd_uncertainty_power')),
                    float(ta.get('mfd_uncertainty_scalar')),
                )
            else:
                raise ValueError("Neither eq/ineq , nor uncertainty weights provided for MFD constraint setup")

            if not ta.get('enable_tvz_mfd') is None:
                inversion_runner.setEnableTvzMFDs(ta.get('enable_tvz_mfd'))

            minMagSans = float(ta['min_mag_sans'])
            minMagTvz = float(ta['min_mag_tvz'])
            inversion_runner.setMinMags(minMagSans, minMagTvz)

            maxMagSans = float(ta['max_mag_sans'])
            maxMagTvz = float(ta['max_mag_tvz'])
            maxMagType = ta['max_mag_type']
            inversion_runner.setMaxMags(maxMagType, maxMagSans, maxMagTvz)

            srf_sans = float(ta.get('sans_slip_rate_factor', 1.0))
            srf_tvz = float(ta.get('tvz_slip_rate_factor', 1.0))
            inversion_runner.setSlipRateFactor(srf_sans, srf_tvz)

            if not ta.get('reweight') is None:
                inversion_runner.setReweightTargetQuantity("MAD")

            if not ta.get('slip_use_scaling') is None:
                # V3x config
                weight = 1 if ta.get('reweight') else ta.get('slip_uncertainty_weight')
                inversion_runner.setSlipRateUncertaintyConstraint(
                    float(weight), float(ta.get('slip_uncertainty_scaling_factor'))  # set default for reweighting
                ).setUnmodifiedSlipRateStdvs(
                    not bool(ta.get('slip_use_scaling'))
                )  # True means no slips scaling and vice-versa
            elif ta.get('slip_rate_weighting_type') and ta['slip_rate_weighting_type'] == 'UNCERTAINTY_ADJUSTED':
                # Deprecated...
                inversion_runner.setSlipRateUncertaintyConstraint(
                    int(float(ta['slip_rate_weight'])), int(ta['slip_uncertainty_scaling_factor'])
                )
            elif ta.get('slip_rate_normalized_weight'):
                # covers UCERF3 style SR constraints
                inversion_runner.setSlipRateConstraint(
                    ta['slip_rate_weighting_type'],
                    float(ta['slip_rate_normalized_weight']),
                    float(ta['slip_rate_unnormalized_weight']),
                )
            else:
                raise ValueError(f"invalid slip constraint weight setup {ta}")

            if ta.get('paleo_rate_constraint_weight', 1):
                weight = 1 if ta.get('reweight') else ta.get('paleo_rate_constraint_weight')
                if ta.get('paleo_rate_constraint'):
                    inversion_runner.setPaleoRateConstraints(
                        float(weight),  # set default for reweighting
                        float(ta['paleo_parent_rate_smoothness_constraint_weight']),
                        ta['paleo_rate_constraint'],
                        ta['paleo_probability_model'],
                    )

        elif ta['config_type'] == 'subduction':
            inversion_runner = self._gateway.entry_point.getSubductionInversionRunner()
            inversion_runner.setDeformationModel(ta['deformation_model'])
            inversion_runner.setGutenbergRichterMFDWeights(
                float(ta['mfd_equality_weight']), float(ta['mfd_inequality_weight'])
            ).setSlipRateConstraint(
                ta['slip_rate_weighting_type'],
                float(ta['slip_rate_normalized_weight']),
                float(ta['slip_rate_unnormalized_weight']),
            )
            if ta['mfd_min_mag']:
                inversion_runner.setGutenbergRichterMFD(
                    float(ta['mfd_mag_gt_5']),
                    float(ta['mfd_b_value']),
                    float(ta['mfd_transition_mag']),
                    float(ta['mfd_min_mag']),
                )
            else:
                inversion_runner.setGutenbergRichterMFD(
                    float(ta['mfd_mag_gt_5']), float(ta['mfd_b_value']), float(ta['mfd_transition_mag'])
                )

            if ta.get('mfd_uncertainty_weight'):
                inversion_runner.setUncertaintyWeightedMFDWeights(
                    float(ta['mfd_uncertainty_weight']),
                    float(ta['mfd_uncertainty_power']),
                    float(ta.get('mfd_uncertainty_scalar')),
                )

        if ta.get('scaling_relationship') and ta.get('scaling_recalc_mag'):
            sr = self._gateway.jvm.nz.cri.gns.NZSHM22.opensha.calc.SimplifiedScalingRelationship()
            if ta.get('scaling_relationship') == "SIMPLE_CRUSTAL":
                sr.setupCrustal(float(ta.get('scaling_c_val_dip_slip')), float(ta.get('scaling_c_val_strike_slip')))
            elif ta.get('scaling_relationship') == "SIMPLE_SUBDUCTION":
                sr.setupSubduction(float(ta.get('scaling_c_val')))
            else:
                sr = ta.get('scaling_relationship')
            inversion_runner.setScalingRelationship(sr, bool(ta.get('scaling_recalc_mag')))

        inversion_runner.setInversionSeconds(
            int(float(ta['max_inversion_time']) * 60)
        ).setEnergyChangeCompletionCriteria(float(0), float(ta['completion_energy']), float(1)).setSelectionInterval(
            int(ta["selection_interval_secs"])
        ).setNumThreadsPerSelector(
            int(ta["threads_per_selector"])
        ).setNonnegativityConstraintType(
            ta['non_negativity_function']
        ).setPerturbationFunction(
            ta['perturbation_function']
        )

        inversion_runner.setRuptureSetFile(str(PurePath(job_arguments['working_path'], ta['rupture_set'])))

        if initial_solution_id:
            inversion_runner.setInitialSolution(initial_solution_info[initial_solution_id]['filepath'])

        if ta.get("averaging_threads"):
            inversion_runner.setInversionAveraging(int(ta["averaging_threads"]), int(ta["averaging_interval_secs"]))

        if ta.get('cooling_schedule'):
            inversion_runner.setCoolingSchedule(ta['cooling_schedule'])

        # int(ta['max_inversion_time'] * 60))\

        if not SPOOF_INVERSION:
            log.info("Starting inversion of up to %s minutes" % ta['max_inversion_time'])
            log.info("======================================")
            inversion_runner.runInversion()

        output_file = str(PurePath(job_arguments['working_path'], f"NZSHM22_InversionSolution-{task_id}.zip"))
        # name the output file
        # outputfile = self._output_folder.joinpath(inversion_runner.getDescriptiveName()+ ".zip")
        # log.info("building %s started at %s" % (outputfile, dt.datetime.utcnow().isoformat()), end=' ')

        # output_file = str(PurePath(job_arguments['output_file']))
        if not SPOOF_INVERSION:
            inversion_runner.writeSolution(output_file)
        else:
            with open(output_file, 'w') as spoof:
                spoof.write("this is spoofed solution")

        t1 = dt.datetime.utcnow()
        log.info("Inversion took %s secs" % (t1 - t0).total_seconds())

        # capture task metrics
        duration = (dt.datetime.utcnow() - t0).total_seconds()

        metrics = {"SPOOF_INVERSION": True}
        if not SPOOF_INVERSION:
            # fecth metrics and convert Java Map to python dict
            jmetrics = inversion_runner.getSolutionMetrics()
            for k in jmetrics:
                metrics[k] = jmetrics[k]

        if ta['config_type'] == 'subduction':
            table_rows_v1 = inversion_runner.getTabularSolutionMfds() if not SPOOF_INVERSION else []
            mfd_table_rows = {"MFD_CURVES": table_rows_v1}
        else:
            table_rows_v1 = inversion_runner.getTabularSolutionMfds() if not SPOOF_INVERSION else []
            table_rows_v2 = inversion_runner.getTabularSolutionMfdsV2() if not SPOOF_INVERSION else []
            mfd_table_rows = {"MFD_CURVES": table_rows_v1, "MFD_CURVES_V2": table_rows_v2}

        if self.use_api:
            # record the completed task
            done_args = {
                'task_id': task_id,
                'duration': duration,
                'result': "SUCCESS",
                'state': "DONE",
            }
            self._toshi_api.automation_task.complete_task(done_args, metrics)

            # and the log files, why not
            java_log_file = self._output_folder.joinpath(f"java_app.{job_arguments['java_gateway_port']}.log")
            # pyth_log_file = self._output_folder.joinpath(f"python_script.{job_arguments['java_gateway_port']}.log")
            self._toshi_api.automation_task.upload_task_file(task_id, java_log_file, 'WRITE')
            # self._toshi_api.automation_task.upload_task_file(task_id, pyth_log_file, 'WRITE')

            # upload the task output
            predecessors = [
                dict(id=task_arguments['rupture_set_file_id'], depth=-1),
            ]

            inversion_id = self._toshi_api.inversion_solution.upload_inversion_solution(
                task_id, filepath=output_file, meta=task_arguments, predecessors=predecessors, metrics=metrics
            )
            log.info(f"created inversion solution: {inversion_id}")

            # Get the MFD tables...
            if not SPOOF_INVERSION:
                for table_type, table_rows in mfd_table_rows.items():
                    mfd_table_id = None

                    mfd_table_data = []
                    for row in table_rows:
                        mfd_table_data.append([x for x in row])

                    result = self._toshi_api.table.create_table(
                        mfd_table_data,
                        column_headers=["series", "series_name", "X", "Y"],
                        column_types=["integer", "string", "double", "double"],
                        object_id=inversion_id,
                        table_name="Inversion Solution MFD table",
                        table_type=table_type,
                        dimensions=None,
                    )
                    mfd_table_id = result['id']
                    result = self._toshi_api.inversion_solution.append_hazard_table(
                        inversion_id,
                        mfd_table_id,
                        label="Inversion Solution MFD table",
                        table_type=table_type,
                        dimensions=None,
                    )
                    log.info(f"created & linked table: {mfd_table_id}")

        else:
            log.info(metrics)
        log.info("; took %s secs" % (dt.datetime.utcnow() - t0).total_seconds())


def get_repo_heads(rootdir, repos):
    result = {}
    for reponame in repos:
        repo = git.Repo(rootdir.joinpath(reponame))
        headcommit = repo.head.commit
        result[reponame] = headcommit.hexsha
    return result


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("config")
    args = parser.parse_args()

    try:
        # LOCAL and CLUSTER this is a file
        config_file = args.config
        f = open(args.config, 'r', encoding='utf-8')
        config = json.load(f)
    except FileNotFoundError:
        # for AWS this must be a quoted JSON string
        config = json.loads(urllib.parse.unquote(args.config))

    # maybe the JVM App is a little slow to get listening
    time.sleep(0.2)
    task = BuilderTask(config['job_arguments'])
    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(config['job_arguments']['task_id'] * 0.01)
    task.run(**config)
