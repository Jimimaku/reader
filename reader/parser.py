import time
import datetime
import calendar
import logging

import feedparser

from .types import Feed, Entry, Content, Enclosure
from .exceptions import ParseError, NotModified

log = logging.getLogger('reader')


HANDLERS = []

try:
    import certifi
    import ssl
    import urllib.request
    HANDLERS.append(
        urllib.request.HTTPSHandler(
            context=ssl.create_default_context(cafile=certifi.where()))
    )
except ImportError:
    pass


def _datetime_from_timetuple(tt):
    return datetime.datetime.utcfromtimestamp(calendar.timegm(tt)) if tt else None

def _get_updated_published(thing, is_rss):
    # feed.get and entry.get don't work for updated due historical reasons;
    # from the docs: "As of version 5.1.1, if this key [.updated] doesn't
    # exist but [thing].published does, the value of [thing].published
    # will be returned. [...] This mapping is temporary and will be
    # removed in a future version of feedparser."

    updated = None
    published = None
    if 'updated_parsed' in thing:
        updated = _datetime_from_timetuple(thing.updated_parsed)
    if 'published_parsed' in thing:
        published = _datetime_from_timetuple(thing.published_parsed)

    if published and not updated and is_rss:
            updated, published = published, None

    return updated, published


def _make_entry(entry, is_rss):
    assert entry.id
    updated, published = _get_updated_published(entry, is_rss)
    assert updated

    content = []
    for data in entry.get('content', ()):
        data = {k: v for k, v in data.items() if k in ('value', 'type', 'language')}
        content.append(Content(**data))
    content = tuple(content)

    enclosures = []
    for data in entry.get('enclosures', ()):
        data = {k: v for k, v in data.items() if k in ('href', 'type', 'length')}
        if 'length' in data:
            try:
                data['length'] = int(data['length'])
            except (TypeError, ValueError):
                del data['length']
        enclosures.append(Enclosure(**data))
    enclosures = tuple(enclosures)

    return Entry(
        entry.id,
        updated,
        entry.get('title'),
        entry.get('link'),
        entry.get('author'),
        published,
        entry.get('summary'),
        content or None,
        enclosures or None,
        False,
        None,
    )


def parse_feedparser(url, http_etag=None, http_last_modified=None):

    d = feedparser.parse(url, etag=http_etag, modified=http_last_modified,
                         handlers=HANDLERS)

    if d.get('status') == 304:
        raise NotModified(url)

    http_etag = d.get('etag', http_etag)
    http_last_modified = d.get('modified', http_last_modified)

    return _process_feed(url, d) + (http_etag, http_last_modified)


def _process_feed(url, d):

    if d.get('bozo'):
        exception = d.get('bozo_exception')
        if isinstance(exception, feedparser.CharacterEncodingOverride):
            log.warning("parse %s: got %r", url, exception)
        else:
            raise ParseError(url) from exception

    is_rss = d.version.startswith('rss')
    updated, _ = _get_updated_published(d.feed, is_rss)

    feed = Feed(
        url,
        updated,
        d.feed.get('title'),
        d.feed.get('link'),
        d.feed.get('author'),
        None,
    )
    entries = (_make_entry(e, is_rss) for e in d.entries)

    return feed, entries


try:
    import requests
except ImportError:
    requests = None

if requests:
    from ._feedparser_parse_data import _feedparser_parse_snippet
    try:
        import feedparser.http as feedparser_http
        import feedparser.api as feedparser_api
    except ImportError:
        feedparser_http = feedparser
        feedparser_api = feedparser


def parse_requests(url, http_etag=None, http_last_modified=None):

    url_split = urllib.parse.urlparse(url)

    if url_split.scheme not in ('http', 'https'):
        # TODO: raise ValueError
        assert not url_split.netloc
        assert not url_split.params
        assert not url_split.query
        assert not url_split.fragment
        if url_split.scheme in ('file', ):
            url = url_split.path
        else:
            url = url_split.scheme + (':' if url_split.scheme else '') + url_split.path
        return parse_feedparser(url, http_etag, http_last_modified)

    """
    Following the implementation in:
    https://github.com/kurtmckee/feedparser/blob/develop/feedparser/http.py

    "Porting" notes:

    No need to add Accept-encoding (requests seems to do this already).

    No need to add Referer / User-Agent / Authorization / custom request
    headers, as they are not exposed in the reader.parser.parse interface
    (not yet, at least).

    We should add:

    * If-None-Match (http_etag)
    * If-Modified-Since (http_last_modified)
    * Accept (feedparser.(html.)ACCEPT_HEADER)
    * A-IM ("feed")

    """

    headers = {
        'Accept': feedparser_http.ACCEPT_HEADER,
        'A-IM': 'feed',
    }
    if http_etag:
        headers['If-None-Match'] = http_etag
    if http_last_modified:
        headers['If-Modified-Since'] = http_last_modified

    try:
        response = requests.get(url, headers=headers)
        # Should we raise_for_status()? feedparser.parse() isn't.
        # Should we check the status on the feedparser.parse() result?
    except Exception as e:
        raise ParseError(url) from e

    if response.status_code == 304:
        raise NotModified(url)

    result = feedparser_api.FeedParserDict(
        bozo = False,
        entries = [],
        feed = feedparser_api.FeedParserDict(),
        headers = {},
    )

    """
    Things we should set on result, but we don't because we're not using them:

    * result['bozo'] and result['bozo_exception']
      (we're raising the exceptions directly)
    * result['etag'], result['modified'], result['modified_parsed']
      (we're returning them)
    * result['version'] and result['debug_message']
      (for 304s; we're raising the exception directly)

    Things we are setting because they are or might be used by
    _feedparser_parse_snippet:

    * result['status']
    * result['headers'] (to response.headers, a CaseInsensitiveDict)
    * result['href'] (to response.url)
    * result.newurl (for 30[01237]s, i.e. response.url != url)

    """

    result['status'] = response.status_code
    result['headers'] = response.headers
    result['href'] = response.url
    if response.url != url:
        result.newurl = response.url

    _feedparser_parse_snippet(result, response.content)

    http_etag = response.headers.get('ETag', http_etag)
    http_last_modified = response.headers.get('Last-Modified', http_last_modified)

    return _process_feed(url, result) + (http_etag, http_last_modified)


parse = parse_feedparser
if requests:
    parse = parse_requests

