import argparse
import json
import git
import os
import uuid
from pathlib import PurePath
import platform
import time
import urllib.parse

from py4j.java_gateway import JavaGateway, GatewayParameters
import datetime as dt
from dateutil.tz import tzutc
from types import SimpleNamespace

from nshm_toshi_client.rupture_generation_task import RuptureGenerationTask
from nshm_toshi_client.task_relation import TaskRelation

from runzi.automation.scaling.toshi_api import ToshiApi
from runzi.automation.scaling.local_config import (WORK_PATH, API_KEY, API_URL, S3_URL)

class BuilderTask():
    """
    Configure the python client for a InversionTask
    """
    def __init__(self, job_args):

        self.use_api = job_args.get('use_api', False)

        #setup the java gateway binding
        self._gateway = JavaGateway(gateway_parameters=GatewayParameters(port=job_args['java_gateway_port']))
        #repos = ["opensha", "nzshm-opensha", "nzshm-runzi"]
        #self._repoheads = get_repo_heads(PurePath(job_args['root_folder']), repos)
        self._output_folder = PurePath(job_args.get('working_path'))

        if self.use_api:
            headers={"x-api-key":API_KEY}
            self._task_relation_api = TaskRelation(API_URL, None, with_schema_validation=True, headers=headers)
            self._toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)

    def run(self, task_arguments, job_arguments):

        # Run the task....
        ta = task_arguments

        t0 = dt.datetime.utcnow()

        API_GitVersion = self._gateway.entry_point.getGitVersion()

        print(f"Running nzshm-opensha {API_GitVersion}")

        environment = {
            "host": platform.node(),
            #"gitref_opensha":self._repoheads['opensha'],
            #"gitref_nzshm-opensha":self._repoheads['nzshm-opensha'],
            #"gitref_nzshm-runzi":self._repoheads['nzshm-runzi']
            "nzshm-opensha.version": API_GitVersion
            }

        if self.use_api:
            #create new task in toshi_api
            task_id = self._toshi_api.automation_task.create_task(
                dict(
                    created=dt.datetime.now(tzutc()).isoformat(),
                    task_type="INVERSION",
                    model_type=ta['config_type'].upper(),
                    ),
                arguments=task_arguments,
                environment=environment
                )

            #link task tp the parent task
            self._task_relation_api.create_task_relation(job_arguments['general_task_id'], task_id)

            # #link task to the input datafile
            input_file_id = task_arguments.get('rupture_set_file_id')
            if input_file_id:
                self._toshi_api.automation_task.link_task_file(task_id, input_file_id, 'READ')

        else:
            task_id = str(uuid.uuid4())


        if ta['config_type'] == 'crustal':
            inversion_runner = self._gateway.entry_point.getCrustalInversionRunner()

            inversion_runner.setDeformationModel(ta['deformation_model'])
            inversion_runner.setGutenbergRichterMFD(
                    float(ta['mfd_mag_gt_5_sans']),
                    float(ta['mfd_mag_gt_5_tvz']),
                    float(ta['mfd_b_value_sans']),
                    float(ta['mfd_b_value_tvz']),
                    float(ta['mfd_transition_mag']))
            inversion_runner.setGutenbergRichterMFDWeights(
                    float(ta['mfd_equality_weight']),
                    float(ta['mfd_inequality_weight']))

            #set both the same for now
            minMagSans = minMagTvz = float(ta['seismogenic_min_mag'])
            inversion_runner.setMinMags(minMagSans, minMagTvz)

            if ta['slip_rate_weighting_type'] == 'UNCERTAINTY_ADJUSTED':
                inversion_runner.setSlipRateUncertaintyConstraint(
                    ta['slip_rate_weighting_type'],
                    int(float(ta['slip_rate_weight'])),
                    int(ta['slip_uncertainty_scaling_factor']))
            else:
                #covers UCERF3 style SR constraints
                inversion_runner.setSlipRateConstraint(ta['slip_rate_weighting_type'],
                    float(ta['slip_rate_normalized_weight']),
                    float(ta['slip_rate_unnormalized_weight']))

            if ta.get('paleo_rate_constraint_weight', 0):
                inversion_runner.setPaleoRateConstraints(
                    float(ta['paleo_rate_constraint_weight']),
                    float(ta['paleo_parent_rate_smoothness_constraint_weight']),
                    ta['paleo_rate_constraint'],
                    ta['paleo_probability_model'])

        elif ta['config_type'] == 'subduction':
            inversion_runner = self._gateway.entry_point.getSubductionInversionRunner()
            inversion_runner.setDeformationModel(ta['deformation_model'])
            inversion_runner.setGutenbergRichterMFDWeights(
                    float(ta['mfd_equality_weight']),
                    float(ta['mfd_inequality_weight']))\
                .setSlipRateConstraint(ta['slip_rate_weighting_type'],
                    float(ta['slip_rate_normalized_weight']),
                    float(ta['slip_rate_unnormalized_weight']))\
                .setGutenbergRichterMFD(
                    float(ta['mfd_mag_gt_5']),
                    float(ta['mfd_b_value']),
                    float(ta['mfd_transition_mag']))\
                .setUncertaintyWeightedMFDWeights(
                    float(ta['mfd_uncertainty_weight']),
                    float(ta['mfd_uncertainty_power']))

        if ta.get('scaling_relationship') and ta.get('scaling_recalc_mag'):
            sr = self._gateway.jvm.nz.cri.gns.NZSHM22.opensha.calc.SimplifiedScalingRelationship()
            if ta.get('scaling_relationship') == "SIMPLE_CRUSTAL":
                sr.setupCrustal(float(ta.get('scaling_c_val_dip_slip')),
                    float(ta.get('scaling_c_val_strike_slip')))
            elif ta.get('scaling_relationship') == "SIMPLE_SUBDUCTION":
                sr.setupSubduction(float(ta.get('scaling_c_val')))
            else:
                sr =ta.get('scaling_relationship')
            inversion_runner.setScalingRelationship(sr, bool(ta.get('scaling_recalc_mag')))

        inversion_runner\
            .setInversionSeconds(int(float(ta['max_inversion_time']) * 60))\
            .setEnergyChangeCompletionCriteria(float(0), float(ta['completion_energy']), float(1))\
            .setSelectionInterval(int(ta["selection_interval_secs"]))\
            .setNumThreadsPerSelector(int(ta["threads_per_selector"]))\
            .setNonnegativityConstraintType(ta['non_negativity_function'])\
            .setPerturbationFunction(ta['perturbation_function'])

        inversion_runner.setRuptureSetFile(str(PurePath(job_arguments['working_path'], ta['rupture_set'])))

        if ta.get("averaging_threads"):
            inversion_runner.setInversionAveraging(
                int(ta["averaging_threads"]),
                int(ta["averaging_interval_secs"]))

        #int(ta['max_inversion_time'] * 60))\

        print("Starting inversion of up to %s minutes" % ta['max_inversion_time'])
        print("======================================")
        inversion_runner.runInversion()

        output_file = str(PurePath(job_arguments['working_path'], f"NZSHM22_InversionSolution-{task_id}.zip"))
        #name the output file
        # outputfile = self._output_folder.joinpath(inversion_runner.getDescriptiveName()+ ".zip")
        # print("building %s started at %s" % (outputfile, dt.datetime.utcnow().isoformat()), end=' ')

        # output_file = str(PurePath(job_arguments['output_file']))
        inversion_runner.writeSolution(output_file)

        t1 = dt.datetime.utcnow()
        print("Inversion took %s secs" % (t1-t0).total_seconds())

        #capture task metrics
        duration = (dt.datetime.utcnow() - t0).total_seconds()

        metrics = {}
        #fecth metrics and convert Java Map to python dict
        jmetrics = inversion_runner.getSolutionMetrics()
        for k in jmetrics:
            metrics[k] = jmetrics[k]

        # metrics['moment_rate'] = inversion_runner.momentAndRateMetrics()
        # metrics['by_fault_name'] = inversion_runner.byFaultNameMetrics()
        # metrics['parent_fault_moment_rates'] = inversion_runner.parentFaultMomentRates()

        table_rows = inversion_runner.getTabularSolutionMfds()

        if self.use_api:
            #record the completed task
            done_args = {
             'task_id':task_id,
             'duration':duration,
             'result':"SUCCESS",
             'state':"DONE",
            }
            self._toshi_api.automation_task.complete_task(done_args, metrics)

            #and the log files, why not
            java_log_file = self._output_folder.joinpath(f"java_app.{job_arguments['java_gateway_port']}.log")
            self._toshi_api.automation_task.upload_task_file(task_id, java_log_file, 'WRITE')
            pyth_log_file = self._output_folder.joinpath(f"python_script.{job_arguments['java_gateway_port']}.log")
            self._toshi_api.automation_task.upload_task_file(task_id, pyth_log_file, 'WRITE')

            #upload the task output
            inversion_id = self._toshi_api.inversion_solution.upload_inversion_solution(task_id, filepath=output_file,
                meta=task_arguments, metrics=metrics)
            print("created inversion solution: ", inversion_id)

            # # now get the MFDS...
            mfd_table_id = None

            mfd_table_data = []
            for row in table_rows:
                mfd_table_data.append([x for x in row])

            result = self._toshi_api.table.create_table(
                mfd_table_data,
                column_headers = ["series", "series_name", "X", "Y"],
                column_types = ["integer","string","double","double"],
                object_id=inversion_id,
                table_name="Inversion Solution MFD table",
                table_type="MFD_CURVES",
                dimensions=None,
            )
            mfd_table_id = result['id']
            result = self._toshi_api.inversion_solution.append_hazard_table(inversion_id, mfd_table_id,
                label= "Inversion Solution MFD table",
                table_type="MFD_CURVES",
                dimensions=None,
            )
            print("created & linked table: ", mfd_table_id)

        else:
            print(metrics)
        print("; took %s secs" % (dt.datetime.utcnow() - t0).total_seconds())


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
        f= open(args.config, 'r', encoding='utf-8')
        config = json.load(f)
    except:
        # for AWS this must be a quoted JSON string
        config = json.loads(urllib.parse.unquote(args.config))

    # maybe the JVM App is a little slow to get listening
    time.sleep(5)
    task = BuilderTask(config['job_arguments'])
    # Wait for some more time, scaled by taskid to avoid S3 consistency issue
    time.sleep(config['job_arguments']['task_id'] * 0.666 * 2 * 4)
    task.run(**config)