# import logging, logging.config
import os

from openquake_hazard import openquake_hazard_query

from runzi.cli.cli_helpers import MenuHandler, build_inversion_index, display_env, landing_banner
from runzi.cli.inv_setup import *
from runzi.cli.inv_setup import add_task_arg, change_job_values, change_task_values
from runzi.cli.inversion_diagnostic_runner import inversion_diagnostic_query
from runzi.cli.load_json import load_crustal, load_from_json, load_subduction

context = 'runziCLI'

LOGGING_CFG = 'logging.yaml'

# if os.path.exists(LOGGING_CFG):
#     with open(LOGGING_CFG, 'rt') as f:
#         config = yaml.safe_load(f.read())
#     logging.config.dictConfig(config)
# else:
#     # logging.getLogger().setLevel(logging.INFO)
#     # logging.basicConfig(level=logging.INFO)
#     pass

def main():

    landing_banner()

    crustal_edit_menu = MenuHandler(context + '/inversions/crustal/edit', {
        'job': change_job_values,
        'task': change_task_values,
        'general': change_general_values,
        'add': add_task_arg,
        'delete': delete_task_arg
    })

    subduction_edit_menu = MenuHandler(context + '/inversions/subduction/edit', {
        'job': change_job_values,
        'task': change_task_values,
        'general': change_general_values,
        'add': add_task_arg,
        'delete': delete_task_arg
    })

    crustal_menu = MenuHandler(context + '/inversions/crustal', {
        'load': load_crustal,
        'save': save_to_json,
        'show': show_values,
        'edit': crustal_edit_menu.run,
        'new': crustal_setup,
        'run': crustal_run,
    })
    
    subduction_menu = MenuHandler(context + '/inversions/subduction', {
        'load': load_subduction,
        'save': save_to_json,
        'show': show_values,
        'edit': subduction_edit_menu.run,
        'new': subduction_setup,
        'run': subduction_run,
    })

    inversions_menu = MenuHandler(context + '/inversions', {
        'crustal': crustal_menu.run,
        'subduction': subduction_menu.run,
        'diagnostics': inversion_diagnostic_query,
        'index': build_inversion_index
    })

    hazard_menu = MenuHandler(context + '/hazards', {
        'openquake': openquake_hazard_query
    })
    main_menu = MenuHandler(context, {
        'inversions': inversions_menu.run,
        'hazard': hazard_menu.run,
        'env': display_env
    })

    main_menu.run()


if __name__ == '__main__':
    main()