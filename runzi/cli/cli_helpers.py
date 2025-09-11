import random
import string
import sys
from pprint import pformat

import inquirer
from prompt_toolkit import PromptSession  # , prompt
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.validation import ValidationError, Validator
from pyfiglet import Figlet
from pygments import highlight
from pygments.formatters import Terminal256Formatter
from pygments.lexers.python import PythonLexer
from termcolor import cprint

from runzi.runners.build_manual_index import build_manual_index
from runzi.automation.scaling.local_config import (
    API_URL,
    CLUSTER_MODE,
    JAVA_THREADS,
    JVM_HEAP_MAX,
    JVM_HEAP_START,
    S3_REPORT_BUCKET,
    S3_UPLOAD_WORKERS,
    S3_URL,
    USE_API,
    WORK_PATH,
    WORKER_POOL_SIZE,
)

session: PromptSession[str] = PromptSession()


def landing_banner():

    f = Figlet(font='univers')
    b = Figlet(font='big')
    cprint('Welcome to the...', 'red')
    cprint(f.renderText('runziCLI'), 'red')
    cprint('You are operating in ...\n', 'cyan')
    cprint(b.renderText(f"{CLUSTER_MODE.name} - {API_URL[-12:-8].upper()}"), 'cyan')
    cprint('try inputting help to get started...', 'green')


def to_json_format(config):
    cleaned_args = {k[1:]: v for k, v in config.items()}
    job_args = ['worker_pool_size', 'jvm_heap_max', 'java_threads', 'use_api', 'general_task_id', 'mock_mode']
    general_args = [
        'task_title',
        'task_description',
        'file_id',
        'model_type',
        'subtask_type',
        'unique_id',
        'rounds_range',
    ]
    formatted_args = {"job_args": {}, "general_args": {}, "task_args": {}}
    for arg in cleaned_args:
        if arg in job_args:
            formatted_args["job_args"][arg] = cleaned_args[arg]
        elif arg in general_args:
            formatted_args["general_args"][arg] = cleaned_args[arg]
        elif arg not in job_args or general_args:
            formatted_args["task_args"][arg] = cleaned_args[arg]
    return formatted_args


def from_json_format(config):
    flat_dict = {**config['job_args'], **config['general_args'], **config['task_args']}
    flat_dict['config_version'] = config.get('config_version')
    return {'_' + k: v for k, v in flat_dict.items()}


def unique_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))


def pprint_color(obj):
    print(highlight(pformat(obj), PythonLexer(), Terminal256Formatter()))


def display(obj):
    print("General Arguments:")
    general_args = {k[1:]: v for k, v in obj.get_general_args().items()}
    pprint_color(general_args)
    print("Task Arguments:")
    task_args = {k[1:]: v for k, v in obj.get_task_args().items()}
    pprint_color(task_args)
    print("Job Arguments:")
    job_args = {k[1:]: v for k, v in obj.get_job_args().items()}
    pprint_color(job_args)


class MenuHandler:

    def __init__(self, menu_context, options=None, exit_options=None):
        self.context = menu_context
        self.options = options or {'quit', sys.exit}
        self.exit_options = exit_options or ['done']
        self.options.update({'help': self.option_help, 'done': self.option_done, 'exit': self.exit})
        self.value = None
        self.cmd = ''

    def help_about(self):
        return "Valid commands: %s" % ", ".join(self.options.keys())

    def option_help(self, option):
        '''help
        help "some command" will print the docstring of the optinos function
        '''
        command = option.strip()
        if not command:
            return self.help_about()

        func = self.options.get(command)
        if func:
            doc = func.__doc__
            if doc:
                return doc
            else:
                return "Oops, no docstring for command:%s " % command
        return "unknown command:%s " % command

    def prompt(self):
        my_completer = WordCompleter(self.options.keys(), sentence=True)
        self.value = session.prompt('%s>' % self.context, completer=my_completer)
        return self.value

    def interrogate(self, cmd):

        matched = None
        for option in self.options.keys():
            cmd_part, remainder = cmd[: len(option)], cmd[len(option) :]
            if cmd_part == option:
                matched = True

                # this might be a helper method, or another menuhandler
                fn = self.options[cmd_part]
                _ = fn(cmd_part, remainder)
                # print(type(fn), dir(fn))
                if not (hasattr(fn, '__self__') and isinstance(fn.__self__, MenuHandler)):
                    None
                    # print(res)
                    # print(fn.__self__)?
                continue
        if not matched:
            print('type "help" to see valid commands')
            # print('Ooops, can\'t handle "%s"' % cmd)
            # return self.help

    def option_done(self, cmd, value=None):
        '''done
        Exit the current menu level, if at the top level, this quits the CLI
        '''
        return None

    def run(self, *args):
        while True:
            self.cmd = self.prompt().strip()

            if self.cmd.lower()[:4] == 'help':
                print(self.option_help(self.cmd.lower()[4:]))
                continue
            if self.cmd.lower() in self.exit_options:
                return self.cmd.lower()  # leave this menu
            self.interrogate(self.cmd)

    def exit(self, *args):
        sys.exit()


class NumberValidator(Validator):
    def validate(self, document):
        text = document.text

        if text and not text.isdigit():
            i = 0

            # Get index of first non numeric character.
            # We want to move the cursor here.
            for i, c in enumerate(text):
                if not c.isdigit():
                    break

            raise ValidationError(
                message='This input must be an integer -- no non-numeric characters please', cursor_position=i
            )


def build_inversion_index(*args):
    build_inversion_index_query()


def display_env(*args):
    cprint('NZSHM22_SCRIPT_WORK_PATH:', 'cyan', end=' ')
    cprint(WORK_PATH, 'magenta')
    cprint('USE_API:', 'cyan', end=' ')
    cprint(USE_API, 'magenta')
    cprint('NZSHM22_TOSHI_API_URL:', 'cyan', end=' ')
    cprint(API_URL, 'magenta')
    cprint('NZSHM22_TOSHI_S3_URL:', 'cyan', end=' ')
    cprint(S3_URL, 'magenta')
    cprint('NZSHM22_SCRIPT_CLUSTER_MODE:', 'cyan', end=' ')
    cprint(CLUSTER_MODE.name, 'magenta')
    cprint('NZSHM22_S3_REPORT_BUCKET:', 'cyan', end=' ')
    cprint(S3_REPORT_BUCKET, 'magenta')
    cprint('NZSHM22_S3_UPLOAD_WORKERS:', 'cyan', end=' ')
    cprint(S3_UPLOAD_WORKERS, 'magenta')
    cprint('NZSHM22_SCRIPT_JAVA_THREADS:', 'cyan', end=' ')
    cprint(JAVA_THREADS, 'magenta')
    cprint('NZSHM22_SCRIPT_JVM_HEAP_START:', 'cyan', end=' ')
    cprint(JVM_HEAP_START, 'magenta')
    cprint('NZSHM22_SCRIPT_JVM_HEAP_MAX:', 'cyan', end=' ')
    cprint(JVM_HEAP_MAX, 'magenta')
    cprint('NZSHM22_SCRIPT_WORKER_POOL_SIZE:', 'cyan', end=' ')
    cprint(WORKER_POOL_SIZE, 'magenta')


def build_inversion_index_query():
    general_tasks = inquirer.text('General Task ID - for multiple put a space between each')
    general_task_list = general_tasks.split(' ')
    confirm = inquirer.confirm(f'Confirm you want to update index.html for IDs: {general_task_list}')
    if confirm:
        if len(general_task_list) == 1:
            build_manual_index(general_task_list[0], 'INVERSION')
        elif len(general_task_list) > 1:
            build_manual_index(general_task_list[0], 'INVERSION')
            for gt in general_task_list[1:]:
                build_manual_index(gt, 'INVERSION', True)
        else:
            return
