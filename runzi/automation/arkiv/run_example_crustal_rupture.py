# run_crustal_rupture_default.py
# import json
# import git
# import csv
import datetime as dt
import os
from pathlib import PurePath

from dateutil.tz import tzutc
from py4j.java_gateway import JavaGateway


def run_task(
    builder,
    crustal_filename,
    filekey,
    ddw,
    distance,
    max_cumulative_azimuth,
    min_sub_sects_per_parent,
    strategy,
    thinning_factor,
):
    t0 = dt.datetime.utcnow()
    outputfile = output_folder.joinpath(
        "ruptset_DEPTH30_ddw%s_jump%s_%s_%s_%s_%s_thin%s.zip"
        % (ddw, distance, filekey, max_cumulative_azimuth, min_sub_sects_per_parent, strategy, thinning_factor)
    )

    print("building %s started at %s" % (outputfile, dt.datetime.utcnow().isoformat()), end=' ')

    # Run the task....
    builder.setMaxJumpDistance(distance).setPermutationStrategy(strategy).setMaxSubSectionLength(
        ddw
    ).setMinSubSectsPerParent(min_sub_sects_per_parent).setMaxCumulativeAzimuthChange(
        max_cumulative_azimuth
    ).setFaultModelFile(
        crustal_filename
    ).setThinningFactor(
        thinning_factor
    )

    builder.buildRuptureSet()

    # capture task metrics
    # duration = (dt.datetime.utcnow() - t0).total_seconds()
    # metrics = ruptureSetMetrics(builder)

    # create the output dataset
    builder.writeRuptureSet(str(outputfile))
    print("; took %s secs" % (dt.datetime.utcnow() - t0).total_seconds())


if __name__ == "__main__":

    # setup the java gateway binding
    gateway = JavaGateway()
    app = gateway.entry_point
    builder = app.getBuilder()

    # get the root path for the task local data
    root_folder = PurePath(os.getcwd())

    repos = ["opensha-ucerf3", "opensha-commons", "opensha-core", "nshm-nz-opensha"]
    # repo_root = root_folder
    output_folder = root_folder.joinpath('tmp').joinpath(dt.datetime.utcnow().isoformat().replace(':', '-'))
    os.mkdir(output_folder)

    ##Test parameters
    crustal_filename = str(root_folder.joinpath("nshm-nz-opensha/data/FaultModels/SANSTVZ2_crustal_opensha.xml"))
    filekey = "SANS_TVZ2"
    strategy = 'UCERF3'  # , ] #'POINTS'] #, 'UCERF3' == DOWNDIP]
    distance = 5.0  # , 5.1, 5.2, 5.3]
    ddw = 0.5  # , 1.5, 2.0, 2.5]
    min_sub_sects_per_parent = 2  # ,3,4]
    max_cumulative_azimuth = 580.0  # , 600.0]
    thinning_factor = 0.0  # .075 #, 0.2, 0.0]

    # test the tests, nomally 1000 for NZ CFM
    max_sections = 1000

    # Run the task....
    run_task(
        builder,
        crustal_filename,
        filekey,
        ddw,
        distance,
        max_cumulative_azimuth,
        min_sub_sects_per_parent,
        strategy,
        thinning_factor,
    )

    print("Done!")
