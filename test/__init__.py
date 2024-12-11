# this is a bit of a wordy way to mock a function and test that it get's the correct arguments. I'm
# trying to avoid using unittest, but maybe unittest.mock would be better here    
from copy import deepcopy

class Spy:
    def __init__(self, func):
        self.func = func
        self.calls = []  # To store calls as (args, kwargs) tuples

    def __call__(self, *args, **kwargs):
        self.calls.append({'args':deepcopy(args), 'kwargs':deepcopy(kwargs)})
        return self.func(*args, **kwargs)