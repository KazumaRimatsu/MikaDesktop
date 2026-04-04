import requests
import time

def test_default_notification():
    """测试默认通知"""
    print("测试默认通知...")
    try:
        response = requests.post("http://127.0.0.2:8848/notify", json={
            "title": "测试通知",
            "context": "这是一个测试通知内容，5秒后自动关闭",
            "level": "default",
            "type": "default",
            "timelimit": 5
        })
        print(f"响应状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"请求失败: {e}")
        return False

def test_warning_notification():
    """测试警告通知"""
    print("\n测试警告通知...")
    try:
        response = requests.post("http://127.0.0.2:8848/notify", json={
            "title": "警告",
            "context": "这是一个警告通知，请注意！",
            "level": "warn",
            "type": "default",
            "timelimit": 3
        })
        print(f"响应状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"请求失败: {e}")
        return False

def test_error_notification():
    """测试错误通知"""
    print("\n测试错误通知...")
    try:
        response = requests.post("http://127.0.0.2:8848/notify", json={
            "title": "错误",
            "context": "发生了一个错误，请检查！",
            "level": "error",
            "type": "default"
        })
        print(f"响应状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"请求失败: {e}")
        return False

def test_interaction_notification():
    """测试交互式通知"""
    print("\n测试交互式通知...")
    try:
        response = requests.post("http://127.0.0.2:8848/notify", json={
            "title": "请选择",
            "context": "请选择一个选项",
            "level": "default",
            "type": "interaction",
            "choice": ["确认","取消","稍后提醒"],
            "wait": "true"
        })
        print(f"响应状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"请求失败: {e}")
        return False

def test_invalid_parameters():
    """测试无效参数"""
    print("\n测试无效参数...")
    
    # 测试缺少必要参数
    print("1. 测试缺少title参数...")
    try:
        response = requests.post("http://127.0.0.2:8848/notify", json={
            "context": "缺少标题",
            "level": "default",
            "type": "default"
        })
        print(f"响应状态码: {response.status_code}")
        print(f"预期: 400 Bad Request")
    except Exception as e:
        print(f"请求失败: {e}")
    
    # 测试无效level参数
    print("\n2. 测试无效level参数...")
    try:
        response = requests.post("http://127.0.0.2:8848/notify", json={
            "title": "测试",
            "context": "测试无效level",
            "level": "invalid",
            "type": "default"
        })
        print(f"响应状态码: {response.status_code}")
        print(f"预期: 400 Bad Request")
    except Exception as e:
        print(f"请求失败: {e}")
    
    # 测试交互式通知缺少choice参数
    print("\n3. 测试交互式通知缺少choice参数...")
    try:
        response = requests.post("http://127.0.0.2:8848/notify", json={
            "title": "测试",
            "context": "测试缺少choice",
            "level": "default",
            "type": "interaction"
        })
        print(f"响应状态码: {response.status_code}")
        print(f"预期: 400 Bad Request")
    except Exception as e:
        print(f"请求失败: {e}")

def main():
    """主测试函数"""
    print("=== 通知系统测试 ===\n")
    
    # 检查dock.py是否在运行
    print("请确保dock.py正在运行，通知服务器已启动在127.0.0.2:8848")
    print("按Enter键开始测试...")
    input()
    
    # 运行测试
    tests = [
        ("默认通知", test_default_notification),
        ("警告通知", test_warning_notification),
        ("错误通知", test_error_notification),
        ("交互式通知", test_interaction_notification),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        if test_func():
            print(f"✓ {test_name} 通过")
            passed += 1
        else:
            print(f"✗ {test_name} 失败")
        time.sleep(2)  # 等待通知显示
    
    # 测试无效参数
    test_invalid_parameters()
    
    # 输出结果
    print(f"\n=== 测试结果 ===")
    print(f"通过: {passed}/{total}")
    
    if passed == total:
        print("所有测试通过！通知系统工作正常。")
    else:
        print("部分测试失败，请检查通知系统。")

if __name__ == "__main__":
    main()