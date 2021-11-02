from runzi.cli.inv_setup import change_job_values, change_task_values, add_task_arg
from runzi.cli.load_json import load_crustal, load_subduction
import sys
import inv_setup
from cli_helpers import MenuHandler, landing_banner
from inv_setup import *
from load_json import load_from_json


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
        'run': crustal_run
    })
    
    subduction_menu = MenuHandler(context + '/inversions/subduction', {
        'load': load_subduction,
        'save': save_to_json,
        'show': show_values,
        'edit': subduction_edit_menu.run,
        'new': subduction_setup,
        'run': subduction_run
    })

    inversions_menu = MenuHandler(context + '/inversions', {
        'crustal': crustal_menu.run,
        'subduction': subduction_menu.run,
    })

    main_menu = MenuHandler(context, {
        'inversions': inversions_menu.run,
    })

    main_menu.run()


if __name__ == '__main__':
    main()