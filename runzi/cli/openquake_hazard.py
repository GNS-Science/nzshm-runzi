import os
import subprocess

import inquirer

from runzi.automation.scaling.local_config import WORK_PATH


def openquake_hazard_query(*args):
    file_list = []
    for root, dirs, files in os.walk(f"{WORK_PATH}/examples"):
        for file in files:
            if file.endswith(".ini"):
                file_list.append(os.path.join(root, file))
    config = inquirer.list_input('Which ini file would you like to use?', choices=file_list)
    confirm = inquirer.confirm(f'Are you sure you would like to run hazard for {config}')
    if confirm:
        subprocess.run([f'oq engine --run {config}'], shell=True)
    else:
        return
    export = inquirer.confirm('Would you like to export your hazard?')
    if export:
        subprocess.run(
            [
                f'oq engine --export-outputs 1 {WORK_PATH}/output',
            ],
            shell=True,
        )
    return
