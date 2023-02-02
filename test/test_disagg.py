import unittest
import json
from pathlib import Path


from runzi.configuration.oq_disagg import get_disagg_configs
from runzi.CONFIG.OQ.SLT_v8 import logic_tree_permutations 

class TestDisaggConfigs(unittest.TestCase):

    def setUp(self):
        self._logic_tree = logic_tree_permutations
        self._config_filepath = Path(Path(__file__).parent, 'fixtures', 'deagg_configs_GIS-0.1-PGA-275.json')
        self._gt_config = dict(
            location = 'GIS',
            poe = 0.1,
            vs30 = 275,
            imt = 'PGA',
            inv_time = 50,
            agg = 'mean',
            hazard_model_id = 'SLT_v8_gmm_v2_FINAL',
        ) 

    def test_disagg_configs(self):

        with open(self._config_filepath, 'r') as config_file:
            config_expected = json.load(config_file)
        
        # print(self._logic_tree)
        disagg_config = get_disagg_configs(self._gt_config, self._logic_tree)

        assert len(config_expected[0]['deagg_specs']) == len(disagg_config[0]['deagg_specs'])
        for k,v in config_expected[0].items():
            if k != 'deagg_specs':
                assert v == disagg_config[0][k]

        for branch in config_expected[0]['deagg_specs']:
            print(branch)
            branch.pop('source_tree_hazid')
            assert branch in disagg_config[0]['deagg_specs']



