# file: mnemosyne/datatypes.py

"""
Mnemosyne - Core Data Types

This file defines the fundamental data structures that represent the graph's
entities. By defining them as dataclasses, we gain type safety, auto-generated
methods, and a clear, self-documenting structure for our APIs.
"""

# 我们从Python的typing模块导入我们需要的类型提示工具
# 让我们的代码像“法律条文”一样严谨！
from dataclasses import dataclass, field
from typing import Dict, Any

# @dataclass 这个“装饰器”是Python送给我们的礼物
# 它会自动为我们生成__init__, __repr__等魔法方法，让我们的类变得简洁又强大
@dataclass(frozen=True)
class Node:
    """
    Represents a single node (or vertex) in the graph.
    
    This object is designed to be immutable (`frozen=True`) once created.
    Any changes to a node should result in a new state, not a modification
    of the existing one, aligning with our Append-Only philosophy.
    
    这代表一个图中的节点（或顶点）。
    这个对象被设计为一旦创建就不可变。任何对节点的修改都应产生新的状态，
    而不是修改现有状态，这与我们的只追加(Append-Only)哲学保持一致。
    """
    id: int
    # 我们使用 `field` 来自定义这个字典的默认值
    # 确保每个Node实例都有自己独立的空字典，而不是共享同一个
    properties: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class Edge:
    """
    Represents a single directed edge (or relationship) in the graph.
    It connects two nodes and has a specific type.
    
    Like Nodes, Edges are also immutable.
    
    这代表一个图中的有向边（或关系）。
    它连接两个节点，并有一个特定的类型。
    和节点一样，边也是不可变的。
    """
    id: int
    source_id: int
    target_id: int
    relation_type: str
    properties: Dict[str, Any] = field(default_factory=dict)

# --- 这里是枫的小小私心w ---
# 我觉得，定义一个更具体的类型别名，能让代码的可读性更高！
# 比如，我们经常需要处理节点ID，用NodeID比用int更清晰地表达了意图。
NodeID = int
EdgeID = int