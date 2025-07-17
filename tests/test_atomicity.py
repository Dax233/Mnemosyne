# file: tests/test_atomicity.py (最终的、正确的逻辑版)

import os
import shutil
import pytest
from unittest.mock import patch
from pathlib import Path

from mnemosyne.engine_core import MnemosyneEngine
from mnemosyne.storage.wal import WriteAheadLog

# 我们不再需要那个复杂的fixture了，我们自己手动管理！
def setup_function():
    # 每个测试函数开始前，都清理环境
    if os.path.exists("./test_temp_data_atomic"):
        shutil.rmtree("./test_temp_data_atomic")
    os.makedirs("./test_temp_data_atomic")

def teardown_function():
    # 每个测试函数结束后，都清理环境
    if os.path.exists("./test_temp_data_atomic"):
        shutil.rmtree("./test_temp_data_atomic")

def test_edge_creation_should_be_atomic():
    TEST_DATA_PATH = "./test_temp_data_atomic"
    # 清理
    if os.path.exists(TEST_DATA_PATH): shutil.rmtree(TEST_DATA_PATH)
    os.makedirs(TEST_DATA_PATH)

    # --- 步骤1: 只创建一个引擎实例，并在其上完成所有操作 ---
    engine = MnemosyneEngine(data_path=TEST_DATA_PATH)
    node_a_id = engine._create_node({"name": "A"})
    node_b_id = engine._create_node({"name": "B"})
    
    # --- 步骤2: 模拟崩溃 ---
    # 我们要patch的目标，是commit_transaction本身！
    with patch('mnemosyne.storage.wal.WriteAheadLog.commit_transaction', side_effect=IOError("Simulated Power Failure!")):
        try:
            engine._create_edge(node_a_id, node_b_id, "connects_to", {})
        except IOError as e:
            print(f"\nSuccessfully simulated a crash: {e}")
    
    # 【关键】我们不关闭引擎，因为现实中断电时，句柄就是未关闭的！
    # 我们直接开始恢复！
    
    # --- 步骤3: 恢复 ---
    # 恢复前，先强制关闭所有句柄，模拟进程被杀死
    engine.close()
    
    MnemosyneEngine.perform_recovery(data_path=TEST_DATA_PATH)
    
    # --- 步骤4: 验证 ---
    final_engine = MnemosyneEngine(data_path=TEST_DATA_PATH)

    print("Verifying data consistency after recovery...")
    
    final_node_a_record = final_engine.native_store.get_node_record(node_a_id)
    assert final_node_a_record[2] == 0
    next_edge_id = final_engine.native_store._get_next_id(final_engine.native_store.edges_file)
    assert next_edge_id == 0
    
    final_engine.close()
    
    # 清理
    if os.path.exists(TEST_DATA_PATH): shutil.rmtree(TEST_DATA_PATH)