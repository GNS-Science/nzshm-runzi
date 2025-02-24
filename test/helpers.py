from contextlib import contextmanager


@contextmanager
def does_not_raise():
    """
    Helper class for writing parameterized tests that might cause exceptions.
    """
    yield
