
Internal API
============

This part of the documentation covers the internal interfaces of *reader*,
which are useful for plugins,
or if you want to use low-level functionality
without using :class:`~reader.Reader` itself.

.. warning::

    As of version |version|,
    the internal API is **not** part of the public API;
    it is not stable yet and might change without any notice.


.. _parser:

Parser
------

.. autoattribute:: reader.Reader._parser


.. module:: reader._parser

.. autofunction:: default_parser

.. autoclass:: Parser
    :members:
    :special-members: __call__


.. module:: reader._parser.requests

.. autoclass:: SessionFactory(...)
    :members:
    :special-members: __call__

.. autoclass:: SessionWrapper(...)
    :members:


Protocols
~~~~~~~~~

.. module:: reader._parser
    :noindex:

.. autoclass:: FeedArgument
    :members:

.. autoclass:: RetrieverType
    :members:
    :special-members: __call__

.. autoclass:: FeedForUpdateRetrieverType
    :members:
    :show-inheritance:

.. autoclass:: ParserType
    :members:
    :special-members: __call__

.. autoclass:: HTTPAcceptParserType
    :members:
    :show-inheritance:

.. autoclass:: EntryPairsParserType
    :members:
    :show-inheritance:


.. module:: reader._parser.requests
    :noindex:

.. autoclass:: RequestHook
    :members:
    :special-members: __call__

.. autoclass:: ResponseHook
    :members:
    :special-members: __call__


Data objects
~~~~~~~~~~~~

.. module:: reader._parser
    :noindex:

.. autoclass:: RetrieveResult
    :members:

.. module:: reader._types

.. autoclass:: ParsedFeed
    :members:

.. autoclass:: FeedData
    :members:
    :undoc-members:

.. autoclass:: EntryData
    :members:
    :undoc-members:

.. todo:: the following should be in the storage section, when we get one

.. autoclass:: FeedForUpdate
    :members:

.. autoclass:: EntryForUpdate
    :members:


.. _storage:

Storage
-------

*reader* storage is abstracted by two :abbr:`DAO (data access object)` protocols:
:class:`StorageType`, which provides the main storage,
and :class:`SearchType`, which provides search-related operations.

Currently, there's only one supported implementation, based on SQLite.

That said, it is possible to use an alternate implementation
by passing a :class:`StorageType` instance
via the ``_storage`` :func:`.make_reader` argument::

    reader = make_reader('unused', _storage=MyStorage(...))

The protocols are *mostly* stable,
but some backwards-incompatible changes are expected in the future
(known ones are marked below with *Unstable*).
The long term goal is for the storage API to become stable,
but at least one other implementation needs to exists before that.
(Working on one? :doc:`Let me know! <contributing>`)


.. admonition:: Unstable

    Currently, search is tightly-bound to a storage implementation
    (see :meth:`~.BoundSearchStorageType.make_search`).
    In the future, it may be possible to mix and match
    main storage and search implementations,
    but :class:`StorageType` will likely need
    additional capabilities to support this.


.. autoattribute:: reader.Reader._storage
.. autoattribute:: reader.Reader._search

.. module:: reader._types
    :noindex:

.. autoclass:: StorageType()
    :members:
    :special-members: __enter__, __exit__

.. autoclass:: BoundSearchStorageType()
    :members:
    :show-inheritance:

.. autoclass:: SearchType()
    :members:


Data objects
~~~~~~~~~~~~

.. autoclass:: FeedFilter
    :members:

.. autoclass:: EntryFilter
    :members:

.. autoclass:: FeedUpdateIntent
    :members:

.. autoclass:: EntryUpdateIntent
    :members:


Type aliases
~~~~~~~~~~~~

.. autodata:: TagFilter
.. autodata:: TristateFilter


Recipes
-------

.. include:: ../examples/parser_only.py
    :start-after: """
    :end-before: """  # docstring-end

.. literalinclude:: ../examples/parser_only.py
    :start-after: """  # docstring-end
