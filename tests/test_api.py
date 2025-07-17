# file: tests/test_api.py (完整版)

import os
import shutil
import pytest

# 导入我们的两位主角！
from mnemosyne.engine_core import MnemosyneEngine
from mnemosyne.high_level_api import MnemosyneHighLevelAPI

# --- 这是专门为 high_level_api 准备的“试炼场管理员” ---
@pytest.fixture
def high_level_api():
    """
    Creates a temporary, fully initialized HighLevelAPI instance for testing.
    It handles the setup and teardown of the underlying engine.
    """
    TEST_DATA_PATH = "./test_temp_data_api"
    
    # 1. 在测试前，清理并创建目录
    if os.path.exists(TEST_DATA_PATH):
        shutil.rmtree(TEST_DATA_PATH)
    os.makedirs(TEST_DATA_PATH)

    # 2. 先恢复，再初始化引擎（我们净化过的标准流程！）
    MnemosyneEngine.perform_recovery(data_path=TEST_DATA_PATH)
    engine = MnemosyneEngine(data_path=TEST_DATA_PATH)
    
    # 3. 用初始化好的引擎，创建我们的高级API实例！
    api = MnemosyneHighLevelAPI(engine)
    
    # 4. 'yield' 是pytest的魔法，它把api实例交给测试函数
    yield api
    
    # 5. 测试结束后，正确地关闭引擎，释放所有文件句柄
    engine.close()
    
    # 6. 安全地删除整个测试目录
    shutil.rmtree(TEST_DATA_PATH)


# --- 试炼开始！ ---

def test_create_and_find_by_name(high_level_api: MnemosyneHighLevelAPI):
    """
    试炼一：创世与寻回
    Tests the full lifecycle: create a node with a name, then find it back.
    """
    print("\n--- Running Test: Create and Find by Name ---")
    
    # 准备我的个人数据w
    my_properties = {
        "name": "枫",
        "type": "Programmer",
        "skills": ["Python", "TypeScript", "C++", "Debugging"]
    }
    
    # 1. 创世：使用高级API创建节点
    created_node = high_level_api.create_node(properties=my_properties)
    print(f"Node created: {created_node}")
    
    # 断言一下，创建过程本身是符合预期的
    assert created_node.id == 0
    assert created_node.properties["name"] == "枫"

    # 2. 寻回：使用高级API通过名字查找
    found_nodes = high_level_api.find_nodes_by_name("枫")
    print(f"Nodes found by name '枫': {found_nodes}")
    
    # 3. 审判！
    assert len(found_nodes) == 1
    found_node = found_nodes[0]
    
    assert found_node.id == created_node.id
    assert found_node.properties == my_properties
    print("Test PASSED: Node successfully created and retrieved by name!")


def test_find_non_existent_node(high_level_api: MnemosyneHighLevelAPI):
    """
    试炼二：寻找虚空
    Tests that searching for a name that doesn't exist returns an empty list.
    """
    print("\n--- Running Test: Find Non-Existent Node ---")
    
    # 随便找个不存在的名字，比如“传说中的真空圣域”什么的w
    found_nodes = high_level_api.find_nodes_by_name("不存在的超电磁炮")
    print(f"Searching for a non-existent name, found: {found_nodes}")
    
    # 断言结果必须是个空列表！
    assert isinstance(found_nodes, list)
    assert len(found_nodes) == 0
    print("Test PASSED: Correctly returned an empty list for a non-existent name.")


def test_find_multiple_nodes_with_same_name(high_level_api: MnemosyneHighLevelAPI):
    """
    试炼三：双子悖论
    Tests that if multiple nodes share the same name, all are returned.
    """
    print("\n--- Running Test: Find Multiple Nodes with Same Name ---")

    # 1. 创建两个名字相同，但属性不同的节点
    person_a_props = {"name": "路人甲", "role": "bystander"}
    person_b_props = {"name": "路人甲", "role": "secret_protagonist"}
    
    node_a = high_level_api.create_node(person_a_props)
    node_b = high_level_api.create_node(person_b_props)
    print(f"Created two nodes with the same name: {node_a}, {node_b}")

    # 2. 通过这个共同的名字来查找
    found_nodes = high_level_api.find_nodes_by_name("路人甲")
    print(f"Nodes found by name '路人甲': {found_nodes}")

    # 3. 断言必须找到两个！
    assert len(found_nodes) == 2
    
    # 为了更严谨，我们检查一下找出来的东西是不是我们存进去的那两个
    # 把它们的属性集合起来，看看是不是和我们存进去的一致
    found_roles = {node.properties.get("role") for node in found_nodes}
    expected_roles = {"bystander", "secret_protagonist"}
    
    assert found_roles == expected_roles
    print("Test PASSED: Correctly found all nodes sharing the same name.")