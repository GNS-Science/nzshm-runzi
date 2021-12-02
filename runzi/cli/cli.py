from runzi.cli.inv_setup import change_job_values, change_task_values, add_task_arg
from runzi.cli.load_json import load_crustal, load_subduction
import sys
from runzi.cli.cli_helpers import MenuHandler, build_inversion_index, landing_banner
from runzi.cli.inv_setup import *
from runzi.cli.load_json import load_from_json
from runzi.cli.inversion_diagnostic_runner import inversion_diagnostic_query
from openquake_hazard import openquake_hazard_query

context = 'runziCLI'

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
        'hazard': hazard_menu.run
    })

    main_menu.run()


if __name__ == '__main__':
    main()