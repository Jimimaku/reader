from datetime import datetime

import pytest
from fakeparser import FailingParser
from fakeparser import NotModifiedParser
from fakeparser import Parser
from test_reader_private import CustomParser
from test_reader_private import CustomRetriever

from reader import EntryUpdateStatus
from reader import ParseError
from reader._types import EntryData


def test_after_entry_update_hooks(reader):
    reader._parser = parser = Parser()
    parser.tzinfo = False

    plugin_calls = []

    def first_plugin(r, e, s):
        assert r is reader
        plugin_calls.append((first_plugin, e, s))

    def second_plugin(r, e, s):
        assert r is reader
        plugin_calls.append((second_plugin, e, s))

    feed = parser.feed(1, datetime(2010, 1, 1))
    one = parser.entry(1, 1, datetime(2010, 1, 1))
    reader.add_feed(feed.url)
    reader.after_entry_update_hooks.append(first_plugin)
    reader.update_feeds()
    assert plugin_calls == [(first_plugin, one, EntryUpdateStatus.NEW)]
    assert {e.id for e in reader.get_entries()} == {'1, 1'}

    plugin_calls[:] = []

    feed = parser.feed(1, datetime(2010, 1, 2))
    one = parser.entry(1, 1, datetime(2010, 1, 2))
    two = parser.entry(1, 2, datetime(2010, 1, 2))
    reader.after_entry_update_hooks.append(second_plugin)
    reader.update_feeds()
    assert plugin_calls == [
        (first_plugin, two, EntryUpdateStatus.NEW),
        (second_plugin, two, EntryUpdateStatus.NEW),
        (first_plugin, one, EntryUpdateStatus.MODIFIED),
        (second_plugin, one, EntryUpdateStatus.MODIFIED),
    ]
    assert {e.id for e in reader.get_entries()} == {'1, 1', '1, 2'}


def test_after_entry_update_hooks_add_entry(reader):
    reader.add_feed('1')

    plugin_calls = []

    def first_plugin(r, e, s):
        assert r is reader
        plugin_calls.append((first_plugin, e, s))

    def second_plugin(r, e, s):
        assert r is reader
        plugin_calls.append((second_plugin, e, s))

    reader.after_entry_update_hooks.append(first_plugin)
    reader.after_entry_update_hooks.append(second_plugin)

    entry = EntryData('1', '1, 1', title='title')

    reader.add_entry(entry)

    assert plugin_calls == [
        (first_plugin, entry, EntryUpdateStatus.NEW),
        (second_plugin, entry, EntryUpdateStatus.NEW),
    ]


def test_feed_update_hooks(reader):
    reader._parser = parser = Parser()
    parser.tzinfo = False

    plugin_calls = []

    def before_plugin(r, f):
        assert r is reader
        plugin_calls.append((before_plugin, f))

    def first_plugin(r, f):
        assert r is reader
        plugin_calls.append((first_plugin, f))

    def second_plugin(r, f):
        assert r is reader
        plugin_calls.append((second_plugin, f))

    # TODO: these should all be different tests

    # base case
    one = parser.feed(1, datetime(2010, 1, 1))
    parser.entry(1, 1, datetime(2010, 1, 1))
    reader.add_feed(one)
    reader.after_feed_update_hooks.append(first_plugin)
    reader.before_feed_update_hooks.append(before_plugin)
    reader.update_feeds()
    assert plugin_calls == [(before_plugin, one.url), (first_plugin, one.url)]

    plugin_calls[:] = []

    # gets called if something changes
    parser.entry(1, 1, datetime(2010, 1, 2))
    reader.update_feeds()
    assert plugin_calls == [(before_plugin, one.url), (first_plugin, one.url)]

    plugin_calls[:] = []

    # gets called even if there was no change
    reader.update_feeds()
    assert plugin_calls == [(before_plugin, one.url), (first_plugin, one.url)]

    plugin_calls[:] = []

    # gets called even if the feed was not modified
    reader._parser = NotModifiedParser()
    reader.update_feeds()
    assert plugin_calls == [(before_plugin, one.url), (first_plugin, one.url)]

    plugin_calls[:] = []

    # gets called even if there was an error
    reader._parser = FailingParser()
    reader.update_feeds()
    assert plugin_calls == [(before_plugin, one.url), (first_plugin, one.url)]

    plugin_calls[:] = []

    # plugin order and feed order is maintained
    reader._parser = parser
    two = parser.feed(2, datetime(2010, 1, 1))
    reader.add_feed(two)
    reader.after_feed_update_hooks.append(second_plugin)
    reader.update_feeds()
    assert plugin_calls == [
        (before_plugin, one.url),
        (first_plugin, one.url),
        (second_plugin, one.url),
        (before_plugin, two.url),
        (first_plugin, two.url),
        (second_plugin, two.url),
    ]

    plugin_calls[:] = []

    # update_feed() only runs hooks for that plugin
    reader.update_feed(one)
    assert plugin_calls == [
        (before_plugin, one.url),
        (first_plugin, one.url),
        (second_plugin, one.url),
    ]


def test_feeds_update_hooks(reader):
    reader._parser = parser = Parser()
    parser.tzinfo = False

    plugin_calls = []

    def before_feed_plugin(r, f):
        assert r is reader
        plugin_calls.append((before_feed_plugin, f))

    def after_feed_plugin(r, f):
        assert r is reader
        plugin_calls.append((after_feed_plugin, f))

    def before_feeds_plugin(r):
        assert r is reader
        plugin_calls.append((before_feeds_plugin,))

    def after_feeds_plugin(r):
        assert r is reader
        plugin_calls.append((after_feeds_plugin,))

    reader.before_feed_update_hooks.append(before_feed_plugin)
    reader.after_feed_update_hooks.append(after_feed_plugin)
    reader.before_feeds_update_hooks.append(before_feeds_plugin)
    reader.after_feeds_update_hooks.append(after_feeds_plugin)

    # TODO: these should all be different tests

    # no feeds
    reader.update_feeds()
    assert plugin_calls == [(before_feeds_plugin,), (after_feeds_plugin,)]

    plugin_calls[:] = []

    # two feeds + feed vs feeds order
    one = parser.feed(1, datetime(2010, 1, 1))
    two = parser.feed(2, datetime(2010, 1, 1))
    reader.add_feed(one)
    reader.add_feed(two)
    reader.update_feeds()
    assert plugin_calls[0] == (before_feeds_plugin,)
    assert plugin_calls[-1] == (after_feeds_plugin,)
    assert set(plugin_calls[1:-1]) == {
        (before_feed_plugin, one.url),
        (after_feed_plugin, one.url),
        (before_feed_plugin, two.url),
        (after_feed_plugin, two.url),
    }

    plugin_calls[:] = []

    # not called for update_feed()
    reader.update_feed(one)
    assert set(plugin_calls) == {
        (before_feed_plugin, one.url),
        (after_feed_plugin, one.url),
    }

    plugin_calls[:] = []

    # called even if there's an error
    reader._parser = FailingParser()
    reader.update_feeds()
    assert plugin_calls[0] == (before_feeds_plugin,)
    assert plugin_calls[-1] == (after_feeds_plugin,)
    assert set(plugin_calls[1:-1]) == {
        (before_feed_plugin, one.url),
        (after_feed_plugin, one.url),
        (before_feed_plugin, two.url),
        (after_feed_plugin, two.url),
    }


# TODO: test relative order of different hooks


@pytest.mark.parametrize(
    'hook_name',
    [
        'after_entry_update_hooks',
        'before_feed_update_hooks',
        'after_feed_update_hooks',
        'before_feeds_update_hooks',
        'after_feeds_update_hooks',
    ],
)
@pytest.mark.xfail(raises=RuntimeError, strict=True)
def test_update_hook_unexpected_exception(reader, update_feeds_iter, hook_name):
    if 'simulated' in update_feeds_iter.__name__ and '_feeds_' in hook_name:
        pytest.skip("does not apply")

    reader._parser = parser = Parser()
    for feed_id in 1, 2, 3:
        reader.add_feed(parser.feed(feed_id))
    parser.entry(1, 1)

    exc = RuntimeError('error')

    def hook(reader, obj=None, *_):
        if '_entry_' in hook_name:
            feed_url = obj.feed_url
        elif '_feed_' in hook_name:
            feed_url = obj
        elif '_feeds_' in hook_name:
            feed_url = None
        else:
            assert False, hook_name
        if not feed_url or feed_url == '1':
            raise exc

    getattr(reader, hook_name).append(hook)

    rv = {int(r.url): r for r in update_feeds_iter(reader)}

    assert rv[1].error.__cause__ is exc
    assert isinstance(rv[1].error, ParseError)
    assert rv[1].error.__cause__ is exc
    assert rv[2].updated_feed
    assert rv[3].updated_feed


@pytest.mark.parametrize(
    'target_name, method_name',
    [
        ('retriever', '__call__'),
        ('retriever', 'process_feed_for_update'),
        ('parser', '__call__'),
        ('parser', 'process_entry_pairs'),
    ],
)
@pytest.mark.xfail(raises=RuntimeError, strict=True)
def test_retriever_parser_unexpected_exception(
    reader, update_feeds_iter, target_name, method_name
):
    retriever = CustomRetriever()
    reader._parser.mount_retriever('test:', retriever)
    parser = CustomParser()
    reader._parser.mount_parser_by_mime_type(parser)

    for feed_id in 1, 2, 3:
        reader.add_feed(f'test:{feed_id}')

    exc = RuntimeError('error')

    def raise_exc(name, url):
        if name == method_name and '1' in url:
            raise exc

    locals()[target_name].raise_exc = raise_exc

    rv = {int(r.url.rpartition(':')[2]): r for r in update_feeds_iter(reader)}

    assert rv[1].error.__cause__ is exc
    assert isinstance(rv[1].error, ParseError)
    assert rv[1].error.__cause__ is exc
    assert rv[2].updated_feed
    assert rv[3].updated_feed


@pytest.mark.parametrize('hook_name', ['request_hooks', 'response_hooks'])
def test_session_hook_unexpected_exception(
    reader, data_dir, update_feeds_iter, requests_mock, hook_name
):
    for feed_id in 1, 2, 3:
        url = f'http://example.com/{feed_id}'
        requests_mock.get(
            url,
            text=data_dir.joinpath('full.atom').read_text(),
            headers={'content-type': 'application/atom+xml'},
        )
        reader.add_feed(url)

    exc = RuntimeError('error')

    def hook(session, obj, *_, **__):
        if '1' in obj.url:
            raise exc

    getattr(reader._parser.session_factory, hook_name).append(hook)

    rv = {int(r.url.rpartition('/')[2]): r for r in update_feeds_iter(reader)}

    assert rv[1].error.__cause__ is exc
    assert isinstance(rv[1].error, ParseError)
    assert rv[1].error.__cause__ is exc
    assert rv[2].updated_feed
    assert rv[3].updated_feed
