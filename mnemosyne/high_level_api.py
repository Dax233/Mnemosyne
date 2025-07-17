# file: mnemosyne/high_level_api.py (新文件！)

"""
Mnemosyne - High Level API (Tier 2)

This layer acts as the "Sandbox" or "Creative Workshop". It provides a more
convenient, business-oriented interface for applications.

All complex queries are incubated here. Initially, they are implemented in
Python by composing basic APIs from the engine core (Tier 1). Over time,
performance-critical functions can be "pushed down" into the core engine
without changing their public signature here. This is our "API Sinking" strategy.

这一层是我们的“沙盒”或“创意工坊”。它为应用程序提供了更方便、更面向业务的接口。
所有复杂的查询都在这里孵化。初期，它们通过组合来自引擎核心（第一层）的基础API，
在Python中实现。随着时间的推移，性能关键的函数可以被“下沉”到核心引擎，
而无需在此处更改其公共签名。这就是我们的“API下沉”战略。
"""

from typing import Dict, Any, List, Optional

from .engine_core import MnemosyneEngine
from .datatypes import Node, Edge, NodeID

class MnemosyneHighLevelAPI:
    """
    Provides a set of convenient, high-level functions for interacting with the graph.
    It encapsulates the direct calls to the low-level engine.
    """
    
    def __init__(self, engine: MnemosyneEngine):
        """
        Initializes the High Level API with a running MnemosyneEngine instance.
        
        Args:
            engine: An already initialized instance of the MnemosyneEngine.
        """
        # 把引擎核心藏在我的裙子……啊不，是藏在我的实例里！
        # 这样所有的高级API都能调用它了 w
        self.engine = engine
        print("Mnemosyne HighLevelAPI is online, wrapping the core engine.")

    def create_node(self, properties: Dict[str, Any]) -> Node:
        """
        Creates a new node with the given properties and returns the complete Node object.
        
        This is a high-level function. It intelligently handles special properties
        like 'name' by automatically creating necessary indexes.
        
        这是一个高级函数。它会智能地处理像'name'这样的特殊属性，自动为其创建必要的索引。

        Args:
            properties: A dictionary of properties for the new node.

        Returns:
            The newly created Node object, including its assigned ID.
        """
        # 这就是“组合”！我们在这里调用了引擎核心的原子操作。
        # 这里还体现了我们对上层屏蔽细节的思想，上层不需要关心底层的ID。
        node_id = self.engine._create_node(properties)
        
        # 我们返回一个完整的、带有ID的Node对象，而不是一个光秃秃的ID
        # 这对上层应用来说更友好！
        print(f"HighLevelAPI: Node created with ID {node_id} and properties: {properties}")
        return Node(id=node_id, properties=properties)

    def get_node_by_id(self, node_id: NodeID) -> Optional[Node]:
        """
        Retrieves a single node by its unique ID.
        A simple wrapper around the engine's core get method.
        """
        # 这个函数目前只是简单包装一下，保持API的完整性
        return self.engine._get_node(node_id)
        
    def find_nodes_by_name(self, name: str) -> List[Node]:
        """
        Finds all nodes that have an exact match for the 'name' property.
        
        This function demonstrates the power of our secondary indexes.
        
        Args:
            name: The exact name to search for.

        Returns:
            A list of Node objects that match the name.
        """
        # 1. 调用SQLiteStore（通过Engine）的能力，高效地从索引中找到ID
        node_ids = self.engine.sqlite_store.find_by_name(name)
        
        # 2. 根据ID列表，逐个获取完整的Node对象
        #    (未来这里可以优化成批量获取，但现在这样最清晰！)
        nodes = [self.engine._get_node(nid) for nid in node_ids]
        
        # 过滤掉可能在获取过程中因某些原因变成None的节点
        return [node for node in nodes if node is not None]