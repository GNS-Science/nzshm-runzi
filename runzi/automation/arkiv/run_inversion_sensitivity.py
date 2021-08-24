
import os
import sys
from io import StringIO
from pathlib import PurePath
from pathlib import Path
import datetime as dt

from itertools import permutations
from dateutil.tz import tzutc
from py4j.java_gateway import JavaGateway, java_import

def report_meta():
    src_folder = PurePath("/tmp")

    filenames = """
    /tmp/CFM_hk_slipdef0_scaling_TMG_solution_TEST_Non0_10m.zip
    /tmp/CFM_hk_slipdef0_scaling_TMG_solution_TEST_Non0_eq1000_ineq_10m.zip
    /tmp/CFM_hk_slipdef0_scaling_TMG_solution_TEST_Non0_eq100_ineq100_10m.zip
    /tmp/CFM_hk_slipdef0_scaling_TMG_solution_TEST_Non0_eq100_ineq100_minRRF0.1_10m.zip
    /tmp/CFM_hk_slipdef0_scaling_TMG_solution_TEST_Non0_eq100_ineq100_minRRF0_90m.zip
    /tmp/CFM_hk_slipdef0_scaling_TMG_solution_TEST_Non0_m5-3_eq100_ineq100_minRRF0_10m.zip
    /tmp/CFM_hk_slipdef0_scaling_TMG_solution_TEST_Non0_m5-3_eq100_ineq100_minRRF0_bval0.94_2m_sf.zip
    /tmp/CFM_hk_slipdef0_scaling_TMG_solution_TEST_Non0_m5-3_eq100_ineq100_minRRF0_bval0.94_480m.zip
    /tmp/CFM_hk_slipdef0_scaling_TMG_solution_TEST_Non0_m5-3_eq10_ineq1000_minRRF0_10m.zip
    /tmp/CFM_hk_slipdef0_scaling_TMG_solution_TEST_Non0_m5-3_eq10_ineq1000_minRRF0_bval0.94_180m.zip
    /tmp/CFM_hk_slipdef0_scaling_TMG_solution_TEST_Non0_m5-3_eq10_ineq1000_minRRF0_bval0.94_2m_sf.zip
    /tmp/CFM_hk_slipdef0_scaling_TMG_solution_TEST_Non0_m5-40_eq100_ineq100_minRRF0_10m.zip
    /tmp/CFM_hk_slipdef0_scaling_TMG_solution_TEST_Non0_m5-5_eq100_ineq100_minRRF0_10m.zip
    """

    paths = StringIO(filenames)

    for path in paths.readlines():
        filepath = path.strip()
        report_name = filepath.replace('/tmp/CFM_hk_slipdef0_scaling_TMG_solution_TEST_Non0_', '')[:-4]
        yield (report_name, filepath)

def run_inversion(mfd_eq_wt, mfd_ineq_wt, output_folder, duration):

    solution_file = "MFD_weight_sensitivity_solution_eq(%04d)_ineq(%04d)_dur(%03d).zip" % (mfd_eq_wt, mfd_ineq_wt, duration)
    solution_path = output_folder.joinpath(solution_file)

    Path(str(output_folder)).mkdir(parents=True, exist_ok=True)

    #write to this file
    run_results = open(output_folder.joinpath("run_results.md"), 'w')

    print("Starting inversion of up to %s minutes" % duration)
    print("======================================")

    t0 = dt.datetime.utcnow()
    inversion_runner = app.getRunner()

    inversion_runner\
                .setInversionMinutes(duration)\
                .setEnergyChangeCompletionCriteria(float(0), float(0.001), float(1))\
                .setNumThreads(12)\
                .setSyncInterval(30)

    # .setSlipRateConstraint(sliprate_weighting.NORMALIZED_BY_SLIP_RATE, float(100), float(10))\
    inversion_runner\
        .setRuptureSetFile(RUPTURE_FILE)\
        .setGutenbergRichterMFDWeights(float(mfd_eq_wt), float(mfd_ineq_wt))\
        .setSlipRateUncertaintyConstraint(sliprate_weighting.UNCERTAINTY_ADJUSTED, 1000, 2)\
        .configure()\
        .runInversion()

    t1 = dt.datetime.utcnow()
    print("Inversion took %s secs" % (t1-t0).total_seconds())

    run_results.write("## Inversion run metrics\n\n")
    run_results.write("### %s\n\n" % solution_file)

    info = inversion_runner.completionCriteriaMetrics()
    run_results.writelines(info)

    info = inversion_runner.momentAndRateMetrics()
    run_results.writelines(info)

    info = inversion_runner.byFaultNameMetrics()
    run_results.writelines(info)

    info = inversion_runner.parentFaultMomentRates()
    run_results.writelines(info)
    run_results.close()

    inversion_runner.writeSolution(str(solution_path))
    print("Wrote to file: " + str(solution_path))

    return str(solution_path)


class SummaryReport():

    def __init__(self, filename, duration, title = ''):
        self._filepath = PurePath(filename)
        self._inversion_duration = duration
        self._title = title

    def intro(self):
        lines = [
        '# Summary of MFD weighting sensitivity test',
        '',
        '## %s' % (self._title,),
        '',
        'Test permutations of mfd_equality and inequality weighting are used to define the Target MFD inversion',
        'constraints. Inversions of %s minutes were performed and MagRate curves generated.' % (self._inversion_duration,),
        ''
        ]
        return [l + '\n' for l in lines]

    def _header_lines(self):
        return [
            '| | Inequality 0 | Inequality 1 | Inequality 10 | Inequality 100 | Inequality 1000 |\n',
            '|-----|-----|-----|-----|-----|----|\n',
            ]

    def _line(self, eq_wt, ineq_wts):
        line = '| **Equality: %s** |' % eq_wt
        for wt in ineq_wts:
            line += ' <img src="eq%04d_ineq%04d/MAG_rates_log_fixed_yscale.png" width=300 > |' % (eq_wt, wt)
        return line + '\n'

    def write(self, eq_wts, ineq_wts):
        report_lines = []
        report_lines = self.intro()
        report_lines += ['\n','\n',]
        report_lines += self._header_lines()
        for eq_wt in eq_wts:
            report_lines += self._line( eq_wt, ineq_wts)
        output = open(self._filepath, 'w')
        output.writelines(report_lines)
        output.close()



if __name__ == "__main__":

    #setup the java gateway binding
    gateway = JavaGateway()

    java_import(gateway.jvm, 'scratch.UCERF3.inversion.*')
    sliprate_weighting = gateway.jvm.UCERF3InversionConfiguration.SlipRateConstraintWeightingType

    app = gateway.entry_point
    # #builder = app.getBuilder()
    INVERSION_MINS = 30
    RUPTURE_FILE = "/tmp/CFM_hk_slipdef0_scalingTMG2.f_rupture_set.zip"

    #get the root path for the task local data
    root_folder = PurePath(os.getcwd())
    output_folder = root_folder.joinpath('tmp/autom/MFD_SENSE_45')
    Path(str(output_folder)).mkdir(parents=True, exist_ok=True)

    reporter = app.createReportBuilder()

    eq_wts = ineq_wts = [0, 1, 10, 100, 1000]

    summary = SummaryReport(output_folder.joinpath("summary_new.md"), INVERSION_MINS, title = 'test')
    summary.write(eq_wts, ineq_wts)

    sys.exit()

    for eq_wt in eq_wts:
        for ineq_wt in ineq_wts:

            new_folder = output_folder.joinpath("eq%04d_ineq%04d" % (eq_wt, ineq_wt))

            ##run an inversion
            solution_path = run_inversion(eq_wt, ineq_wt, new_folder, INVERSION_MINS)

            #run the report
            print("report: eq%04d_ineq%04d" % (eq_wt, ineq_wt))
            print("==============================")
            reporter.setName("eq%04d_ineq%04d" % (eq_wt, ineq_wt))\
                .setRuptureSetName(solution_path)\
                .setOutputDir(str(new_folder))\
                .generate()

    summary.close()
    print('Done!')
