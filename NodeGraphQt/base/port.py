#!/usr/bin/python
from .commands import (PortConnectedCmd,
                       PortDisconnectedCmd,
                       PortVisibleCmd,
                       NodeInputConnectedCmd,
                       NodeInputDisconnectedCmd)
from .model import PortModel
from ..constants import IN_PORT, OUT_PORT
from ..errors import PortError


class Port(object):
    """
    The ``Port`` class is used for connecting one node to another.

    .. image:: ../_images/port.png
        :width: 50%

    See Also:
        For adding a ports into a node see:
        :meth:`BaseNode.add_input`, :meth:`BaseNode.add_output`

    Args:
        node (NodeGraphQt.NodeObject): parent node.
        port (PortItem): graphic item used for drawing.
    """

    def __init__(self, node, port):
        self.__view = port
        self.__model = PortModel(node)

    def __repr__(self):
        port = str(self.__class__.__name__)
        return f'<{port}("{self.name()}") object at {hex(id(self))}>'

    @property
    def view(self):
        """
        returns the :class:`QtWidgets.QGraphicsItem` used in the scene.

        Returns:
            NodeGraphQt.qgraphics.port.PortItem: port item.
        """
        return self.__view

    @property
    def model(self):
        """
        returns the port model.

        Returns:
            NodeGraphQt.base.model.PortModel: port model.
        """
        return self.__model

    def type_(self):
        """
        Returns the port type.

        Port Types:
            - :attr:`NodeGraphQt.constants.IN_PORT` for input port
            - :attr:`NodeGraphQt.constants.OUT_PORT` for output port

        Returns:
            str: port connection type.
        """
        return self.model.type_

    def multi_connection(self):
        """
        Returns if the ports is a single connection or not.

        Returns:
            bool: false if port is a single connection port
        """
        return self.model.multi_connection

    def node(self):
        """
        Return the parent node.

        Returns:
            NodeGraphQt.BaseNode: parent node object.
        """
        return self.model.node

    def name(self):
        """
        Returns the port name.

        Returns:
            str: port name.
        """
        return self.model.name

    def visible(self):
        """
        Port visible in the node graph.

        Returns:
            bool: true if visible.
        """
        return self.model.visible

    def set_visible(self, visible=True):
        """
        Sets weather the port should be visible or not.

        Args:
            visible (bool): true if visible.
        """
        self.model.visible = visible
        label = 'show' if visible else 'hide'
        undo_stack = self.node().graph.undo_stack()
        undo_stack.beginMacro(f'{label} port {self.name()}')

        for port in self.connected_ports():
            undo_stack.push(PortDisconnectedCmd(self, port))

        undo_stack.push(PortVisibleCmd(self))
        undo_stack.endMacro()

    def locked(self):
        """
        Returns the locked state.

        If ports are locked then new pipe connections can't be connected
        and current connected pipes can't be disconnected.

        Returns:
            bool: true if locked.
        """
        return self.model.locked

    def lock(self):
        """
        Lock the port so new pipe connections can't be connected and
        current connected pipes can't be disconnected.

        This is the same as calling :meth:`Port.set_locked` with the arg
        set to ``True``
        """
        self.set_locked(True)

    def unlock(self):
        """
        Unlock the port so new pipe connections can be connected and
        existing connected pipes can be disconnected.

        This is the same as calling :meth:`Port.set_locked` with the arg
        set to ``False``
        """
        self.set_locked(False)

    def set_locked(self, locked=False):
        """
        Sets the port locked state. When locked pipe connections can't be
        connected or disconnected from this port.

        Args:
            locked (Bool): true if locked.
        """
        self.model.locked = locked
        self.__view.locked = locked

    def connected_ports(self):
        """
        Returns all connected ports.

        Returns:
            list[NodeGraphQt.Port]: list of connected ports.
        """
        ports = []
        graph = self.node().graph
        for node_id, port_names in self.model.connected_ports.items():
            for port_name in port_names:
                node = graph.get_node_by_id(node_id)
                if self.type_() == IN_PORT:
                    ports.append(node.outputs()[port_name])
                elif self.type_() == OUT_PORT:
                    ports.append(node.inputs()[port_name])
        return ports

    def connect_to(self, port=None):
        """
        Create connection to the specified port and emits the
        :attr:`NodeGraph.port_connected` signal from the parent node graph.

        Args:
            port (NodeGraphQt.Port): port object.
        """
        if not port:
            return

        if self in port.connected_ports():
            return

        if self.locked() or port.locked():
            name = [p.name() for p in [self, port] if p.locked()][0]
            raise PortError(f"""Can't connect port because "{name}" is locked.""")

        graph = self.node().graph
        viewer = graph.viewer()

        undo_stack = graph.undo_stack()
        undo_stack.beginMacro('connect port')

        pre_conn_port = None
        src_conn_ports = self.connected_ports()
        if not self.multi_connection() and src_conn_ports:
            pre_conn_port = src_conn_ports[0]

        if not port:
            if pre_conn_port:
                undo_stack.push(PortDisconnectedCmd(self, port))
                undo_stack.push(NodeInputDisconnectedCmd(self, port))
            return

        if (
            graph.acyclic()
            and viewer.acyclic_check(self.view, port.view)
            and pre_conn_port
        ):
            undo_stack.push(PortDisconnectedCmd(self, pre_conn_port))
            undo_stack.push(NodeInputDisconnectedCmd(self, pre_conn_port))
            return

        trg_conn_ports = port.connected_ports()
        if not port.multi_connection() and trg_conn_ports:
            dettached_port = trg_conn_ports[0]
            undo_stack.push(PortDisconnectedCmd(port, dettached_port))
            undo_stack.push(NodeInputDisconnectedCmd(port, dettached_port))
        if pre_conn_port:
            undo_stack.push(PortDisconnectedCmd(self, pre_conn_port))
            undo_stack.push(NodeInputDisconnectedCmd(self, pre_conn_port))

        undo_stack.push(PortConnectedCmd(self, port))
        undo_stack.push(NodeInputConnectedCmd(self, port))

        undo_stack.endMacro()

        # emit "port_connected" signal from the parent graph.
        ports = {p.type_(): p for p in [self, port]}
        graph.port_connected.emit(ports[IN_PORT], ports[OUT_PORT])

    def disconnect_from(self, port=None):
        """
        Disconnect from the specified port and emits the
        :attr:`NodeGraph.port_disconnected` signal from the parent node graph.

        Args:
            port (NodeGraphQt.Port): port object.
        """
        if not port:
            return

        if self.locked() or port.locked():
            name = [p.name() for p in [self, port] if p.locked()][0]
            raise PortError(f"""Can't disconnect port because "{name}" is locked.""")

        graph = self.node().graph
        graph.undo_stack().beginMacro('disconnect port')
        graph.undo_stack().push(PortDisconnectedCmd(self, port))
        graph.undo_stack().push(NodeInputDisconnectedCmd(self, port))
        graph.undo_stack().endMacro()

        # emit "port_disconnected" signal from the parent graph.
        ports = {p.type_(): p for p in [self, port]}
        graph.port_disconnected.emit(ports[IN_PORT], ports[OUT_PORT])

    @property
    def color(self):
        return self.__view.color

    @color.setter
    def color(self, color=(0, 0, 0, 255)):
        self.__view.color = color

    @property
    def data_type(self):
        return self.__model.data_type

    @data_type.setter
    def data_type(self, data_type):
        self.__model.data_type = data_type

    @property
    def border_color(self):
        return self.__view.border_color

    @border_color.setter
    def border_color(self, color=(0, 0, 0, 255)):
        self.__view.border_color = color
