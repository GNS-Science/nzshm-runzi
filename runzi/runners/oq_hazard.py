"""This module provides the runner class for running OQ hazard calculations."""

from pathlib import Path
from typing import cast

from nzshm_model import get_model_version
from nzshm_model.logic_tree import GMCMLogicTree, SourceLogicTree
from nzshm_model.psha_adapter.openquake.hazard_config import OpenquakeConfig

import runzi.execute.oq_hazard_task as task_module
from runzi.automation.scaling.local_config import API_KEY, API_URL, S3_URL, USE_API
from runzi.automation.scaling.toshi_api import ModelType, SubtaskType, ToshiApi
from runzi.execute import ArgSweeper, OQHazardArgs

from .job_runner import JobRunner

headers = {"x-api-key": API_KEY}
toshi_api = ToshiApi(API_URL, S3_URL, None, with_schema_validation=True, headers=headers)


def _upload_file(file_path: Path) -> str:
    file_id, post_url = toshi_api.file.create_file(file_path)
    toshi_api.file.upload_content(post_url, file_path)
    return file_id


class OQHazardJobRunner(JobRunner):
    """A class to run Crustal inversion jobs.

    Assumes that logic trees, hazard_config, and locations are not swept args.
    """

    subtask_type = SubtaskType.HAZARD
    job_name = "Runzi-automation-oq-hazard"

    def __init__(self, argument_sweeper: ArgSweeper):
        """Initialize the OQHazardJobRunner.

        Args:
            job_args: input arguments for the jobs including swept args.
        """
        super().__init__(argument_sweeper, task_module)
        self.srm_logic_tree_path: Path | None = None
        self.gmcm_logic_tree_path: Path | None = None
        self.hazard_config_path: Path | None = None

        self.argument_sweeper.prototype_args = cast(OQHazardArgs, self.argument_sweeper.prototype_args)

        # if using the toshiAPI, upload the locations file
        if locations_file_path := self.argument_sweeper.prototype_args.locations_file:
            file_id = _upload_file(locations_file_path)
            self.argument_sweeper.prototype_args.locations_file_id = file_id

        # if using an NSHM model version, get the logic trees and hazard config
        if model_version := self.argument_sweeper.prototype_args.nshm_model_version:
            model = get_model_version(model_version)
            srm_logic_tree = model.source_logic_tree
            gmcm_logic_tree = model.gmm_logic_tree
            hazard_config = model.hazard_config

        # over-write default values converting any filepaths to the objects themselves
        # if using toshiAPI, upload the files for posterity
        if srm_logic_tree_ovr := self.argument_sweeper.prototype_args.srm_logic_tree:
            if isinstance(srm_logic_tree_ovr, Path):
                srm_logic_tree = SourceLogicTree.from_json(srm_logic_tree_ovr)
                self.srm_logic_tree_path = srm_logic_tree_ovr
            else:
                srm_logic_tree = srm_logic_tree_ovr

        if gmcm_logic_tree_ovr := self.argument_sweeper.prototype_args.gmcm_logic_tree:
            if isinstance(gmcm_logic_tree_ovr, Path):
                gmcm_logic_tree = GMCMLogicTree.from_json(gmcm_logic_tree_ovr)
                self.gmcm_logic_tree_path = gmcm_logic_tree_ovr
            else:
                gmcm_logic_tree = gmcm_logic_tree_ovr

        if hazard_config_ovr := self.argument_sweeper.prototype_args.hazard_config:
            if isinstance(hazard_config_ovr, Path):
                hazard_config = OpenquakeConfig.from_json(hazard_config_ovr)
                self.hazard_config_path = hazard_config_ovr
            else:
                hazard_config = hazard_config_ovr

        self.argument_sweeper.prototype_args.srm_logic_tree = srm_logic_tree
        self.argument_sweeper.prototype_args.gmcm_logic_tree = gmcm_logic_tree
        self.argument_sweeper.prototype_args.hazard_config = hazard_config

        # convert the SRM logic tree into swept arguments
        logic_trees = []
        for branch in self.argument_sweeper.prototype_args.srm_logic_tree:  # type: ignore
            branch.weight = 1.0
            logic_trees.append(SourceLogicTree.from_branches([branch]))
        self.argument_sweeper.swept_args['srm_logic_tree'] = logic_trees

    def get_model_type(self) -> ModelType:
        """Get the model type for OQ hazard jobs."""
        return ModelType.COMPOSITE

    def _build_argument_list(self) -> list[dict[str, str | list[str]]]:
        args_list = super()._build_argument_list()
        if USE_API:
            if self.srm_logic_tree_path:
                file_id = _upload_file(self.srm_logic_tree_path)
                args_list.append(dict(k="srm_logic_tree_id", v=[file_id]))
            if self.gmcm_logic_tree_path:
                file_id = _upload_file(self.gmcm_logic_tree_path)
                args_list.append(dict(k="gmcm_logic_tree_id", v=[file_id]))
            if self.hazard_config_path:
                file_id = _upload_file(self.hazard_config_path)
                args_list.append(dict(k="hazard_config_id", v=[file_id]))
        return args_list
