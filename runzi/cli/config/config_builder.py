import json
import os
from runzi.cli.crustal_inversion_runner import run_crustal_inversion
from runzi.cli.subduction_inversion_runner import run_subduction_inversion
from runzi.cli.cli_helpers import display, to_json_format, from_json_format, unique_id
from pathlib import Path
from datetime import datetime

class Config:
    def __init__(self, task_title=None, task_description=None, file_id=None, worker_pool_size = 2, jvm_heap_max = 12,
    java_threads = 0, use_api = False, general_task_id = None, mock_mode = False, rounds = 1) -> None:

        self._unique_id = unique_id()
        self._task_title = task_title
        self._task_description = task_description
        self._worker_pool_size = worker_pool_size
        self._jvm_heap_max = jvm_heap_max
        self._java_threads = java_threads
        self._use_api = use_api
        self._general_task_id = general_task_id
        self._file_id = file_id
        self._mock_mode = mock_mode
        self._rounds = rounds
    
    def to_json(self, overwrite):

        json_dict = to_json_format(self.__dict__)
        path = Path(__file__).resolve().parent / 'saved_configs' / self._subtask_type / self._model_type
        if overwrite == True:
            for root, dirs, files in os.walk(path):
                for file in files:
                    if self._unique_id in file:
                        with open(path / file, "w") as myfile:
                            print('')
                            myfile.write(json.dumps(json_dict, indent=2))
                        return
                else:
                    print('No file to overwrite - saving to new file')
                    self.save_as_new()
        if overwrite == False:
            self.save_as_new()

    def save_as_new(self):
        json_dict = to_json_format(self.__dict__)
        path = Path(__file__).resolve().parent / 'saved_configs' / self._subtask_type /self._model_type
        formatted_date = datetime.strftime(datetime.now(), '%y-%m-%d-%H%M')
        jsonpath = path / f'{formatted_date}_{self._unique_id}_config.json'
        path.mkdir(exist_ok=True)
        print(f'Saved your config to JSON as {formatted_date}_{self._unique_id}_config.json')
        jsonpath.write_text(json.dumps(json_dict, indent=2))

    def from_json(self, config):
        for k, v in config.items():
            self.__setitem__(k, v)

    def get_job_args(self):
        job_args = ['_worker_pool_size',
                    '_jvm_heap_max',
                    '_java_threads',
                    '_use_api',
                    '_general_task_id',
                    '_mock_mode']
        return {k:v for k, v in self.__dict__.items() if k in job_args}

    def get_task_args(self):
        non_task_args = ['_worker_pool_size',
                        '_jvm_heap_max',
                        '_java_threads',
                        '_use_api',
                        '_general_task_id',
                        '_mock_mode', 
                        '_task_title',
                        '_task_description',
                        '_file_id',
                        '_model_type',
                        '_subtask_type',
                        '_unique_id']
        return {k:v for k, v in self.__dict__.items() if k not in non_task_args}

    def get_run_args(self):
        non_task_args = ['_worker_pool_size',
                        '_jvm_heap_max',
                        '_java_threads',
                        '_use_api',
                        '_general_task_id',
                        '_mock_mode', 
                        '_task_title',
                        '_task_description',
                        '_file_id',
                        '_model_type',
                        '_subtask_type',
                        '_unique_id']

        return {k[1:]:v for k, v in self.__dict__.items() if k not in non_task_args}

    def get_general_args(self):
        general_args = ['_task_title',
                        '_task_description',
                        '_file_id',
                        '_model_type',
                        '_subtask_type',
                        '_unique_id']
        return {k:v for k, v in self.__dict__.items() if k in general_args}
    
    def get_keys(self):
        return list(self.__dict__.keys())

    def get_all(self):
        return dict(self.__dict__.items())

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        return setattr(self, key, value)
    
    def __deleteitem__(self, key):
        delattr(self, key)

    def run_subduction(self):
        run_subduction_inversion(self)
    
    def run_crustal(self):
        run_crustal_inversion(self)

