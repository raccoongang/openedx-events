"""
Classes and utility functions for the event bus.

This module includes the entry points for the producer and consumer.

API:

- ``get_producer`` returns an ``EventBusProducer`` singleton that should be used for sending all events
  to the Event Bus. The backing implementation is chosen via the Django setting ``EVENT_BUS_PRODUCER``.
- ``make_single_consumer`` creates an ``EventBusConsumer`` instance for a particular combination of
  topic, consumer group, and signal. The backing implementation is chosen via the Django setting
  ``EVENT_BUS_CONSUMER``.
"""

import warnings
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import NoReturn, Optional

from django.conf import settings
from django.dispatch import receiver
from django.test.signals import setting_changed
from django.utils.module_loading import import_string

from openedx_events.tooling import OpenEdxPublicSignal


def _try_load(*, setting_name: str, args: tuple, kwargs: dict, expected_class: type, default):
    """
    Load an instance of ``expected_class`` as indicated by ``setting_name``.

    The setting points to a callable (function or class) that will fetch or create an
    instance of the expected class. If the configuration is missing or invalid,
    or the callable throws an exception or returns the wrong type, the default is
    returned instead.

    Arguments:
        setting_name: Name of a Django setting containing a dotted module path, indicating a callable
        args: Tuple of positional arguments to pass to the callable
        kwargs: Dictionary of keyword arguments to pass to the callable
        expected_class: The callable must produce an instance of this class object (or a subclass)
        default: Object to return if any part of the lookup or loading fails
    """
    constructor_path = getattr(settings, setting_name, None)
    if constructor_path is None:
        warnings.warn(f"Event Bus setting {setting_name} is missing; component will be inactive")
        return default

    try:
        constructor = import_string(constructor_path)
        instance = constructor(*args, **kwargs)
        if isinstance(instance, expected_class):
            return instance
        else:
            warnings.warn(
                f"{constructor_path} from {setting_name} returned unexpected type {type(instance)}; "
                "component will be inactive"
            )
            return default
    except BaseException as e:
        warnings.warn(
            f"Failed to load {expected_class} from setting {setting_name}: {e!r}; "
            "component will be inactive"
        )
        return default


class EventBusProducer(ABC):
    """
    Parent class for event bus producer implementations.
    """

    @abstractmethod
    def send(
            self, *, signal: OpenEdxPublicSignal, topic: str, event_key_field: str, event_data: dict,
    ) -> None:
        """
        Send a signal event to the event bus under the specified topic.

        Arguments:
            signal: The original OpenEdxPublicSignal the event was sent to
            topic: The event bus topic for the event (without any environmental prefix)
            event_key_field: Path to the event data field to use as the event key (period-delimited
              string naming the dictionary keys to descend)
            event_data: The event data (kwargs) sent to the signal
        """


class NoEventBusProducer(EventBusProducer):
    """
    Stub implementation to "load" when no implementation is properly configured.
    """

    def send(
            self, *, signal: OpenEdxPublicSignal, topic: str, event_key_field: str, event_data: dict,
    ) -> None:
        """Do nothing."""


# .. setting_name: EVENT_BUS_PRODUCER
# .. setting_default: None
# .. setting_description: String naming a callable (function or class) that can be called to create
#   or retrieve an instance of EventBusProducer when ``openedx_events.event_bus.get_producer`` is
#   called. The format of the string is a dotted path to an attribute in a module, e.g.
#   ``some.module.path.EventBusImplementation``. This producer will be managed as a singleton
#   by openedx_events. If setting is not supplied or the callable raises an exception or does not return
#   an instance of EventBusProducer, calls to the producer will be ignored with a warning at startup.

@lru_cache  # will just be one cache entry, in practice
def get_producer() -> EventBusProducer:
    """
    Create or retrieve the producer implementation, as configured.

    If misconfigured, returns a fake implementation that can be called but does nothing.
    """
    return _try_load(
        setting_name='EVENT_BUS_PRODUCER', args=(), kwargs={},
        expected_class=EventBusProducer, default=NoEventBusProducer(),
    )


class EventBusConsumer(ABC):
    """
    Parent class for event bus consumer implementations.
    """

    @abstractmethod
    def consume_indefinitely(self) -> NoReturn:
        """
        Consume events from a topic in an infinite loop.

        Events will be converted into calls to Django signals.
        """


class NoEventBusConsumer(EventBusConsumer):
    """
    Stub implementation to "load" when no implementation is properly configured.
    """

    def consume_indefinitely(self) -> NoReturn:
        """Do nothing."""


# .. setting_name: EVENT_BUS_CONSUMER
# .. setting_default: None
# .. setting_description: String naming a callable (function or class) that can be called to create
#   or retrieve an instance of EventBusConsumer when ``openedx_events.event_bus.make_single_consumer`` is
#   called. The format of the string is a dotted path to an attribute in a module, e.g.
#   ``some.module.path.EventBusImplementation``. See docstring of ``make_single_consumer`` for
#   parameters. If setting is not supplied or the callable raises an exception or does not return
#   an instance of EventBusConsumer, calls to the consumer will be ignored with a warning at startup.


def make_single_consumer(*, topic: str, group_id: str, signal: OpenEdxPublicSignal) -> EventBusConsumer:
    """
    Construct a consumer for a given topic, group, and signal.

    If misconfigured, returns a fake implementation that does nothing.

    Arguments:
        topic: The event bus topic to consume from (without any environmental prefix)
        group_id: The consumer group to participate in
        signal: Send consumed, decoded events to the receivers of this signal
    """
    kwargs = {
        'topic': topic,
        'group_id': group_id,
        'signal': signal,
    }
    return _try_load(
        setting_name='EVENT_BUS_CONSUMER', args=(), kwargs=kwargs,
        expected_class=EventBusConsumer, default=NoEventBusConsumer(),
    )


@receiver(setting_changed)
def _reset_state(sender, **kwargs):  # pylint: disable=unused-argument
    """Reset caches when settings change during unit tests."""
    get_producer.cache_clear()
