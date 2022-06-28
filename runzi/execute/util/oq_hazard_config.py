#!python3 oq_hazard_config.py
import logging
import configparser
import io

from pathlib import Path
log = logging.getLogger(__name__)

SITES = dict(
    WLG = {"sites": "174.7762 -41.2865"},
    NZ4 = {"site_model_file": "site_model_nz_4.csv"},
    NZ34 = {"site_model_file": "site_model_nz_34.csv"},
    GRD1 = {"sites_csv": "NZ_whole_country_10k.csv"},
    NZ6 =  {"site_model_file": "site_model_test.csv"},
    GRD_NZ_0_5 = {"sites_csv": "./grids/grid-NZ-0.5-0.0003.nb1.csv" },               # 50km  240 sites, 0.5 degs 1 neighbour
    GRD_NZ_0_25 = {"sites_csv": "./NZ_POLYS_0.25.csv" },                             # 25km  471 sites, 0.25 degs 0 neighbour
    GRD_NZ_0_1 = {"sites_csv": "./grids/grid-NZ-0.1-0.0003.nb1.csv" },               # 10km 3618 sites, 0.1 degs, 1 neighbour
    GRD_WLGREG_0_05 = {"sites_csv": "./grids/grid-Wellington-0.05.0003.nb1.csv" },   #  5km  62 sites
    GRD_WLGREG_0_01 = {"sites_csv": "./grids/grid-Wellington-0.01.0003.nb1.csv" },   #  1km 764 sites
)

#Sanjay new values
DEFAULT_DISAGG = dict(
    max_sites_disagg = 1,
    poes_disagg = "0.002105 0.000404",
    mag_bin_width = 0.25,
    distance_bin_width = 10,
    coordinate_bin_width = 1,
    num_epsilon_bins = 4,
    disagg_outputs = "Mag_Dist Mag_Dist_Eps TRT"
    )

class OpenquakeConfig():

    def __init__(self, config):
        self.config = configparser.ConfigParser()
        self.config.read_file(config)

    def set_ps_grid_spacing(self, value=30):
        self.config.pop('ps_grid_spacing', None) # destroy any existing disagg settings
        self.config['general']['ps_grid_spacing'] = str(value)
        return self

    def set_rupture_mesh_spacing(self, rupture_mesh_spacing):
        """We can assume an erf section exists..."""
        self.config['erf']['rupture_mesh_spacing'] = str(rupture_mesh_spacing)
        #self.config['erf']['complex_fault_mesh_spacing'] = str(rupture_mesh_spacing) #CDC thinks this is only for complex
        return self

    def set_sites(self, site_key: str):
        assert site_key in SITES.keys()
        #destroy any existing site configs
        self.config['site_params'].pop('sites', None)
        self.config['site_params'].pop('sites_csv', None)
        self.config['site_params'].pop('site_model_file', None)
        self.config.pop('geometry', None)

        key, value = list(SITES[site_key].items())[0]
        self.config['site_params'][key] = value
        return self

    def set_disaggregation(self, enable: bool, values: dict = None):
        self.config['general']['calculation_mode'] = 'disaggregation' if enable else 'classical'
        if enable:
            self.config.pop('disagg', None) # destroy any existing disagg settings
            self.config.add_section('disagg')
            settings = DEFAULT_DISAGG.copy()
            if values:
                settings.update(values)
            for k, v in settings.items():
                self.config['disagg'][k] = str(v)
        return self

    def set_iml(self, measures: list, levels: object):
        self.config['calculation'].pop('intensity_measure_types_and_levels', None)

        new_iml = '{'
        for m in measures:
            new_iml += f'"{m}": {str(levels)}, '
        new_iml += '}'

        self.config['calculation']['intensity_measure_types_and_levels '] = new_iml
        return self

    def set_vs30(self, vs30):
        try:
            from openquake.commands.prepare_site_model import calculate_z1pt0, calculate_z2pt5_ngaw2
        except:
            print("openquake librarys are not available, skipping set_vs30 ")
            return self

        sect = self.config['site_params']
        #Clean up old settings
        for setting in ['reference_vs30_type', 'reference_vs30_value',
            'reference_depth_to_1pt0km_per_sec', 'reference_depth_to_2pt5km_per_sec']:
            sect.pop(setting, None)

        sect['reference_vs30_type'] = 'measured'
        sect['reference_vs30_value'] = str(vs30)
        sect['reference_depth_to_1pt0km_per_sec'] = str(round(calculate_z1pt0(vs30), 0))
        sect['reference_depth_to_2pt5km_per_sec'] = str(round(calculate_z2pt5_ngaw2(vs30), 1))
        return self

    def write(self, tofile):
        self.config.write(tofile)


if __name__ == "__main__":

    sample_conf = """
    [general]
    calculation_mode = disaggregation

    [logic_tree]

    number_of_logic_tree_samples = 0

    [erf]

    [site_params]
    sites = 174.7762 -41.2865
    foo=bar
    ps_grid_spacing = 10


    [calculation]
    intensity_measure_types_and_levels = {"SA(0.5)": logscale(0.005, 4.00, 30)}

    """
    sample = io.StringIO(sample_conf) #fake file for demo

    nc = OpenquakeConfig(sample)\
        .set_sites('NZ4')\
        .set_disaggregation(False, {"num_rlz_disagg": 0})\
        .set_ps_grid_spacing(20)

    measures = ['PGA', 'SA(0.5)']
    levels0 = [0.01, 0.02, 0.04, 0.06, 0.08, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0, 3.5, 4, 4.5, 5.0]
    levels1 = 'logscale(0.005, 4.00, 30)'
    _4_sites_levels = [0.01, 0.02, 0.04, 0.06, 0.08, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0, 3.5, 4, 4.5, 5.0]
    _4_sites_measures = ['PGA',"SA(0.1)","SA(0.2)","SA(0.3)","SA(0.4)","SA(0.5)","SA(0.7)","SA(1.0)","SA(1.5)","SA(2.0)","SA(3.0)","SA(4.0)","SA(5.0)"]

    nc.set_iml(_4_sites_measures, _4_sites_levels)
    nc.set_vs30(250)
    nc.set_rupture_mesh_spacing(42)

    out = io.StringIO() #aother fake file
    nc.write(out)

    out.seek(0)
    for l in out:
        print(l)

