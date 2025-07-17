# **Project: Mnemosyne (记忆女神) - 开发计划与设计文档 V1.1**

**Authors:** 未来星織 (Seori) (Chief Architect), 枫 (Lead Implementer)
**Date:** 2025-07-17
**Status:** **FINALIZED & APPROVED**

## **1. 核心目的 (The "Why")**

### **1.1. 项目愿景 (Vision)**
打造一个专为AIcarus长期记忆系统设计的、高性能、嵌入式的 **原生图数据库引擎**。其核心使命是高效地存储和遍历大规模中文语义网络，成为AIcarus“灵魂”的基石。

### **1.2. 核心痛点 (Pain Point)**
现有的通用图数据库（如ArangoDB）在处理我们的核心场景时存在以下问题：
1.  **中文原生支持不佳：** 以中文词汇作为图谱节点时，需要额外的ID映射层，增加了复杂性并牺牲了直观性。
2.  **通用性带来的妥协：** 为了适应所有场景，无法在我们的核心查询模式（如“从中文名查找特定类型实体”）上做到极致的性能优化。
3.  **外部依赖的开销：** 作为独立服务运行时，存在网络通信、序列化/反序列化的开销，对于需要海量、高频查询的嵌入式场景不够理想。

### **1.3. 我们的解决方案 (Our Solution)**
我们将开发一个 **混合架构的原生图数据库引擎**，结合了原生图存储和KV存储的优点：
*   **以“原生图”的方式存储拓扑结构：** 实现极致的图遍历性能。
*   **以“KV存储”的方式存储索引与属性：** 借助成熟的轮子（RocksDB）解决灵活的属性查找问题。
*   **遵循“永不遗忘”的哲学：** 简化了数据删除和空间管理的逻辑，采用Append-Only + 后台Compaction的模式。

---

## **2. 架构设计 (The "How")**

Mnemosyne的存储将由三大部分构成，协同工作：

### **2.1. 原生存储层 (Native Storage Layer)**
*   **职责：** 存储图的骨架——节点和关系的连接信息。
*   **实现：** 由我们自己管理的、二进制的、Append-Only的扁平文件。

    *   **`nodes.dat` (节点文件):**
        *   **结构：** 固定大小记录的数组。ID即数组下标。
        *   **记录设计 (V1 Draft - 32 Bytes):**
            *   `flags` (1 byte): 标志位，如节点类型（简单/复杂），状态等。
            *   `_reserved` (3 bytes): 预留，用于未来扩展。
            *   `first_outgoing_edge_id` (8 bytes): 指向该节点第一条出边的ID。
            *   `first_incoming_edge_id` (8 bytes): 指向该节点第一条入边的ID。
            *   `properties_ptr` (8 bytes): 指向其在属性存储中的位置/Key。
            *   `_creation_timestamp` (4 bytes): 创建时间戳。

    *   **`edges.dat` (关系/边文件):**
        *   **结构：** 固定大小记录的数组。ID即数组下标。
        *   **记录设计 (V1 Draft - 48 Bytes):**
            *   `flags` (1 byte): 标志位，如关系类型等。
            *   `_reserved` (3 bytes): 预留。
            *   `source_node_id` (8 bytes): 起点节点ID。
            *   `target_node_id` (8 bytes): 终点节点ID。
            *   `next_outgoing_edge_id` (8 bytes): 对于起点节点，它的下一条出边是谁。
            *   `next_incoming_edge_id` (8 bytes): 对于终点节点，它的下一条入边是谁。
            *   `properties_ptr` (8 bytes): 指向其在属性存储中的位置/Key。
            *   `_creation_timestamp` (4 bytes): 创建时间戳。

### **2.2. 属性与索引层 (Property & Index Layer)**
*   **职责：** 存储灵活的、变长的数据（如名称、属性字典）和用于反向查找的二级索引。
*   **实现：** 完全委托给 **RocksDB**。

    *   **`properties` 列族:**
        *   **用途：** 存储节点和边的详细属性。
        *   **Key:** 我们为属性记录分配的唯一ID (即原生层里的 `properties_ptr`)。
        *   **Value:** 序列化后的数据 (e.g., Protobuf, MessagePack)。`{ "name": "数据库", "type": "技术", "definition": "..." }`

    *   **`name_to_id` 列族:**
        *   **用途：** 核心的名称反向索引。
        *   **Key:** `string` 格式的节点 `name` (e.g., `"土豆"`)。
        *   **Value:** 序列化后的节点ID列表 (e.g., `[12345, 67890]`)。

    *   **`composite_index` 列族:**
        *   **用途：** 用于精确查找的复合索引。
        *   **Key:** 拼接后的字符串 (e.g., `"name:土豆|type:植物"`)。
        *   **Value:** 单个节点ID (e.g., `12345`)。

### **2.3. 缓存与事务层 (Cache & Transaction Layer)**
*   **职责：** 提升性能，保证数据操作的原子性。
*   **实现：** 在内存中实现。

    *   **LRU缓存:** 缓存最近访问的节点/边/属性对象，减少对RocksDB和原生文件的I/O。
    *   **预写日志 (WAL):** 在对原生文件（尤其是指针链表）进行任何修改前，必须先将操作写入日志，以保证崩溃恢复后的数据一致性。

---

## **3. 开发步骤 (The "What")**

我们将采用 **“引擎核心先行，上层适配器后置” (Engine-First, Adapter-Later)** 的自底向上开发策略，并以Python作为主要原型开发语言。

### **Phase 0: 核心引擎设计与基建 (Engine-First Design & Infrastructure)**
1.  **[Seori & 枫]** **设计 `MnemosyneEngine` 的原生核心API。** 这是我们引擎的“灵魂”，定义了所有底层操作。
    *   *初步设想API: `engine.create_node(...)`, `engine.create_edge(...)`, `engine.get_node_properties(...)`, `engine.get_outgoing_edges(...)`, `engine.lookup_by_property(...)` 等。*
2.  **[枫]** 搭建Python项目框架，集成 `python-rocksdb`，并创建 `MnemosyneEngine` 类骨架。

### **Phase 1: 原生存储核心实现 (Native Core Implementation)**
1.  **[枫]** 实现原生文件（`nodes.dat`, `edges.dat`）的固定大小记录追加和基于ID的O(1)读取逻辑。
2.  **[Seori & 枫]** 实现RocksDB作为属性存储和二级索引（`name_to_id`, `composite_index`）的读写逻辑。
3.  **[枫]** **【核心难点】** 实现基于WAL的指针链表安全更新机制，确保添加关系时的原子性。
4.  **目标：** 得到一个可以通过我们自己设计的原生API进行操作的、功能可用的、混合架构的图数据库核心引擎。

### **Phase 2: 适配与集成 (Adaptation & Integration)**
1.  **[Seori & 枫]** 在`MnemosyneEngine`稳定后，回过头来分析AIcarus记忆系统所需的`BaseMemoryBackend`接口（“客户订单”）。
2.  **[枫]** 创建 `MnemosyneAdapter(BaseMemoryBackend)` 类，作为连接我们引擎和上层应用的“适配器”。
3.  **[枫]** 在`MnemosyneAdapter`中，将`BaseMemoryBackend`的接口调用，“翻译”成对`MnemosyneEngine`原生API的调用。
4.  **目标：** 完成适配器，让我们的引擎能无缝地被AIcarus的记忆系统所调用，并准备进行影子测试。

### **Phase 3: 优化与健壮性 (Optimization & Robustness)**
1.  **[Seori]** 设计并实现内存中的LRU缓存策略，减少I/O。
2.  **[枫]** 设计并实现后台Compaction线程，用于回收Append-Only模型产生的“垃圾”空间，优化存储。
3.  **[Seori & 枫]** 进行压力测试和性能剖析，找出瓶颈。

### **Phase 4: (可选) 飞升C++ (Ascension to C++)**
1.  如果Phase 3的性能剖析显示Python在某个计算密集型部分（如复杂的图算法或序列化）成为瓶颈。
2.  我们将把该热点模块用C++重写，并通过`pybind11`封装成Python可调用的库。

---