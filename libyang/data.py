# Copyright (c) 2020 6WIND S.A.
# SPDX-License-Identifier: MIT

from _libyang import ffi
from _libyang import lib

from .schema import Module
from .schema import SContainer
from .schema import SLeaf
from .schema import SLeafList
from .schema import SList
from .schema import SNode
from .schema import SRpc
from .schema import Type
from .util import c2str
from .util import str2c


#------------------------------------------------------------------------------
def printer_flags(with_siblings=False, pretty=False, keep_empty_containers=False,
                  trim_default_values=False, include_implicit_defaults=False):
    flags = 0
    if with_siblings:
        flags |= lib.LYP_WITHSIBLINGS
    if pretty:
        flags |= lib.LYP_FORMAT
    if keep_empty_containers:
        flags |= lib.LYP_KEEPEMPTYCONT
    if trim_default_values:
        flags |= lib.LYP_WD_TRIM
    if include_implicit_defaults:
        flags |= lib.LYP_WD_ALL
    return flags


#------------------------------------------------------------------------------
def data_format(fmt_string):
    if fmt_string == 'json':
        return lib.LYD_JSON
    if fmt_string == 'xml':
        return lib.LYD_XML
    if fmt_string == 'lyb':
        return lib.LYD_LYB
    raise ValueError('unknown data format: %r' % fmt_string)


#------------------------------------------------------------------------------
def path_flags(update=False, rpc_output=False, no_parent_ret=False):
    flags = 0
    if update:
        flags |= lib.LYD_PATH_OPT_UPDATE
    if rpc_output:
        flags |= lib.LYD_PATH_OPT_OUTPUT
    if no_parent_ret:
        flags |= lib.LYD_PATH_OPT_NOPARENTRET
    return flags


#------------------------------------------------------------------------------
def parser_flags(data=False, config=False, strict=False, trusted=False,
                 no_yanglib=False):
    flags = 0
    if data:
        flags |= lib.LYD_OPT_DATA
    if config:
        flags |= lib.LYD_OPT_CONFIG
    if strict:
        flags |= lib.LYD_OPT_STRICT
    if trusted:
        flags |= lib.LYD_OPT_TRUSTED
    if no_yanglib:
        flags |= lib.LYD_OPT_DATA_NO_YANGLIB
    return flags


#------------------------------------------------------------------------------
class DNode(object):
    """
    Data tree node.
    """
    def __init__(self, context, node_p):
        """
        :arg Context context:
            The libyang.Context python object.
        :arg struct lyd_node * node_p:
            The pointer to the C structure allocated by libyang.so.
        """
        self.context = context
        self._node = ffi.cast('struct lyd_node *', node_p)

    def name(self):
        return c2str(self._node.schema.name)

    def module(self):
        mod = lib.lyd_node_module(self._node)
        if not mod:
            raise self.context.error('cannot get module')
        return Module(self.context, mod)

    def schema(self):
        return SNode.new(self.context, self._node.schema)

    def parent(self):
        if not self._node.parent:
            return None
        return self.new(self.context, self._node.parent)

    def root(self):
        node = self
        while node.parent() is not None:
            node = node.parent()
        return node

    def first_sibling(self):
        n = lib.lyd_first_sibling(self._node)
        if n == self._node:
            return self
        return self.new(self.context, n)

    def siblings(self, include_self=True):
        n = lib.lyd_first_sibling(self._node)
        while n:
            if n == self._node:
                if include_self:
                    yield self
            else:
                yield self.new(self.context, n)
            n = n.next

    def find_one(self, xpath):
        try:
            return next(self.find_all(xpath))
        except StopIteration:
            return None

    def find_all(self, xpath):
        node_set = lib.lyd_find_path(self._node, str2c(xpath))
        if not node_set:
            raise self.context.error('cannot find path: %s', xpath)
        try:
            for i in range(node_set.number):
                yield DNode.new(self.context, node_set.d[i])
        finally:
            lib.ly_set_free(node_set)

    def path(self):
        path = lib.lyd_path(self._node)
        try:
            return c2str(path)
        finally:
            lib.free(path)

    def validate(self, data=False, config=False, strict=False, trusted=False,
                 no_yanglib=False):
        flags = parser_flags(
            data=data, config=config, strict=strict, trusted=trusted,
            no_yanglib=no_yanglib)
        node_p = ffi.new('struct lyd_node **')
        node_p[0] = self._node
        ret = lib.lyd_validate(node_p, flags, ffi.NULL)
        if ret != 0:
            self.context.error('validation failed')

    def dump_str(self, fmt,
                 with_siblings=False,
                 pretty=False,
                 include_implicit_defaults=False,
                 trim_default_values=False,
                 keep_empty_containers=False):
        flags = printer_flags(
            with_siblings=with_siblings, pretty=pretty,
            include_implicit_defaults=include_implicit_defaults,
            trim_default_values=trim_default_values,
            keep_empty_containers=keep_empty_containers)
        buf = ffi.new('char **')
        fmt = data_format(fmt)
        ret = lib.lyd_print_mem(buf, self._node, fmt, flags)
        if ret != 0:
            raise self.context.error('cannot print node')
        try:
            return c2str(buf[0])
        finally:
            lib.free(buf[0])

    def dump_file(self, fileobj, fmt,
                  with_siblings=False,
                  pretty=False,
                  include_implicit_defaults=False,
                  trim_default_values=False,
                  keep_empty_containers=False):
        flags = printer_flags(
            with_siblings=with_siblings, pretty=pretty,
            include_implicit_defaults=include_implicit_defaults,
            trim_default_values=trim_default_values,
            keep_empty_containers=keep_empty_containers)
        fmt = data_format(fmt)
        ret = lib.lyd_print_fd(fileobj.fileno(), self._node, fmt, flags)
        if ret != 0:
            raise self.context.error('cannot print node')

    def free(self, with_siblings=True):
        try:
            if with_siblings:
                lib.lyd_free_withsiblings(self._node)
            else:
                lib.lyd_free(self._node)
        finally:
            self._node = None

    def __repr__(self):
        cls = self.__class__
        return '<%s.%s: %s>' % (cls.__module__, cls.__name__, str(self))

    def __str__(self):
        return self.name()

    NODETYPE_CLASS = {}

    @classmethod
    def register(cls, *nodetypes):
        def _decorator(nodeclass):
            for t in nodetypes:
                cls.NODETYPE_CLASS[t] = nodeclass
            return nodeclass
        return _decorator

    @classmethod
    def new(cls, context, node_p):
        node_p = ffi.cast('struct lyd_node *', node_p)
        nodecls = cls.NODETYPE_CLASS.get(node_p.schema.nodetype, DNode)
        return nodecls(context, node_p)


#------------------------------------------------------------------------------
@DNode.register(SNode.CONTAINER)
class DContainer(DNode):

    def create_path(self, path, value=None, rpc_output=False):
        return self.context.create_data_path(
            path, parent=self, value=value, rpc_output=rpc_output)

    def children(self):
        child = self._node.child
        while child:
            yield DNode.new(self.context, child)
            child = child.next

    def __iter__(self):
        return self.children()


#------------------------------------------------------------------------------
@DNode.register(SNode.RPC)
class DRpc(DContainer):
    pass


#------------------------------------------------------------------------------
@DNode.register(SNode.LIST)
class DList(DContainer):
    pass


#------------------------------------------------------------------------------
@DNode.register(SNode.LEAF)
class DLeaf(DNode):

    def __init__(self, context, node_p):
        DNode.__init__(self, context, node_p)
        self._leaf = ffi.cast('struct lyd_node_leaf_list *', node_p)

    def value(self):
        if self._leaf.value_type == Type.EMPTY:
            return None
        if self._leaf.value_type in Type.NUM_TYPES:
            return int(c2str(self._leaf.value_str))
        if self._leaf.value_type in (
                Type.STRING, Type.BINARY, Type.ENUM, Type.IDENT, Type.BITS):
            return c2str(self._leaf.value_str)
        if self._leaf.value_type == Type.DEC64:
            return lib.lyd_dec64_to_double(self._node)
        if self._leaf.value_type == Type.LEAFREF:
            referenced = DNode.new(self.context, self._leaf.value.leafref)
            return referenced.value()
        if self._leaf.value_type == Type.BOOL:
            return bool(self._leaf.value.bln)


#------------------------------------------------------------------------------
@DNode.register(SNode.LEAFLIST)
class DLeafList(DLeaf):
    pass


#------------------------------------------------------------------------------
def dnode_to_dict(dnode, strip_prefixes=True):
    """
    Convert a DNode object to a python dictionary.

    :arg DNode dnode:
        The data node to convert.
    :arg bool strip_prefixes:
        If True (the default), module prefixes are stripped from dictionary
        keys. If False, dictionary keys are in the form ``<module>:<name>``.
    """
    def _to_dict(node, parent_dic):
        if strip_prefixes:
            name = node.name()
        else:
            name = '%s:%s' % (node.module().name(), node.name())
        if isinstance(node, DList):
            list_element = {}
            for child in node:
                _to_dict(child, list_element)
            parent_dic.setdefault(name, []).append(list_element)
        elif isinstance(node, (DContainer, DRpc)):
            container = {}
            for child in node:
                _to_dict(child, container)
            parent_dic[name] = container
        elif isinstance(node, DLeafList):
            parent_dic.setdefault(name, []).append(node.value())
        elif isinstance(node, DLeaf):
            parent_dic[name] = node.value()

    dic = {}
    _to_dict(dnode, dic)
    return dic


#------------------------------------------------------------------------------
def dict_to_dnode(dic, schema, parent=None, rpc_input=False, rpc_output=False):
    """
    Convert a python dictionary to a DNode object given a YANG schema object.
    The returned value is always a top-level data node (i.e.: without parent).

    :arg dict dic:
        The python dictionary to convert.
    :arg SNode or Module schema:
        The libyang schema object associated with the dictionary. It must be
        at the same "level" than the dictionary (i.e.: direct children names of
        the schema object must be keys in the dictionary).
    :arg DNode parent:
        Optional parent to update. If not specified a new top-level DNode will
        be created.
    :arg bool rpc_input:
        If True, expect schema to be a SRpc object and dic will be parsed
        by looking in the rpc input nodes.
    :arg bool rpc_output:
        If True, expect schema to be a SRpc object and dic will be parsed
        by looking in the rpc output nodes.
    """
    if not dic:
        return parent

    if not isinstance(dic, dict):
        raise TypeError('dic argument must be a python dict')

    # XXX: ugly, required for python2. Cannot use nonlocal keyword
    _parent = [parent]

    def _to_dnode(_dic, _schema, key=()):
        if isinstance(_schema, SRpc):
            if rpc_input:
                _schema = _schema.input()
            elif rpc_output:
                _schema = _schema.output()
            else:
                raise ValueError('rpc_input or rpc_output must be specified')
        if not _schema:
            return
        for s in _schema:
            name = s.name()
            if name not in _dic:
                name = s.fullname()
                if name not in _dic:
                    continue
            d = _dic[name]
            if isinstance(s, SContainer):
                if not isinstance(d, dict):
                    raise TypeError('%s: python value is not a dict: %r'
                                    % (s.schema_path(), d))
                if s.presence():
                    dnode = s.context.create_data_path(
                        s.data_path() % key, parent=_parent[0],
                        rpc_output=rpc_output)
                    if _parent[0] is None:
                        _parent[0] = dnode
                _to_dnode(d, s, key)
            elif isinstance(s, SList):
                if not isinstance(d, (list, tuple)):
                    raise TypeError('%s: python value is not a list/tuple: %r'
                                    % (s.schema_path(), d))
                for element in d:
                    if not isinstance(element, dict):
                        raise TypeError('%s: list element is not a dict: %r'
                                        % (s.schema_path(), element))
                    try:
                        next_key = []
                        for k in s.keys():
                            try:
                                next_key.append(element[k.name()])
                            except KeyError as _e:
                                try:
                                    next_key.append(element[k.fullname()])
                                except KeyError:
                                    raise _e
                    except KeyError as e:
                        raise KeyError(
                            "%s: key '%s' not present in list element: %r"
                            % (s.schema_path(), e, element))
                    _to_dnode(element, s, key + tuple(next_key))
            elif isinstance(s, SLeafList):
                if not isinstance(d, (list, tuple)):
                    raise TypeError('%s: python value is not a list/tuple: %r'
                                    % (s.schema_path(), d))
                for element in d:
                    dnode = s.context.create_data_path(
                        s.data_path() % key, parent=_parent[0],
                        value=element, rpc_output=rpc_output)
                    if _parent[0] is None:
                        _parent[0] = dnode
            elif isinstance(s, SLeaf):
                dnode = s.context.create_data_path(
                    s.data_path() % key, parent=_parent[0], value=d,
                    rpc_output=rpc_output)
                if _parent[0] is None:
                    _parent[0] = dnode

    _to_dnode(dic, schema)

    # XXX: ugly, required for python2 support
    parent = _parent[0]

    if parent is not None:
        # go back to the root of the created tree
        while parent.parent() is not None:
            parent = parent.parent()

    return parent
