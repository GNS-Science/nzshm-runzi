from ast import Num

from termcolor import cprint
from runzi.cli.cli_helpers import unique_id
from prompt_toolkit import prompt 
import inquirer
from config.inversion_builder import CrustalConfig, SubductionConfig
from cli_helpers import NumberValidator, display
from datetime import date

def base_config():
    global global_vars
    global_vars = {}
    
    global_vars['task_title'] = prompt('Enter the task title - str: ')
    global_vars['task_description'] = prompt('Enter the task description - str: ')
    global_vars['worker_pool_size'] = int(prompt('Enter the worker pool size - int: ',
                validator=NumberValidator(), validate_while_typing=True))
    global_vars['jvm_heap_max'] = int(prompt('Enter the jvm heap max - int: ', 
                validator=NumberValidator(), validate_while_typing=True))
    global_vars['java_threads'] = int(prompt('Enter the java threads - int: ', 
                validator=NumberValidator(), validate_while_typing=True))
    global_vars['use_api'] = prompt('Enter the use api - yes or no: ') in ['yes', 'y'] or False
    global_vars['general_task_id'] = prompt('Enter the general task id - string: ')
    global_vars['file_id'] = prompt('Enter the file id - string: ')
    global_vars['mock_mode'] = prompt('Would you like to use mock mode? - yes or no: ') in ['yes', 'y'] or False
    global_vars['rounds'] = int(prompt('How many rounds would you like to run? - int: ', 
                validator=NumberValidator(), validate_while_typing=True))

def crustal_setup(*args):
    global global_config
    base_config()

    global_config = CrustalConfig(global_vars['task_title'], 
    global_vars['task_description'], 
    global_vars['file_id'], 
    global_vars['worker_pool_size'], 
    global_vars['jvm_heap_max'],
    global_vars['java_threads'], 
    global_vars['use_api'], 
    global_vars['general_task_id'], 
    global_vars['mock_mode'],
    global_vars['rounds'])

    print('Here\'s your crustal config')
    display(global_config)


def subduction_setup(*args):
    global global_config
    base_config()

    global_config = SubductionConfig(global_vars['task_title'], 
    global_vars['task_description'],
    global_vars['file_id'], 
    global_vars['worker_pool_size'], 
    global_vars['jvm_heap_max'],
    global_vars['java_threads'], 
    global_vars['use_api'], 
    global_vars['general_task_id'], 
    global_vars['mock_mode'],
    global_vars['rounds'])

    print('Here\'s your subduction config')
    display(global_config)

def show_values(*args):
    global global_config
    try: 
        global_config
    except NameError: 
        print("Load or create a config first!")
    else:
        display(global_config)   

def change_general_values(*args): 
    global global_config
    try:
        global_config
    except NameError:
        print("Load or create a config first!")
    else:
        change_values(global_config.get_general_args)

def change_job_values(*args): 
    global global_config
    try:
        global_config
    except NameError:
        print("Load or create a config first!")
    else:
        change_values(global_config.get_job_args)

def change_task_values(*args): 
    global global_config
    try:
        global_config
    except NameError:
        print("Load or create a config first!")
    else:
        change_values(global_config.get_task_args)

def subduction_run(*args):
    global_config.run_subduction()

def crustal_run(*args):
    global_config.run_crustal()

def change_values(value_callback):
    arg_list = value_callback()
    #removes underscore from start of args and adds on the values
    arg_list = [f'{k[1:]}: {v}' for k, v in arg_list.items()]
    arg_list.append('Exit')
    arg_type_tips = ['List - Separate values with commas!',
    'Integer - Put a number!', 'Boolean - yes or no!', 'String - text would be good!']

    arg = inquirer.list_input(message="Choose a value to edit", choices=arg_list)
    arg = arg.split(':')[0]#removes values from argument after displaying

    if arg == "Exit":
        return

    if arg in ['worker_pool_size', 'jvm_heap_max', 'java_threads', 'rounds_range']:
        val = inquirer.text(message=f'New value {arg_type_tips[1]}')
    elif arg in ['mock_mode', 'use_api']:
        val = inquirer.confirm(message=f'New value {arg_type_tips[2]}')
    elif arg in ['task_title', 'task_description', 'general_task_id', 'file_id']:
        val = inquirer.text(message=f'New value {arg_type_tips[3]}')
    else:
        val = inquirer.text(message=f'New value {arg_type_tips[0]}')
    
    go_again = inquirer.confirm(message='Would you like to change another value?')


    if value_callback == global_config.get_task_args:
        val = [x.strip() for x in val.split(',')]

    if arg in ['worker_pool_size', 'jvm_heap_max', 'java_threads', 'rounds_range']:
        if val == '':
            val = 0
        val = int(val)

    if arg in ['mock_mode', 'use_api']:
        if val in ['yes', 'y', 'true', 'True', '1', 'Yes']:
            val = True
        else:
            val = False
    
    if arg == 'rounds':
        val = [str(x) for x in range(int(val))]

    global_config.__setitem__("_" + arg, val)
    
    if go_again == True:
        print(f'You changed {arg} to: {val}')
        change_values(value_callback)

    if go_again == False:
        save_to_json()

def save_to_json(*args):
    answers = ['Overwrite config', 'Save as new config', 'Continue without saving']
    display(global_config)
    save_query = inquirer.list_input('Would you like to save this config to JSON?', 
    choices=answers)
    if save_query == answers[0]:
        global_config.to_json(True)
    elif save_query == answers[1]:
        global_config._unique_id = unique_id()
        global_config.to_json(False)
    else:
        return

def add_task_arg(*args):
    key = inquirer.text('Argument key: ')
    data_type = inquirer.list_input('Argument data type: ', choices=['Integer', 'List', 'String'])
    value = inquirer.text('Argument value: ')
    if data_type == 'Integer':
        value = int(value)
    if data_type == 'List (put a comma between each value)':
        value = value.split(',')
    confirm = inquirer.confirm("Are you sure you would like to add this argument?")
    if confirm == True: 
        global_config.__setitem__("_" + key, value)
        cprint(f'New task argument - {key}: {value}')
    else: 
        return

def delete_task_arg(*args):
    arg_list = global_config.get_task_args()
    arg_list = [k[1:] for k, _ in arg_list.items()]
    arg_list.append("Exit")
    deleted_arg = inquirer.list_input('Argument to delete: ', choices=arg_list)
    if deleted_arg == "Exit":
        return
    else:
        try:
            confirm = inquirer.confirm(f"Are you sure you would like to delete {deleted_arg}?")
            if confirm == True:
                global_config.__deleteitem__('_' + deleted_arg)
            else:
                return
        except AttributeError:
            print(f'No such argument as {deleted_arg}!')




