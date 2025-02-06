import runzi.cli.inv_setup as inv_setup
from runzi.cli.cli_helpers import MenuHandler, build_inversion_index, display_env, landing_banner
from runzi.cli.inversion_diagnostic_runner import inversion_diagnostic_query
from runzi.cli.load_json import load_crustal, load_subduction

from runzi.cli.openquake_hazard import openquake_hazard_query

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

    crustal_edit_menu = MenuHandler(
        context + '/inversions/crustal/edit',
        {
            'job': inv_setup.change_job_values,
            'task': inv_setup.change_task_values,
            'general': inv_setup.change_general_values,
            'add': inv_setup.add_task_arg,
            'delete': inv_setup.delete_task_arg,
        },
    )

    subduction_edit_menu = MenuHandler(
        context + '/inversions/subduction/edit',
        {
            'job': inv_setup.change_job_values,
            'task': inv_setup.change_task_values,
            'general': inv_setup.change_general_values,
            'add': inv_setup.add_task_arg,
            'delete': inv_setup.delete_task_arg,
        },
    )

    crustal_menu = MenuHandler(
        context + '/inversions/crustal',
        {
            'load': load_crustal,
            'save': inv_setup.save_to_json,
            'show': inv_setup.show_values,
            'edit': crustal_edit_menu.run,
            'new': inv_setup.crustal_setup,
            'run': inv_setup.crustal_run,
        },
    )

    subduction_menu = MenuHandler(
        context + '/inversions/subduction',
        {
            'load': load_subduction,
            'save': inv_setup.save_to_json,
            'show': inv_setup.show_values,
            'edit': subduction_edit_menu.run,
            'new': inv_setup.subduction_setup,
            'run': inv_setup.subduction_run,
        },
    )

    inversions_menu = MenuHandler(
        context + '/inversions',
        {
            'crustal': crustal_menu.run,
            'subduction': subduction_menu.run,
            'diagnostics': inversion_diagnostic_query,
            'index': build_inversion_index,
        },
    )

    hazard_menu = MenuHandler(context + '/hazards', {'openquake': openquake_hazard_query})
    main_menu = MenuHandler(context, {'inversions': inversions_menu.run, 'hazard': hazard_menu.run, 'env': display_env})

    main_menu.run()


if __name__ == '__main__':
    main()
