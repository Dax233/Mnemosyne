# file: mnemosyne/storage/native_store.py

"""
Mnemosyne - Native Storage Engine

This is the heart of our graph's performance. This module directly manages
the binary flat files (`nodes.dat`, `edges.dat`) that store the core graph
topology. By using fixed-size records and direct file I/O, we achieve O(1)
access for nodes/edges by their ID and enable lightning-fast graph traversal
through physical pointer chasing (Index-Free Adjacency).

这里是我们图性能的心脏。该模块直接管理存储核心图拓扑的二进制扁平文件。
通过使用固定大小的记录和直接的文件I/O，我们实现了通过ID对节点/边进行O(1)访问，
并通过物理指针追逐（无索引邻接）实现闪电般的图遍历。
"""
import os
import struct
from pathlib import Path
from typing import Tuple, Optional

# 导入我们的ID类型别名
from ..datatypes import NodeID, EdgeID

# --- 定义我们的“物理法则”：记录的结构和大小 ---

# 我们在设计文档里定义的节点记录结构 (32字节)
# '<' 代表小端字节序 (little-endian)，这是现代CPU的标准
# B: unsigned char (1 byte), 3x: 3 padding bytes, Q: unsigned long long (8 bytes), I: unsigned int (4 bytes)
NODE_RECORD_FORMAT = '<B 3x Q Q Q I'
NODE_RECORD_SIZE = struct.calcsize(NODE_RECORD_FORMAT)  # 应该是 32

# 边记录结构 (48字节)
EDGE_RECORD_FORMAT = '<B 3x Q Q Q Q Q I'
EDGE_RECORD_SIZE = struct.calcsize(EDGE_RECORD_FORMAT)  # 应该是 48


class NativeStore:
    """
    Manages the raw, fixed-size record files for nodes and edges.
    This class is NOT thread-safe by itself. Concurrency must be handled
    by the upper layer (MnemosyneEngine).
    
    管理节点和边的原始、固定大小的记录文件。
    这个类本身不是线程安全的。并发必须由上层(MnemosyneEngine)处理。
    """

    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)

        self.nodes_path = data_dir / 'nodes.dat'
        self.edges_path = data_dir / 'edges.dat'

        # 以二进制读写追加模式(ab+)打开文件。如果文件不存在，会自动创建。
        # 'a' for append, 'b' for binary, '+' for read/write access.
        # 我们把文件句柄缓存起来，避免重复打开
        self.nodes_file = self.nodes_path.open('ab+')
        self.edges_file = self.edges_path.open('ab+')
        
        print(f"NativeStore initialized. Node record size: {NODE_RECORD_SIZE}, Edge record size: {EDGE_RECORD_SIZE}")

    def _get_next_id(self, file) -> int:
        """通过文件大小计算下一个可用的ID。"""
        # 把文件指针移到末尾
        file.seek(0, os.SEEK_END)
        # 获取当前文件大小（字节数）
        size = file.tell()
        # 根据记录大小计算ID。比如nodes.dat是320字节，那么就有10条记录，下一个ID是10。
        record_size = NODE_RECORD_SIZE if file is self.nodes_file else EDGE_RECORD_SIZE
        return size // record_size

    # --- 核心操作：在硬盘上雕刻！ ---

    def append_node(self, first_outgoing_edge_id: EdgeID, first_incoming_edge_id: EdgeID, properties_ptr: int, creation_timestamp: int, flags: int = 0) -> NodeID:
        """
        在nodes.dat文件末尾追加一条新的节点记录。
        返回新节点的ID。
        """
        next_id = self._get_next_id(self.nodes_file)
        
        # `struct.pack` 是我们的“雕刻刀”！它把Python的数字变成精确的二进制字节串。
        record_bytes = struct.pack(
            NODE_RECORD_FORMAT,
            flags,
            first_outgoing_edge_id,
            first_incoming_edge_id,
            properties_ptr,
            creation_timestamp
        )
        
        self.nodes_file.write(record_bytes)
        self.nodes_file.flush() # 确保立刻写入硬盘，对于WAL很重要
        return next_id

    def get_node_record(self, node_id: NodeID) -> Tuple:
        """根据ID读取一条节点记录的原始数据。"""
        offset = node_id * NODE_RECORD_SIZE
        # `seek` 是我们的“定位仪”，直接把指针跳到硬盘的特定物理位置！
        self.nodes_file.seek(offset)
        record_bytes = self.nodes_file.read(NODE_RECORD_SIZE)

        if len(record_bytes) < NODE_RECORD_SIZE:
            raise IndexError(f"Node with id {node_id} does not exist.")

        # `struct.unpack` 是我们的“解读器”！它把二进制字节串翻译回Python的数字元组。
        return struct.unpack(NODE_RECORD_FORMAT, record_bytes)

    def append_edge(self, source_id: NodeID, target_id: NodeID, next_outgoing_id: EdgeID, next_incoming_id: EdgeID, properties_ptr: int, creation_timestamp: int, flags: int = 0) -> EdgeID:
        """在edges.dat文件末尾追加一条新的边记录。"""
        next_id = self._get_next_id(self.edges_file)
        
        record_bytes = struct.pack(
            EDGE_RECORD_FORMAT,
            flags,
            source_id,
            target_id,
            next_outgoing_id,
            next_incoming_id,
            properties_ptr,
            creation_timestamp
        )
        
        self.edges_file.write(record_bytes)
        self.edges_file.flush()
        return next_id
        
    def get_edge_record(self, edge_id: EdgeID) -> Tuple:
        """根据ID读取一条边记录的原始数据。"""
        offset = edge_id * EDGE_RECORD_SIZE
        self.edges_file.seek(offset)
        record_bytes = self.edges_file.read(EDGE_RECORD_SIZE)

        if len(record_bytes) < EDGE_RECORD_SIZE:
            raise IndexError(f"Edge with id {edge_id} does not exist.")
            
        return struct.unpack(EDGE_RECORD_FORMAT, record_bytes)

    def _update_record(self, file, record_id: int, record_bytes: bytes):
        """
        【危险】在指定位置覆写一条记录。
        这主要用于更新指针链表。必须在锁和WAL的保护下调用！
        """
        record_size = NODE_RECORD_SIZE if file is self.nodes_file else EDGE_RECORD_SIZE
        offset = record_id * record_size
        file.seek(offset)
        file.write(record_bytes)
        file.flush()

    # 我们还需要一个方法来更新特定字段，而不是整个记录
    def update_node_head_pointers(self, node_id: NodeID, first_outgoing: Optional[EdgeID] = None, first_incoming: Optional[EdgeID] = None):
        """更新一个节点记录里的头指针。"""
        # 1. 先读出整条记录
        record_tuple = self.get_node_record(node_id)
        # 把元组变成列表，方便修改
        record_list = list(record_tuple)

        # 2. 按需修改指针
        # 我们的格式是 '<B 3x Q Q Q I'
        # flags, _, out_ptr, in_ptr, prop_ptr, time
        #       0, 1, 2,      3,      4,        5
        if first_outgoing is not None:
            record_list[2] = first_outgoing
        if first_incoming is not None:
            record_list[3] = first_incoming
        
        # 3. 把修改后的列表重新打包成二进制
        updated_record_bytes = struct.pack(NODE_RECORD_FORMAT, *record_list)
        
        # 4. 在原位置覆写
        self._update_record(self.nodes_file, node_id, updated_record_bytes)

    def close(self):
        """关闭文件句柄。"""
        self.nodes_file.close()
        self.edges_file.close()