#!python3 oq_hazard_config.py
import logging
import configparser
import io

from pathlib import Path
log = logging.getLogger(__name__)

SITES = dict(
    WLG = {"sites": "174.7762 -41.2865"},
    NZ4 = {"sites_csv": "nz_towns_4.csv"},
    NZ34 = {"sites_csv": "nz_towns_34.csv"},
    GRD1 = {"sites_csv": "NZ_whole_country_10k.csv"})

# DEFAULT_DISAGG = dict(
#     poes_disagg = 0.002,
#     mag_bin_width = 0.25,
#     distance_bin_width = 1.0,
#     coordinate_bin_width = 5.0,
#     num_epsilon_bins = 1)


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

    def set_sites(self, site_key: str):
        """

        """
        assert site_key in SITES.keys()
        #destroy any existing site configs
        self.config['site_params'].pop('sites', None)
        self.config['site_params'].pop('sites_csv', None)
        self.config.pop('geometry', None)
        key, value = list(SITES[site_key].items())[0]
        self.config.add_section('geometry')
        self.config['geometry'][key] = value
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

    [site_params]
    sites = 174.7762 -41.2865
    foo=bar


    [calculation]
    intensity_measure_types_and_levels = {"SA(0.5)": logscale(0.005, 4.00, 30)}

    """
    sample = io.StringIO(sample_conf) #fake file for demo

    nc = OpenquakeConfig(sample)\
        .set_sites('NZ4')\
        .set_disaggregation(True, {"num_rlz_disagg": 0})

    measures = ['PGA', 'SA(0.5)']
    levels0 = [0.01, 0.02, 0.04, 0.06, 0.08, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0, 3.5, 4, 4.5, 5.0]
    levels1 = 'logscale(0.005, 4.00, 30)'

    nc.set_iml(measures, levels1)
    nc.set_vs30(355)

    out = io.StringIO() #aother fake file
    nc.write(out)

    out.seek(0)
    for l in out:
        print(l)
