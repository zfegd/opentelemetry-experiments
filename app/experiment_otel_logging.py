import asyncio
import logging
import time

from asgiref.sync import async_to_sync
from asgiref.sync import sync_to_async

from opentelemetry_wrapper.instrument_decorator import instrument_decorate
from opentelemetry_wrapper.instrument_logging import instrument_logging

instrument_logging()


@instrument_decorate
async def bitshift(x: int, shift_by: int):
    """
    shifts left if positive, right if negative
    uses async in order to test that logging works normally
    """
    await asyncio.sleep(0.01)

    assert isinstance(x, int)
    assert isinstance(shift_by, int)

    if shift_by > 0:
        logging.debug(f'bit-shifting {x=} right by {shift_by}')
        return x << shift_by
    elif shift_by < 0:
        logging.debug(f'bit-shifting {x=} left by {-shift_by}')
        return x >> -shift_by
    else:
        logging.debug(f'bit-shifting {x=} by 0')
        return x


@instrument_decorate
async def multiply(multiplier: int, multiplicand: int):
    """
    very silly way to multiply things inspired by exponentiation-by-squaring
    constrained to only use the `bitshift` function and addition
    """
    await asyncio.sleep(0.01)

    logging.info(f'multiply {multiplier=} by {multiplicand=}')
    _negative = multiplicand < 0
    multiplicand = abs(multiplicand)

    assert multiplicand >= 0
    assert isinstance(multiplier, int)
    assert isinstance(multiplicand, int)

    accumulator = 0
    while multiplicand:
        _tmp, multiplicand = multiplicand, await bitshift(multiplicand, -1)
        if _tmp != await bitshift(multiplicand, 1):
            accumulator += multiplier
        if multiplicand:
            multiplier = await bitshift(multiplier, 1)

    return accumulator if not _negative else -accumulator


@instrument_decorate
async def square(x):
    """
    absolutely unnecessary abstraction as would be expected in enterprise code
    uses warning instead of info just for testing
    """
    await asyncio.sleep(0.01)

    assert isinstance(x, int)
    if x < 0:
        logging.warning(f'squaring absolute of negative integer abs({x=})')
    else:
        logging.info(f'squaring non-negative number {x=}')

    return await multiply(abs(x), abs(x))


@instrument_decorate
@async_to_sync
@instrument_decorate
@sync_to_async
@instrument_decorate
@async_to_sync
@instrument_decorate
async def exponentiate(base, exponent):
    """
    exponentiation-by-squaring
    constrained not to use any math other than the functions defined above
    """
    await asyncio.sleep(0.01)

    logging.info(f'exponentiate {base=} by non-negative {exponent=}')
    assert exponent >= 0
    assert isinstance(base, int)
    assert isinstance(exponent, int)

    out = 1
    while exponent:
        _tmp, exponent = exponent, await bitshift(exponent, -1)
        if _tmp != await bitshift(exponent, 1):
            out = await multiply(out, base)
        if exponent:
            base = await square(base)
    return out


if __name__ == '__main__':
    t = time.perf_counter()
    assert exponentiate(-10, 5) == -100000
    print('elapsed time:', round(time.perf_counter() - t, 10), 'seconds')
