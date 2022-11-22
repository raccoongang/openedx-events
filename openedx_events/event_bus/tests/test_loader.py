"""
Tests for event bus implementation loader.
"""

import warnings
from contextlib import contextmanager
from unittest import TestCase

from django.test import override_settings

from openedx_events.event_bus import _try_load, get_producer, make_single_consumer
from openedx_events.learning.signals import SESSION_LOGIN_COMPLETED


@contextmanager
def assert_warnings(warning_messages: list):
    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter('always')
        yield
    assert [str(w.message) for w in caught_warnings] == warning_messages


class TestLoader(TestCase):

    # No, the "constructors" here don't make much sense, but I didn't
    # want to create a bunch of test classes/factory functions, so I'm
    # using built-in functions instead.

    def test_unconfigured(self):
        with assert_warnings(["Event Bus setting DOES_NOT_EXIST is missing; component will be inactive"]):
            loaded = _try_load(
                setting_name="DOES_NOT_EXIST", args=(1), kwargs={'2': 3},
                expected_class=dict, default={'def': 'ault'},
            )
        assert loaded == {'def': 'ault'}

    @override_settings(EB_LOAD_PATH='builtins.dict')
    def test_success(self):
        with assert_warnings([]):
            loaded = _try_load(
                setting_name="EB_LOAD_PATH", args=(), kwargs={'2': 3},
                expected_class=dict, default={'def': 'ault'},
            )
        assert loaded == {'2': 3}

    @override_settings(EB_LOAD_PATH='builtins.list')
    def test_wrong_type(self):
        with assert_warnings([
                "builtins.list from EB_LOAD_PATH returned unexpected type <class 'list'>; "
                "component will be inactive"
        ]):
            loaded = _try_load(
                setting_name="EB_LOAD_PATH", args=([1, 2, 3],), kwargs={},
                expected_class=dict, default={'def': 'ault'},
            )
        assert loaded == {'def': 'ault'}

    @override_settings(EB_LOAD_PATH='no_module_here.foo.nope')
    def test_missing_module(self):
        with assert_warnings([
                "Failed to load <class 'dict'> from setting EB_LOAD_PATH: "
                "ModuleNotFoundError(\"No module named 'no_module_here'\"); "
                "component will be inactive"
        ]):
            loaded = _try_load(
                setting_name="EB_LOAD_PATH", args=(1), kwargs={'2': 3},
                expected_class=dict, default={'def': 'ault'},
            )
        assert loaded == {'def': 'ault'}

    @override_settings(EB_LOAD_PATH='builtins.does_not_exist')
    def test_missing_attribute(self):
        with assert_warnings([
                "Failed to load <class 'dict'> from setting EB_LOAD_PATH: "
                "ImportError('Module \"builtins\" does not define a \"does_not_exist\" attribute/class'); "
                "component will be inactive"
        ]):
            loaded = _try_load(
                setting_name="EB_LOAD_PATH", args=(1), kwargs={'2': 3},
                expected_class=dict, default={'def': 'ault'},
            )
        assert loaded == {'def': 'ault'}

    @override_settings(EB_LOAD_PATH='builtins.dict')
    def test_bad_args_for_callable(self):
        with assert_warnings([
                "Failed to load <class 'dict'> from setting EB_LOAD_PATH: "
                "TypeError('type object argument after * must be an iterable, not int'); "
                "component will be inactive"
        ]):
            loaded = _try_load(
                setting_name="EB_LOAD_PATH", args=(1), kwargs={'2': 3},
                expected_class=dict, default={'def': 'ault'},
            )
        assert loaded == {'def': 'ault'}


class TestProducer(TestCase):

    @override_settings(EVENT_BUS_PRODUCER=None)
    def test_default_does_nothing(self):
        """
        Test that the default is of the right class but does nothing.
        """
        producer = get_producer()

        with assert_warnings([]):
            # Nothing thrown, no warnings.
            assert producer.send(
                signal=SESSION_LOGIN_COMPLETED, topic='user-logins',
                event_key_field='user.id', event_data={},
            ) is None
