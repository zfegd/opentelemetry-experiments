import datetime
import json
import logging
import sys
from functools import lru_cache
from functools import update_wrapper
from functools import wraps
from pathlib import Path
from typing import Dict
from typing import Iterable
from typing import List
from typing import Optional
from typing import TextIO
from typing import Tuple
from typing import Union

from opentelemetry.instrumentation.logging import LoggingInstrumentor

from opentelemetry_wrapper.instrument_decorator import instrument_decorate
from opentelemetry_wrapper.utils.json_encoder import jsonable_encoder

# write IDs as 0xBEEF instead of BEEF so it matches the trace json exactly
LOGGING_FORMAT_VERBOSE = (
    '%(asctime)s '
    '%(levelname)-8s '
    '[%(name)s] '
    '[%(filename)s:%(funcName)s:%(lineno)d] '
    '[trace_id=0x%(otelTraceID)s span_id=0x%(otelSpanID)s resource.service.name=%(otelServiceName)s] '
    '- %(message)s'
)

# in the short format, write it as a [traceparent header](https://www.w3.org/TR/trace-context/#traceparent-header)
LOGGING_FORMAT_MINIMAL = (
    '%(levelname)-8s '
    '%(otelServiceName)s '
    '[00-%(otelTraceID)s-%(otelSpanID)s-01] '
    '[%(name)s:%(module)s:%(funcName)s] '
    '%(message)s'
)


class JsonFormatter(logging.Formatter):
    """
    converts a LogRecord to a JSON string
    """

    def __init__(self,
                 keys: Optional[Union[Tuple[str, ...], List[str], Dict[str, str]]] = None,
                 *,
                 datefmt: Optional[str] = None,
                 ensure_ascii: bool = False,
                 allow_nan: bool = True,
                 indent: Optional[int] = None,
                 separators: Optional[Tuple[str, str]] = None,
                 sort_keys: bool = False,
                 ) -> None:
        """
        see https://docs.python.org/3/library/logging.html#logrecord-attributes for record keys
        (opentelemetry also adds `otelSpanID`, `otelTraceID`, and `otelServiceName`)

        :param keys: list of LogRecord attributes, or mapper from LogRecord attribute name -> output json key name
        :param datefmt: date format string; if not set, defaults to ISO8601
        :param ensure_ascii: see `json.dumps` docs
        :param allow_nan: see `json.dumps` docs
        :param indent: see `json.dumps` docs
        :param separators: see `json.dumps` docs
        :param sort_keys: see `json.dumps` docs
        """

        super().__init__(datefmt)

        self._keys: Optional[Dict[str, str]]
        if isinstance(keys, dict):
            self._keys = dict()
            self._keys.update(keys)
        elif not isinstance(keys, str) and isinstance(keys, Iterable):
            self._keys = dict()
            for key in keys:
                assert isinstance(key, str), key
                self._keys[key] = key
        elif keys is None:
            self._keys = None
        else:
            raise TypeError(keys)

        self.ensure_ascii = ensure_ascii
        self.allow_nan = allow_nan
        self.indent = indent
        self.separators = separators
        self.sort_keys = sort_keys

        # noinspection PyTypeChecker
        self.tz = datetime.datetime.now(datetime.timezone.utc).astimezone().tzinfo

    def usesTime(self):
        return self._keys is None or 'asctime' in self._keys

    def formatMessage(self, record: logging.LogRecord):
        raise DeprecationWarning

    # flake8: noqa: C901
    def format(self, record):
        """
        Format the specified record as text.

        The record's attribute dictionary is used as the operand to a
        string formatting operation which yields the returned string.
        Before formatting the dictionary, a couple of preparatory steps
        are carried out. The message attribute of the record is computed
        using LogRecord.getMessage(). If the formatting string uses the
        time (as determined by a call to usesTime(), formatTime() is
        called to format the event time. If there is exception information,
        it is formatted using formatException() and appended to the message.
        """
        # add `message` but catch errors
        try:
            record.message = record.getMessage()
        except TypeError:
            record.message = f'MSG={repr(record.msg)} ARGS={repr(record.args)}'

        # add `asctime`, `tz_name`, and `tz_utc_offset_seconds`
        if self.usesTime():
            record.tz_name = self.tz.tzname(None)
            record.tz_utc_offset_seconds = self.tz.utcoffset(None).seconds
            if self.datefmt:
                record.asctime = self.formatTime(record, self.datefmt)
            else:
                record.asctime = datetime.datetime.fromtimestamp(record.created, tz=self.tz).isoformat()

        # add `exc_text`
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)

        if self._keys is not None:
            log_data = {k: getattr(record, v, None) for k, v in self._keys.items()}
        else:
            log_data = record.__dict__

        # noinspection PyBroadException
        try:
            safe_log_data = jsonable_encoder(log_data)

        # failsafe: stringify everything using `repr()`
        except Exception:
            safe_log_data = dict()
            for k, v in log_data.items():

                # stringify key
                if not isinstance(k, str):
                    # noinspection PyBroadException
                    try:
                        k = repr(k)
                    except Exception:
                        continue  # failed, skip key

                # encode value
                if isinstance(v, (int, float, bool, str, type(None))):
                    safe_log_data[k] = v
                else:
                    # noinspection PyBroadException
                    try:
                        safe_log_data[k] = repr(v)
                    except Exception:
                        continue  # failed, skip key

        # truncate extremely long things
        # todo: make the length a specifiable parameter
        # todo: handle other jsonable object types more intelligently
        for k, v in safe_log_data.items():
            if isinstance(v, str) and len(v) > 10000:
                k[v] = f'{v[:9985]}... (truncated)'

        return json.dumps(safe_log_data,
                          ensure_ascii=self.ensure_ascii,
                          allow_nan=self.allow_nan,
                          indent=self.indent,
                          separators=self.separators,
                          sort_keys=self.sort_keys)


@lru_cache  # avoid creating duplicate handlers
def get_json_handler(*,
                     level: int = logging.NOTSET,
                     path: Optional[Path] = None,
                     stream: Optional[TextIO] = None,
                     ) -> logging.Handler:
    if path is not None and stream is not None:
        raise ValueError('cannot set both path and stream')

    if path is not None:
        handler = logging.FileHandler(path)
    elif stream is not None:
        handler = logging.StreamHandler(stream=stream)
    else:
        handler = logging.StreamHandler(stream=sys.stderr)

    handler.setFormatter(JsonFormatter())
    handler.setLevel(level)
    return handler


@instrument_decorate
def instrument_logging(*,
                       level: int = logging.NOTSET,
                       print_json: bool = True,
                       verbose: bool = True,
                       force_reinstrumentation: bool = False,
                       ) -> None:
    """
    this function is (by default) idempotent; calling it multiple times has no additional side effects

    :param print_json:
    :param verbose:
    :param force_reinstrumentation:
    :param level:
    :return:
    """
    _instrumentor = LoggingInstrumentor()
    if _instrumentor.is_instrumented_by_opentelemetry:
        if force_reinstrumentation:
            _instrumentor.uninstrument()
        else:
            return
    _instrumentor.instrument(set_logging_format=False)
    old_factory = logging.getLogRecordFactory()

    # the instrumentor failed to use the @wraps decorator so let's do it for them
    # noinspection PyProtectedMember
    if LoggingInstrumentor._old_factory is not None:
        # noinspection PyProtectedMember
        update_wrapper(old_factory, LoggingInstrumentor._old_factory)

    @wraps(old_factory)
    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)

        # we want the trace-id and span-id in a log to match the span it was created in
        # so we format it to match
        # note that logs outside a span will be assigned an invalid trace-id and span-id (all zeroes)
        record.otelTraceID = f'0x{int(record.otelTraceID, 16):032x}'
        record.otelSpanID = f'0x{int(record.otelSpanID, 16):016x}'

        return record

    logging.setLogRecordFactory(record_factory)

    # output as json
    if print_json:
        # todo: take in appropriate args to specify an output (e.g. to a path or stream)
        # todo: re-instrument correctly if args are different
        json_handler = get_json_handler(level=level)
        if json_handler not in logging.root.handlers:
            logging.root.addHandler(json_handler)
        logging.root.setLevel(level)

    # output as above logging string format
    else:
        # force overwrite of logging basic config since their instrumentor doesn't do it correctly
        logging.basicConfig(format=LOGGING_FORMAT_VERBOSE if verbose else LOGGING_FORMAT_MINIMAL,
                            level=level,
                            force=True,
                            )
