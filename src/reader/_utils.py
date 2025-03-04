from __future__ import annotations

import functools
import inspect
import itertools
import logging
import pkgutil
import warnings
from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Iterator
from collections.abc import Sequence
from contextlib import AbstractContextManager
from contextlib import contextmanager
from functools import wraps
from typing import Any
from typing import cast
from typing import TypeVar


FuncType = Callable[..., Any]
F = TypeVar('F', bound=FuncType)

_T = TypeVar('_T')
_U = TypeVar('_U')


class MissingType:
    def __repr__(self) -> str:
        return "no value"


#: Sentinel object used to detect if the `default` argument was provided."""
MISSING = MissingType()


def zero_or_one(
    it: Iterable[_U],
    make_exc: Callable[[], Exception],
    default: MissingType | _T = MISSING,
) -> _U | _T:
    things = list(it)
    if len(things) == 0:
        if isinstance(default, MissingType):
            raise make_exc()
        return default
    elif len(things) == 1:
        return things[0]
    else:
        assert False, "shouldn't get here"  # noqa: B011; # pragma: no cover


def exactly_one(it: Iterable[_U]) -> _U:
    things = list(it)
    if len(things) == 1:
        return things[0]
    else:
        assert False, "shouldn't get here"  # noqa: B011; # pragma: no cover


def join_paginated_iter(
    get_things: Callable[[int, _T | None], Iterable[tuple[_U, _T]]],
    chunk_size: int,
    last: _T | None = None,
    limit: int = 0,
) -> Iterable[_U]:
    """
    count_to_ten(4, None) -> ('one', 1), ..., ('four', 4)
    count_to_ten(0, None) -> ('one', 1), ..., ('ten', 10)
    count_to_ten(4, 4) -> ('five', 5), ..., ('eight', 8)
    count_to_ten(0, 4) -> ('five', 5), ..., ('ten', 10)

    join_paginated_iter(count_to_ten, 4, None) -> one, ..., ten (3 calls)
    join_paginated_iter(count_to_ten, 0, None) -> one, ..., ten (1 call)
    join_paginated_iter(count_to_ten, 4, 4) -> five, ..., ten (2 calls)
    join_paginated_iter(count_to_ten, 0, 4) -> five, ..., ten (1 call)
    join_paginated_iter(count_to_ten, 4, 4, limit=5) -> five, ..., nine (2 calls)
    join_paginated_iter(count_to_ten, 0, 4, limit=5) -> five, ..., nine (1 call)

    """
    # At the moment get_things must take positional arguments.
    # We could make it work with kwargs by using protocols,
    # but mypy gets confused about partials with kwargs.
    # https://github.com/python/mypy/issues/1484

    if not chunk_size:
        # When chunk_size is 0, don't chunk the query.
        #
        # This will ensure there are no missing/duplicated entries, but
        # will block database writes until the whole generator is consumed.
        #
        # Currently not exposed through the public API.
        #
        things = get_things(limit, last)
        yield from (t for t, _ in things)
        return

    remaining = limit

    while True:
        if limit:
            if not remaining:
                break
            to_get = min(remaining, chunk_size)
            remaining = max(0, remaining - to_get)
        else:
            to_get = chunk_size

        things = list(get_things(to_get, last))
        if not things:
            break

        _, last = things[-1]

        yield from (t for t, _ in things)

        if len(things) < to_get:
            break


def chunks(n: int, iterable: Iterable[_T]) -> Iterable[Iterable[_T]]:
    """grouper(2, 'ABCDE') --> AB CD E"""
    # based on https://stackoverflow.com/a/8991553
    it = iter(iterable)
    while True:
        chunk = itertools.islice(it, n)
        try:
            first = next(chunk)
        except StopIteration:
            break
        yield itertools.chain([first], chunk)


def count_consumed(it: Iterable[_T]) -> tuple[Iterable[_T], Callable[[], int]]:
    consumed = 0

    def wrapper() -> Iterable[_T]:
        nonlocal consumed
        for e in it:
            yield e
            consumed += 1

    def get_count() -> int:
        return consumed

    return wrapper(), get_count


MapFunction = Callable[[Callable[[_T], _U], Iterable[_T]], Iterator[_U]]
MapContextManager = AbstractContextManager[MapFunction[_T, _U]]


@contextmanager
def make_pool_map(workers: int) -> Iterator[MapFunction[_T, _U]]:
    # We are using concurrent.futures instead of multiprocessing.dummy
    # because the latter doesn't work on some environments (e.g. AWS Lambda).
    # We are not using executor.map() because it consumes the entire iterable.

    # lazy import (https://github.com/lemon24/reader/issues/297)
    import concurrent.futures

    executor = concurrent.futures.ThreadPoolExecutor(workers)

    def imap_unordered(fn: Callable[[_T], _U], iterable: Iterable[_T]) -> Iterator[_U]:
        iterable = iter(iterable)
        iterable_ended = False
        pending: set[concurrent.futures.Future[_U]] = set()

        while pending or not iterable_ended:
            while len(pending) < workers and not iterable_ended:
                try:
                    arg = next(iterable)
                except StopIteration:
                    iterable_ended = True
                else:
                    pending.add(executor.submit(fn, arg))

            if not pending:  # pragma: no cover
                return

            done, pending = concurrent.futures.wait(
                pending, return_when=concurrent.futures.FIRST_COMPLETED
            )
            while done:
                yield done.pop().result()

    with executor:
        yield imap_unordered


class PrefixLogger(logging.LoggerAdapter):  # type: ignore
    # if needed, add: with log.push('another prefix'): ...

    def __init__(self, logger: logging.Logger, prefixes: Sequence[str] = ()):
        super().__init__(logger, {})
        self.prefixes = tuple(prefixes)

    @staticmethod
    def _escape(s: str) -> str:  # pragma: no cover
        return '%%'.join(s.split('%'))

    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:  # pragma: no cover
        return ': '.join(tuple(self._escape(p) for p in self.prefixes) + (msg,)), kwargs


_DEPRECATED_FUNC_WARNING = """\
{old_name}() is deprecated and will be removed in reader {removed_in}. \
Use {new_name}() instead.\
"""
_DEPRECATED_FUNC_DOCSTRING = """\
Deprecated alias for :meth:`{new_name}`.
{doc}
.. deprecated:: {deprecated_in}
    This method will be removed in *reader* {removed_in}.
    Use :meth:`{new_name}` instead.

"""

_DEPRECATED_PROP_WARNING = """\
{old_name} is deprecated and will be removed in reader {removed_in}. \
Use {new_name} instead.\
"""
_DEPRECATED_PROP_DOCSTRING = """\
Deprecated variant of :attr:`{new_name}`.
{doc}
.. deprecated:: {deprecated_in}
    This property will be removed in *reader* {removed_in}.
    Use :attr:`{new_name}` instead.

"""


def _deprecated_wrapper(
    old_name: str,
    new_name: str,
    func: F,
    deprecated_in: str,
    removed_in: str,
    doc: str = '',
    warning_template: str = _DEPRECATED_FUNC_WARNING,
    docstring_template: str = _DEPRECATED_FUNC_DOCSTRING,
) -> F:
    format_kwargs = dict(locals())

    @wraps(func)
    def old_func(*args, **kwargs):  # type: ignore
        warnings.warn(
            warning_template.format_map(format_kwargs),
            DeprecationWarning,
            stacklevel=2,
        )
        return func(*args, **kwargs)

    old_func.__name__ = old_name
    old_func.__doc__ = docstring_template.format_map(format_kwargs)
    return cast(F, old_func)


def deprecated_wrapper(
    old_name: str, func: F, deprecated_in: str, removed_in: str
) -> F:
    return _deprecated_wrapper(old_name, func.__name__, func, deprecated_in, removed_in)


def deprecated(
    new_name: str, deprecated_in: str, removed_in: str, property: bool = False
) -> Callable[[F], F]:
    if not property:
        kwargs = {}
    else:
        kwargs = dict(
            warning_template=_DEPRECATED_PROP_WARNING,
            docstring_template=_DEPRECATED_PROP_DOCSTRING,
        )

    def decorator(func: F) -> F:
        doc = inspect.getdoc(func) or ''
        if doc:  # pragma: no cover
            doc = '\n' + doc + '\n'
        return _deprecated_wrapper(
            func.__name__, new_name, func, deprecated_in, removed_in, doc=doc, **kwargs
        )

    return decorator


def _name(thing: object) -> str:
    name = getattr(thing, '__name__', None)
    if name:
        return str(name)
    for attr in ('__func__', 'func'):
        new_thing = getattr(thing, attr, None)
        if new_thing:  # pragma: no cover
            return _name(new_thing)
    return '<noname>'


class BetterStrPartial(functools.partial[_T]):
    __slots__ = ()

    def __str__(self) -> str:
        name = _name(self.func)
        parts = [repr(getattr(v, 'resource_id', v)) for v in self.args]
        parts.extend(
            f"{k}={getattr(v, 'resource_id', v)!r}" for k, v in self.keywords.items()
        )
        return f"{name}({', '.join(parts)})"


def lazy_import(module: str, names: list[str]) -> Callable[[str], Any]:
    def __getattr__(name: str) -> Any:
        if name not in names:  # pragma: no cover
            raise AttributeError(f"module {module!r} has no attribute {name!r}")
        return pkgutil.resolve_name(f'{module}._lazy:{name}')

    return __getattr__
