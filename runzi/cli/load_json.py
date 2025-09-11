import json
import os
from pathlib import Path

import inquirer

import runzi.cli.inv_setup
from runzi.cli.cli_helpers import display
from runzi.runners.inversion_inputs import from_json_format
from runzi.cli.config.inversion_builder import Config


def load_crustal(*args):
    load_from_json("INVERSION", "CRUSTAL")


def load_subduction(*args):
    load_from_json("INVERSION", "SUBDUCTION")


def load_from_json(subtask, model):
    if os.path.exists(Path(__file__).resolve().parent / 'config' / 'saved_configs' / subtask / model):
        saved_configs = os.listdir(Path(__file__).resolve().parent / 'config' / 'saved_configs' / subtask / model)
        if len(saved_configs) == 0:
            print("Nothing here!")
            return
        filepath = inquirer.list_input("Choose from past configs, select to preview", choices=saved_configs)
        file = open(Path(__file__).resolve().parent / 'config' / 'saved_configs' / subtask / model / filepath)
        loaded_config = json.load(file)
        parse_config_locally_and_display(loaded_config)
        choice = inquirer.list_input("Would you like to load this config?", choices=['Yes', 'No', 'Exit'])
        if choice == 'Yes':
            parse_config(loaded_config)
        if choice == 'No':
            load_from_json(subtask, model)
        if choice == 'Exit':
            return
    else:
        os.makedirs(Path(__file__).resolve().parent / 'config' / 'saved_configs' / subtask / model)
        print("Nothing here!")


def parse_config(config):
    formatted_json = from_json_format(config)
    runzi.cli.inv_setup.global_config = Config()
    runzi.cli.inv_setup.global_config.from_json(formatted_json)


def parse_config_locally_and_display(config):
    # Displays config without making it the global_config
    formatted_json = from_json_format(config)
    local_config = Config()
    local_config.from_json(formatted_json)
    display(local_config)
