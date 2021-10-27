import json
from platform import version
from runzi.cli.cli_helpers import from_json_format
import sys
import os
from pathlib import Path

from config.inversion_builder import Config
import inquirer
from cli_helpers import display
import inv_setup

def load_crustal(*args): load_from_json("INVERSION", "CRUSTAL")
def load_subduction(*args): load_from_json("INVERSION", "SUBDUCTION")

def load_from_json(subtask, model):
    if os.path.exists(Path(__file__).resolve().parent / 'config' / 'saved_configs' / subtask / model):
        saved_configs = os.listdir(Path(__file__).resolve().parent / 'config' / 'saved_configs'/ subtask / model)
        if len(saved_configs) == 0: 
            print("Nothing here!")
            return
        filepath = inquirer.list_input("Choose from past configs, select to preview", choices=saved_configs)
        file = open(Path(__file__).resolve().parent / 'config' / 'saved_configs' / subtask / model / filepath)
        loaded_config = json.load(file)
        parse_config_locally_and_display(loaded_config)
        choice = inquirer.list_input("Would you like to load this config?", 
            choices = ['Yes', 'No', 'Exit'])
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
    inv_setup.global_config = Config()
    inv_setup.global_config.from_json(formatted_json)

def parse_config_locally_and_display(config):
    #Displays config without making it the global_config
    formatted_json = from_json_format(config)
    local_config = Config()
    local_config.from_json(formatted_json)
    display(local_config)



    
