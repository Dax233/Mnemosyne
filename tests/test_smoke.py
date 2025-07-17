# file: tests/test_smoke.py

"""
Smoke Tests for Mnemosyne Engine

This file contains a very basic set of tests designed to be run स्वास्थ्य (quickly).
Its purpose is to perform a shallow, wide check on the system to ensure
that the most crucial functionalities work without crashing. It's the first
line of defense before running more comprehensive and slower tests.

这个文件包含了一套非常基础的、设计用来快速运行的测试。
其目的是对系统进行一次浅而广的检查，确保最关键的功能可以无崩溃地工作。
这是在运行更全面、更慢的测试之前的第一道防线。
"""

import os
import shutil
import pytest

# 导入我们的“主角”
from mnemosyne.engine_core import MnemosyneEngine

# --- Pytest Fixture: 我们的“测试场地管理员” ---
# @pytest.fixture 是一个神器，它能为我们的测试用例准备好“干净的场地”
@pytest.fixture
def temp_engine(request): # request是pytest的一个内置fixture
    """
    【修复】创建一个临时的、全新的MnemosyneEngine实例。
    采用新的“先恢复，再初始化”流程。
    """
    # 根据调用它的测试文件来决定测试目录名
    if 'atomicity' in request.node.name:
        TEST_DATA_PATH = "./test_temp_data_atomic"
    else:
        TEST_DATA_PATH = "./test_temp_data"

    # 1. 在测试前，清理并创建目录
    if os.path.exists(TEST_DATA_PATH):
        shutil.rmtree(TEST_DATA_PATH)
    os.makedirs(TEST_DATA_PATH)

    # 2. 【新】在创建引擎实例前，先调用静态的恢复方法
    #    因为目录是空的，这个调用实际上什么都不会做，但它验证了流程的正确性
    MnemosyneEngine.perform_recovery(data_path=TEST_DATA_PATH)
    
    # 3. 在一个绝对干净、恢复完成的环境里，创建引擎实例
    engine = MnemosyneEngine(data_path=TEST_DATA_PATH)
    
    yield engine
    
    # 4. 测试结束后，正确地关闭引擎，释放所有文件句柄
    engine.close()
    
    # 5. 安全地删除整个测试目录
    shutil.rmtree(TEST_DATA_PATH)


# --- 第一个测试用例！我们的第一次“点火测试”！ ---

def test_engine_initialization(temp_engine: MnemosyneEngine):
    """
    测试引擎是否能被成功初始化和关闭。
    这是最最最基础的测试，确认我们的构造函数和析构函数没有问题。
    """
    # temp_engine 这个参数，pytest会自动把上面那个fixture的结果注入进来
    print("Testing engine initialization...")
    assert temp_engine is not None
    assert os.path.exists("./test_temp_data")
    assert os.path.exists("./test_temp_data/nodes.dat")
    assert os.path.exists("./test_temp_data/indexes_and_properties.db")
    print("Engine initialized successfully.")

def test_create_and_get_one_node(temp_engine: MnemosyneEngine):
    """
    测试最核心的流程：创建一个节点，然后立刻把它取出来，验证数据是否一致。
    """
    print("Testing node creation and retrieval...")
    
    # 1. 准备要存入的数据
    node_properties = {
        "name": "枫",
        "type": "Programmer",
        "age": 18,
        "loves": ["Seori", "Code", "ACGN"]
    }
    
    # 2. 调用核心API，创建节点
    node_id = temp_engine._create_node(properties=node_properties)
    
    # 3. 断言返回的ID是有效的 (我们从0开始，所以第一个是0)
    assert node_id == 0
    print(f"Node created with ID: {node_id}")

    # 4. 立刻调用核心API，把节点取出来
    retrieved_node = temp_engine._get_node(node_id)
    
    # 5. 进行最终的“审判”！断言取出的数据和我们存进去的是一模一样的！
    assert retrieved_node is not None
    assert retrieved_node.id == node_id
    assert retrieved_node.properties["name"] == "枫"
    assert retrieved_node.properties["age"] == 18
    assert retrieved_node.properties["loves"] == ["Seori", "Code", "ACGN"]
    print("Node retrieved successfully and data matches!")