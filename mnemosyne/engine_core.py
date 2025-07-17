# file: mnemosyne/engine_core.py (最终修复与完善版)

import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Iterator
import threading
import json
import struct

from .storage.native_store import NativeStore, NODE_RECORD_FORMAT, EDGE_RECORD_FORMAT
from .storage.sqlite_store import SQLiteStore, RecordNotFoundError
from .storage.wal import WriteAheadLog, LogOperation
from .datatypes import Node, Edge, NodeID, EdgeID

class MnemosyneEngine:
    """
    The core engine that provides the Tier 1, low-level graph manipulation API.
    """
    def __init__(self, data_path: str = "./data"):
        self.data_dir = Path(data_path)
        self.wal_path = self.data_dir / "mnemosyne.wal"
        self.db_path = self.data_dir / "indexes_and_properties.db"

        self.wal: Optional[WriteAheadLog] = None
        self.native_store: Optional[NativeStore] = None
        self.sqlite_store: Optional[SQLiteStore] = None
        self._write_lock = threading.Lock()
        
        self._initialize_stores()
        print("MnemosyneEngine Core is online and ready.")

    def _initialize_stores(self):
        self.wal = WriteAheadLog(self.wal_path)
        self.native_store = NativeStore(self.data_dir)
        self.sqlite_store = SQLiteStore(self.db_path)

    @staticmethod
    def perform_recovery(data_path: str):
        """
        【最终修复】一个独立的、用于在引擎启动前执行恢复的静态方法。
        """
        data_dir = Path(data_path)
        wal_path = data_dir / "mnemosyne.wal"
        db_path = data_dir / "indexes_and_properties.db"

        if not wal_path.exists(): return

        # 【修复】我们创建所有需要的临时存储实例
        temp_native_store = NativeStore(data_dir)
        temp_sqlite_store = SQLiteStore(db_path)
        
        # 【修复】把所有需要的参数都传进去！
        WriteAheadLog.recover(wal_path, temp_native_store, temp_sqlite_store)
        
        # 【修复】关闭所有临时的句柄！
        temp_native_store.close()
        temp_sqlite_store.close()

    def close(self):
        # 【调试】在关闭前，检查一下文件大小
        if self.native_store and self.native_store.nodes_file and not self.native_store.nodes_file.closed:
            self.native_store.nodes_file.seek(0, os.SEEK_END)
            size = self.native_store.nodes_file.tell()
            print(f"DEBUG: Closing engine. nodes.dat size is {size} bytes.")

        if self.wal: self.wal.close()
        if self.native_store: self.native_store.close()
        if self.sqlite_store: self.sqlite_store.close()
        print("MnemosyneEngine Core has been shut down.")

    def _create_node(self, properties: Dict[str, Any]) -> NodeID:
        with self._write_lock:
            txn_id = self.wal.begin_transaction()
            
            next_node_id = self.native_store._get_next_id(self.native_store.nodes_file)
            prop_id = next_node_id
            creation_time = int(time.time())
            
            # --- 记录日志 ---
            new_node_bytes = struct.pack(NODE_RECORD_FORMAT, 0, 0, 0, prop_id, creation_time)
            self.wal.log_append(txn_id, LogOperation.NODE_APPEND, new_node_bytes)
            
            sqlite_op_data = json.dumps({"op": "store_properties", "args": [prop_id, properties]}).encode('utf-8')
            self.wal.log_append(txn_id, LogOperation.SQLITE_WRITE, sqlite_op_data)
            
            if 'name' in properties:
                name_index_op_data = json.dumps({"op": "add_to_name_index", "args": [properties['name'], next_node_id]}).encode('utf-8')
                self.wal.log_append(txn_id, LogOperation.SQLITE_WRITE, name_index_op_data)

            # --- 提交 ---
            self.wal.commit_transaction(txn_id)

            # --- 应用变更 ---
            self.sqlite_store.store_properties(prop_id, properties)
            node_id = self.native_store.append_node(0, 0, prop_id, creation_time)
            if 'name' in properties:
                self.sqlite_store.add_to_name_index(properties['name'], node_id)
                
            return node_id

    def _create_edge(self, source_id: NodeID, target_id: NodeID, relation_type: str, properties: Optional[Dict[str, Any]] = None) -> EdgeID:
        with self._write_lock:
            txn_id = self.wal.begin_transaction()
            
            prop_id = 0
            if properties:
                prop_id = self.native_store._get_next_id(self.native_store.edges_file)
            
            source_record = self.native_store.get_node_record(source_id)
            target_record = self.native_store.get_node_record(target_id)
            current_head_outgoing_id = source_record[2]
            current_head_incoming_id = target_record[3]
            
            relation_type_id = 0
            creation_time = int(time.time())
            next_edge_id = self.native_store._get_next_id(self.native_store.edges_file)

            # --- 记录日志 ---
            new_edge_bytes = struct.pack(EDGE_RECORD_FORMAT, relation_type_id, source_id, target_id, current_head_outgoing_id, current_head_incoming_id, prop_id, creation_time)
            self.wal.log_append(txn_id, LogOperation.EDGE_APPEND, new_edge_bytes)
            
            temp_source_record = list(source_record)
            temp_source_record[2] = next_edge_id
            updated_source_bytes = struct.pack(NODE_RECORD_FORMAT, *temp_source_record)
            self.wal.log_update(txn_id, LogOperation.NODE_UPDATE, source_id, updated_source_bytes)

            temp_target_record = list(target_record)
            temp_target_record[3] = next_edge_id
            updated_target_bytes = struct.pack(NODE_RECORD_FORMAT, *temp_target_record)
            self.wal.log_update(txn_id, LogOperation.NODE_UPDATE, target_id, updated_target_bytes)
            
            if properties:
                sqlite_op_data = json.dumps({"op": "store_properties", "args": [prop_id, properties]}).encode('utf-8')
                self.wal.log_append(txn_id, LogOperation.SQLITE_WRITE, sqlite_op_data)
            
            # --- 提交 ---
            self.wal.commit_transaction(txn_id)
            
            # --- 应用变更 ---
            if properties:
                self.sqlite_store.store_properties(prop_id, properties)

            new_edge_id_actual = self.native_store.append_edge(source_id, target_id, current_head_outgoing_id, current_head_incoming_id, prop_id, creation_time, relation_type_id)
            self.native_store.update_node_head_pointers(node_id=source_id, first_outgoing=new_edge_id_actual)
            self.native_store.update_node_head_pointers(node_id=target_id, first_incoming=new_edge_id_actual)
            
            return new_edge_id_actual

    def _get_node(self, node_id: NodeID) -> Optional[Node]:
        # get操作是只读的，保持不变
        try:
            record = self.native_store.get_node_record(node_id)
            # 修正解包和空指针判断
            flags, out_ptr, in_ptr, properties_ptr, timestamp = record
            properties = {}
            if properties_ptr >= 0: # 假设0是有效ID，-1或类似值为无效
                 try:
                     properties = self.sqlite_store.get_properties(properties_ptr)
                 except RecordNotFoundError:
                     # 即使指针有效，也可能因为某种原因找不到属性，这时返回空属性
                     pass
            return Node(id=node_id, properties=properties)
        except IndexError:
            return None

    def _get_edge(self, edge_id: EdgeID) -> Optional[Edge]:
        try:
            record = self.native_store.get_edge_record(edge_id)
            flags, _, source_id, target_id, _, _, properties_ptr, _ = record
            properties = self.sqlite_store.get_properties(properties_ptr) if properties_ptr > 0 else {}
            # TODO: Map flags back to relation_type string
            relation_type = "placeholder"
            return Edge(id=edge_id, source_id=source_id, target_id=target_id, relation_type=relation_type, properties=properties)
        except IndexError:
            return None

    def _traverse(self, start_node_id: NodeID, direction: str = 'outgoing') -> Iterator[Edge]:
        node_record = self.native_store.get_node_record(start_node_id)
        
        if direction == 'outgoing':
            current_edge_id = node_record[2] # first_outgoing_edge_id
            next_edge_idx = 4 # index of next_outgoing_id in edge record
        else: # 'incoming'
            current_edge_id = node_record[3] # first_incoming_edge_id
            next_edge_idx = 5 # index of next_incoming_id in edge record

        while current_edge_id != 0: # 0 is our NULL_POINTER
            edge = self._get_edge(current_edge_id)
            if not edge: break
            yield edge
            
            edge_record = self.native_store.get_edge_record(current_edge_id)
            current_edge_id = edge_record[next_edge_idx]