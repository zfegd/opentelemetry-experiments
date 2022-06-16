import fastapi
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import Span
from starlette.datastructures import Headers
from starlette.types import Scope

from otel_instrumentation.instrument_decorator import instrument_decorate

_HEADER_ATTRIBUTES = (
    # subset of headers set in cookiecutter's OPA file
    'x-pf-number',
    'x-client-id',
    'x-preferred-username',
    # 'x-full-name',
    # 'x-given-name',
    # 'x-family-name',
    'x-resource-access',
    # 'x-realm-roles',
    # 'x-groups',
)


def request_hook(span: Span, scope: Scope) -> None:
    """
    add span attributes from headers
    note: RFC 7230 says header keys and values should be ASCII
    """
    headers = dict(Headers(scope=scope))  # keys are lowercase latin-1 (ascii)
    for header_name in _HEADER_ATTRIBUTES:
        # null values are silently dropped by the attribute setter
        # so we don't need an explicit check if the header exists
        span.set_attribute(header_name, headers.get(header_name.lower()))


@instrument_decorate
def instrument_fastapi_app(app: fastapi.FastAPI) -> fastapi.FastAPI:
    """
    instrument a FastAPI app
    also instruments logging and requests (if requests exists)
    this function is idempotent; calling it multiple times has no additional side effects
    """

    if not getattr(app, '_is_instrumented_by_opentelemetry', None):
        FastAPIInstrumentor.instrument_app(app,
                                           server_request_hook=request_hook,
                                           client_request_hook=request_hook,
                                           )
    return app


_WRAPPED = None


@instrument_decorate
def instrument_fastapi() -> None:
    """
    this function is idempotent; calling it multiple times has no additional side effects
    """
    _instrumentor = FastAPIInstrumentor()
    if not _instrumentor.is_instrumented_by_opentelemetry:
        _instrumentor.instrument(server_request_hook=request_hook,
                                 client_request_hook=request_hook,
                                 )
