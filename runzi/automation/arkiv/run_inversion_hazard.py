import csv
import datetime as dt
import json
import os
from pathlib import PurePath
from types import SimpleNamespace

import git
from dateutil.tz import tzutc
from py4j.java_gateway import JavaGateway, java_import


def inversion():
    inversion_runner = app.getRunner()

    mfd = SimpleNamespace(**dict(
        total_rate_m5 = 8.8,
        b_value = 1.0,
        mfd_transition_mag = 7.85,
        mfd_num = 40,
        mfd_min = 5.05,
        mfd_max = 8.95))

    mfd_equality_constraint_weight = 10
    mfd_inequality_constraint_weight = 1000

    sliprate_weighting = gateway.jvm.UCERF3InversionConfiguration.SlipRateConstraintWeightingType

    print("Starting inversion of up to %s minutes" % INVERSION_MINS)
    print("======================================")
    inversion_runner\
        .setInversionSeconds(INVERSION_MINS * 60)\
        .setEnergyChangeCompletionCriteria(float(0), float(0.001), float(1))\
        .setNumThreads(8)\
        .setSyncInterval(30)\
        .setRuptureSetFile(inputfile)

    # .setGutenbergRichterMFD(mfd.total_rate_m5, mfd.b_value, mfd.mfd_transition_mag, mfd.mfd_num, mfd.mfd_min, mfd.mfd_max)
    # .setSlipRateConstraint(sliprate_weighting.NORMALIZED_BY_SLIP_RATE, float(100), float(10))\

    inversion_runner\
        .setGutenbergRichterMFDWeights(
             float(mfd_equality_constraint_weight),
             float(mfd_inequality_constraint_weight))\
        .setSlipRateUncertaintyConstraint(sliprate_weighting.UNCERTAINTY_ADJUSTED, 1000, 2)\
        .configure()\
        .runInversion()

    inversion_runner.writeSolution(SOLUTION_FILE)

    t1 = dt.datetime.utcnow()
    print("Inversion took %s secs" % (t1-t0).total_seconds())

    info = inversion_runner.completionCriteriaMetrics()
    print(info)

    info = inversion_runner.momentAndRateMetrics()
    print(info)

    info = inversion_runner.byFaultNameMetrics()
    print(info)

    info = inversion_runner.parentFaultMomentRates()
    print(info)

    print()
    print("Done")


def hazard():
    print("Setting up hazard")
    print("=================")

    hazard_calc = app.getCalculator()

    calc = hazard_calc\
        .setForecastTimespan(50.0)\
        .setSolutionFile(SOLUTION_FILE)\
        .setMaxDistance(250.0)\
        .build()

    # t2 = dt.datetime.utcnow()
    # print("took %s secs" % (t2-t1).total_seconds())


    print("Hazard in Site...")
    print("==========================")
    masterton = dict(lat=-40.95972, lon=175.6575)
    wellington = dict(lat=-41.289, lon=174.777)
    result = calc.calc(wellington['lat'], wellington['lon'])

    # # print(dir(result))
    # """
    # ['areAllXValuesInteger', 'calcSumOfY_Vals', 'clear', 'deepClone', 'equals', 'forEach', 'fromXMLMetadata',
    # 'get', 'getClass', 'getClosestXtoY', 'getClosestYtoX', 'getDatasetsToPlot',
    # 'getFirstInterpolatedX', 'getFirstInterpolatedX_inLogXLogYDomain', 'getFirstInterpolatedX_inLogYDomain',
    # 'getIndex', 'getInfo', 'getInterpExterpY_inLogYDomain', 'getInterpolatedY', 'getInterpolatedY_inLogXDomain',
    # 'getInterpolatedY_inLogXLogYDomain', 'getInterpolatedY_inLogYDomain', 'getMaxX', 'getMaxY',
    # 'getMetadataString', 'getMinX', 'getMinY', 'getName', 'getPlotNumColorList',
    # 'getPointsIterator', 'getTolerance', 'getX', 'getXAxisName', 'getXIndex', 'getXVals',
    # 'getXValuesIterator', 'getY', 'getYAxisName', 'getYVals', 'getYValuesIterator',
    # 'getYY_Function', 'hasX', 'hashCode', 'iterator', 'loadFuncFromSimpleFile',
    # 'main', 'notify', 'notifyAll', 'scale', 'set', 'setInfo', 'setName',
    # 'setTolerance', 'setXAxisName', 'setYAxisName', 'size', 'spliterator', 'toDebugString',
    # 'toString', 'toXMLMetadata', 'wait', 'writeSimpleFuncFile', 'xValues', 'yValues']
    # """

    fout = open("wgtn_50yr_250km_PGA_inversion_for_%sm_" % INVERSION_MINS, 'w')
    fout.write(result.getInfo())
    fout.write('\n\n')
    fout.write(result.toString())

    # t3 = dt.datetime.utcnow()
    # print("took %s secs" % (t3-t2).total_seconds())
    print("Done!")


if __name__ == "__main__":

    #setup the java gateway binding
    gateway = JavaGateway()

    java_import(gateway.jvm, 'scratch.UCERF3.inversion.*') ## for SlipRateConstraintWeightingType

    app = gateway.entry_point
    #builder = app.getBuilder()


    ##Test parameters
    # inputfile = "/home/chrisbc/DEV/GNS/opensha/tmp/2020-11-22T23-49-54.671294/ruptset_ddw0.5_jump5.0_SANS_TVZ2_560.0_2_DOWNDIP.zip"
    # inputfile = "/home/chrisbc/DEV/GNS/opensha/tmp/2020-12-07T01-14-52.776388/ruptset_ddw0.5_jump5.0_SANS_TVZ2_580.0_2_DOWNDIP.zip"
    #inputfile = "/home/chrisbc/DEV/GNS/opensha/tmp/2020-12-07T23-33-01.777193/ruptset_ddw0.5_jump5.0_SANS_TVZ2_580.0_2_DOWNDIP_0.1.zip"
    #inputfile = "/home/chrisbc/DEV/GNS/opensha/tmp/2020-12-07T23-40-04.296119/ruptset_ddw0.5_jump5.0_SANS_TVZ2_580.0_2_DOWNDIP_thin0.5.zip"
    #inputfile = "/home/chrisbc/DEV/GNS/opensha/tmp/2020-12-14T00-03-34.026887/ruptset_ddw0.5_jump5.0_SANS_TVZ2_HIKURANGI_1_580.0_2_UCERF3_thin0.1.zip"
    #inputfile = "/home/chrisbc/DEV/GNS/opensha/tmp/2020-12-15T00-02-59.733572/ruptset_ddw0.5_jump5.0_SANS_TVZ2_HIKURANGI_1_580.0_2_UCERF3_thin0.1.zip"

    # COMBO 330K
    # inputfile = "/home/chrisbc/DEV/GNS/opensha/tmp/2020-12-15T02-58-03.807233/ruptset_ddw0.5_jump5.0_SANS_TVZ2_HIKURANGI_1_580.0_2_UCERF3_thin0.1.zip"
    # inputfile = "/home/chrisbc/DEV/GNS/opensha/tmp/2021-03-02T08-04-59.066119/ruptset_ddw0.5_jump5.0_SANS_TVZ2_580.0_2_UCERF3_thin0.zip"
    #inputfile = "/home/chrisbc/DEV/GNS/opensha/tmp/2021-03-02T08-30-22.459299/ruptset_ddw0.5_jump5.0_SANS_TVZ2_580.0_2_UCERF3_thin0.05.zip"
    #inputfile = "/home/chrisbc/DEV/GNS/opensha/tmp/2021-03-02T08-04-59.066119/ruptset_ddw0.5_jump5.0_SANS_TVZ2_580.0_2_UCERF3_thin0.zip"
    #inputfile = "/home/chrisbc/DEV/GNS/opensha/nshm-nz-opensha/data/ruptureSets/ruptset_ddw0.5_jump5.0_SANS_TVZ2_580.0_2_UCERF3_thin0.1.zip"
    #inputfile = "/home/chrisbc/DEV/GNS/opensha/nshm-nz-opensha/data/ruptureSets/ruptset_ddw0.5_jump5.0_SANS_TVZ2_580.0_2_UCERF3_thin0.0.zip"
    inputfile = "/home/chrisbc/DEV/GNS/opensha/nshm-nz-opensha/data/ruptureSets/ruptset_DEPTH30_ddw0.5_jump5.0_SANS_TVZ2_580.0_2_UCERF3_thin0.0.zip"
    inputfile = "/home/chrisbc/DEV/GNS/opensha/tmp/2021-05-06T04-52-17.049810/ruptset_DEPTH30_ddw0.5_jump5.0_SANS_TVZ2_580.0_2_UCERF3_thin0.0.zip"
    t0 = dt.datetime.utcnow()

    INVERSION_MINS = 240; #185
    #SOLUTION_FILE = "/home/chrisbc/DEV/GNS/opensha/tmp/reports/TestSolution_%sm_CRUSTAL_SANS_TVZ2_BGSEIS.zip" % INVERSION_MINS
    #SOLUTION_FILE = "/home/chrisbc/DEV/GNS/opensha/nshm-nz-opensha/data/inversionSolutions/TestSolution_%sm_CRUSTAL_SANS_TVZ2_BGSEIS_thin0.0.zip" % INVERSION_MINS
    SOLUTION_FILE = "/home/chrisbc/DEV/GNS/opensha/nshm-nz-opensha/data/inversionSolutions/TestSolution_%sm_CRUSTAL_SANS_TVZ2_BGSEIS_thin0.0.zip" % INVERSION_MINS

    inversion()
    print(SOLUTION_FILE)
    # print()
    # hazard()

    print( "done")