# file: mnemosyne/storage/sqlite_store.py

"""
Mnemosyne - SQLite Storage Backend

This module is responsible for handling all interactions with the SQLite
database. It acts as a persistent, indexed key-value store for node/edge
properties and provides the secondary indexing capabilities needed for
property-based lookups.

All complex filtering logic (our "Tier 2 API" which will be optimized later)
will eventually be pushed down into this layer as efficient SQL queries.
"""
import sqlite3
import threading
import json  # 我们先用JSON作为序列化格式，因为它直观易读，便于调试
from pathlib import Path
from typing import Dict, Any, List

# 导入我们刚刚定义的核心“原子”和类型别名
from ..datatypes import NodeID

# 定义一个简单的异常，当查找不到东西时可以抛出
class RecordNotFoundError(Exception):
    pass

class SQLiteStore:
    """
    Manages the storage of properties and indexes in a SQLite database.
    This class is designed to be thread-safe.
    
    管理SQLite数据库中属性和索引的存储。
    这个类被设计为线程安全的。
    """
    def __init__(self, db_path: Path):
        # 确保数据库文件所在的目录存在
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        
        # 使用线程局部变量来存储数据库连接，确保每个线程使用独立的连接
        # 这是在多线程环境下使用SQLite的标准做法
        self.thread_local = threading.local()
        
        # 在启动时，立刻初始化数据库和表结构
        self._initialize_database()
        print(f"SQLiteStore initialized at: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接。如果不存在，则创建一个新的。"""
        if not hasattr(self.thread_local, 'connection'):
            # check_same_thread=False 配合我们自己的线程锁，可以更灵活地管理并发
            self.thread_local.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        return self.thread_local.connection

    def _initialize_database(self):
        """创建数据库表和索引，如果它们还不存在的话。"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # --- 属性存储表 ---
        # 这是一个通用的“大仓库”，节点和边的属性都存在这里。
        # Key是我们在原生层分配的properties_ptr，Value是序列化后的属性字典。
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS properties (
                id INTEGER PRIMARY KEY,
                data TEXT NOT NULL
            )
        ''')

        # --- 名称索引表 (`name_to_id`) ---
        # 这是我们最重要的二级索引！
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS name_index (
                name TEXT NOT NULL,
                node_id INTEGER NOT NULL
            )
        ''')
        # 为name列创建索引，极大加速 `WHERE name = ?` 的查询
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_name ON name_index (name)')

        # --- 复合索引表 (未来扩展用) ---
        # 我们先把这个表建好，为我们未来的“API下沉”优化做好准备
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS composite_index (
                key TEXT PRIMARY KEY,
                node_id INTEGER NOT NULL
            )
        ''')

        conn.commit()
    
    # --- 下面是这个仓库的“操作API” ---
    
    def store_properties(self, prop_id: int, properties: Dict[str, Any]) -> None:
        """将一个属性字典存入数据库。"""
        conn = self._get_connection()
        serialized_data = json.dumps(properties)
        
        # 【最终修复！】从 INSERT 改为 INSERT OR REPLACE！
        # 这会让操作变成幂等的。如果ID已存在，就用新数据覆盖它；如果不存在，就插入。
        # 这正是我们在恢复时所需要的行为！
        conn.execute(
            'INSERT OR REPLACE INTO properties (id, data) VALUES (?, ?)',
            (prop_id, serialized_data)
        )
        conn.commit()

    def add_to_name_index(self, name: str, node_id: NodeID) -> None:
        """在名称索引中添加一条记录。"""
        conn = self._get_connection()
        # 这里我们也用同样的方式，防止重复添加
        # 虽然在当前逻辑下不会发生，但这是好习惯
        conn.execute(
            'INSERT OR IGNORE INTO name_index (name, node_id) VALUES (?, ?)',
            (name, node_id)
        )
        conn.commit()

    def get_properties(self, prop_id: int) -> Dict[str, Any]:
        """根据ID取出属性字典。"""
        cursor = self._get_connection().cursor()
        cursor.execute('SELECT data FROM properties WHERE id = ?', (prop_id,))
        row = cursor.fetchone()
        if row is None:
            raise RecordNotFoundError(f"Properties with id {prop_id} not found.")
        return json.loads(row[0])

    def find_by_name(self, name: str) -> List[NodeID]:
        """根据名称查找所有匹配的节点ID。"""
        cursor = self._get_connection().cursor()
        cursor.execute('SELECT node_id FROM name_index WHERE name = ?', (name,))
        # fetchall()返回一个元组列表，比如[(123,), (456,)]，我们需要把它解包
        return [row[0] for row in cursor.fetchall()]

    def close(self):
        """关闭当前线程的数据库连接。"""
        if hasattr(self.thread_local, 'connection'):
            self.thread_local.connection.close()
            del self.thread_local.connection