#!python3 oq_hazard_config.py
import logging
import configparser
import io

from typing import List
from pathlib import Path

log = logging.getLogger(__name__)

#Sanjay new values
DEFAULT_DISAGG = dict(
    max_sites_disagg = 1,
    #poes_disagg = "0.002105 0.000404",
    mag_bin_width = 0.5,
    distance_bin_width = 10,
    coordinate_bin_width = 1,
    num_epsilon_bins = 4,
    disagg_outputs = "Mag Dist Mag_Dist Mag_Dist_Eps TRT Mag_Dist_TRT Mag_Dist_TRT_Eps"
    )

class OpenquakeConfig():

    DEFAULT_CONFIG = dict(
        general = dict(
            random_seed = 25,
            calculation_mode = 'classical',
            ps_grid_spacing = 30,
        ),
        logic_tree = dict(
            number_of_logic_tree_samples = 0,
        ),
        erf = dict(
            rupture_mesh_spacing = 5,
            width_of_mfd_bin = 0.1,
            complex_fault_mesh_spacing = 10.0,
            area_source_discretization = 10.0,
        ),
        site_params = dict(
            reference_vs30_type = 'measured',
        ),
        calculation = dict(
            investigation_time = 1.0,
            truncation_level = 4,
            maximum_distance = {'Active Shallow Crust': [(4.0, 0), (5.0, 100.0), (6.0, 200.0), (9.5, 300.0)],
                                'Subduction Interface': [(5.0, 0), (6.0, 200.0), (10, 500.0)],
                                'Subduction Intraslab': [(5.0, 0), (6.0, 200.0), (10, 500.0)]}
        ),
        output = dict(
            individual_curves = 'true',
        ),
    )

    def __init__(self):
        self.config = configparser.ConfigParser()
        for k,v in self.DEFAULT_CONFIG.items():
            self.config[k] = v

    def set_source_logic_tree_file(self, source_lt_filepath):
        self.set_parameter("calculation", "source_model_logic_tree_file", source_lt_filepath)
        return self

    def set_parameter(self, parameter_table, parameter_name, value):
        self.unset_parameter(parameter_table, parameter_name)
        if (parameter_table == "calculation") & (parameter_name == "maximum_distance"):
            self.set_maximum_distance(value)
        else:
            self.config[parameter_table][parameter_name] = str(value)
        return self

    def unset_parameter(self, parameter_table, parameter_name):
        if parameter_table not in self.config:
            return
        else:
            self.config[parameter_table].pop(parameter_name, None)
    
    def set_maximum_distance(self, value):
        import ast
        value_new = {}
        for trt, dist_str in value.items():
            value_new[trt] = [tuple(dm) for dm in ast.literal_eval(dist_str)]
        self.config["calculation"]["maximum_distance"] = str(value_new)
        return self

    # def set_rupture_mesh_spacing(self, rupture_mesh_spacing):
    #     """We can assume an erf section exists..."""
    #     self.config['erf']['rupture_mesh_spacing'] = str(rupture_mesh_spacing)
    #     #self.config['erf']['complex_fault_mesh_spacing'] = str(rupture_mesh_spacing) #CDC thinks this is only for complex
    #     return self

    # def clear_sites(self):
    #     #destroy any existing site configs
    #     self.config['site_params'].pop('sites', None)
    #     self.config['site_params'].pop('sites_csv', None)
    #     self.config['site_params'].pop('site_model_file', None)
    #     self.config.pop('geometry', None)
    #     return self

    def set_sites(self, site_model_filename):
        self.config['site_params']['site_model_file'] = site_model_filename
        return self
    
    def set_disagg_site_model(self):
        self.clear_sites()
        self.config['site_params']['site_model_file'] = 'site.csv'
        return self

    def set_disagg_site(self, lat, lon):
        self.clear_sites()
        self.config['site_params']['sites'] = f'{lon} {lat}'
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

    def set_iml_disagg(self, imt, level):
        self.config['disagg']['iml_disagg'] = str({imt:level})
        return self

    def clear_iml(self):
        self.config['calculation'].pop('intensity_measure_types_and_levels', None)
        return self

    def set_iml(self, measures: list, levels: object):
        self.clear_iml()
        new_iml = '{'
        for m in measures:
            new_iml += f'"{m}": {str(levels)}, '
        new_iml += '}'

        self.config['calculation']['intensity_measure_types_and_levels '] = new_iml
        return self

    def set_rlz_index(self, num_rlz):
        self.config['disagg']['rlz_index'] = repr(list(range(num_rlz)))[1:-1]
        return self

    def set_vs30(self, vs30):
        try:
            from openquake.hazardlib.site import calculate_z1pt0, calculate_z2pt5
        except ImportError:
            from openquake.commands.prepare_site_model import calculate_z1pt0
            from openquake.commands.prepare_site_model import calculate_z2pt5_ngaw2 as calculate_z2pt5

        sect = self.config['site_params']
        #Clean up old settings
        for setting in ['reference_vs30_type', 'reference_vs30_value',
            'reference_depth_to_1pt0km_per_sec', 'reference_depth_to_2pt5km_per_sec']:
            sect.pop(setting, None)

        if vs30 == 0:
            return self

        sect['reference_vs30_type'] = 'measured'
        sect['reference_vs30_value'] = str(vs30)
        sect['reference_depth_to_1pt0km_per_sec'] = str(round(calculate_z1pt0(vs30), 0))
        sect['reference_depth_to_2pt5km_per_sec'] = str(round(calculate_z2pt5(vs30), 1))
        return self

    def set_gsim_logic_tree_file(self, filepath):
        self.config['calculation']['gsim_logic_tree_file'] = filepath
        return self

    def set_description(self, description):
        self.config['general']['description'] = description
        return self

    def write(self, tofile):
        self.config.write(tofile)


if __name__ == "__main__":

    nc = OpenquakeConfig()\
        .set_sites('./sites.csv')\
        .set_parameter("general", "ps_grid_spacing", 20)

    measures = ['PGA', 'SA(0.5)']
    levels0 = [0.01, 0.02, 0.04, 0.06, 0.08, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0, 3.5, 4, 4.5, 5.0]
    levels1 = 'logscale(0.005, 4.00, 30)'
    _4_sites_levels = [0.01, 0.02, 0.04, 0.06, 0.08, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0, 3.5, 4, 4.5, 5.0]
    _4_sites_measures = ['PGA',"SA(0.1)","SA(0.2)","SA(0.3)","SA(0.4)","SA(0.5)","SA(0.7)","SA(1.0)","SA(1.5)","SA(2.0)","SA(3.0)","SA(4.0)","SA(5.0)"]

    nc.set_iml(_4_sites_measures, _4_sites_levels)
    nc.set_vs30(250)
    nc.set_parameter("erf", "rupture_mesh_spacing", 42)

    out = io.StringIO() #aother fake file
    nc.write(out)

    out.seek(0)
    for l in out:
        print(l)

