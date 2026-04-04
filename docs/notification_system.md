# 通知系统使用指南

## 概述

通知系统是一个基于HTTP API的通知处理与显示系统，随dock.py一起启动。它提供了一个简单的API接口，允许其他应用程序发送通知到屏幕上显示。系统支持普通通知和交互式通知，并可以等待用户选择后返回结果。

## 快速开始

1. 启动dock.py应用程序
2. 通知系统会自动启动，监听在 `127.0.0.2:8848`
3. 使用HTTP GET或POST请求发送通知

## API

### 发送通知

**端点**: `POST http://127.0.0.2:8848/notify`

**请求头**:

- `Content-Type: application/json`

**请求体（JSON格式）**:

```json
{
  "title": "通知标题",
  "context": "通知内容",
  "level": "default",
  "type": "default",
  "timelimit": 5,
  "icon": "图标路径",
  "choice": ["选项1", "选项2", "选项3"],
  "wait": true
}
```

**参数说明**:

| 参数名         | 类型      | 必需                     | 说明                                        |
| ----------- | ------- | ---------------------- | ----------------------------------------- |
| `title`     | string  | 是                      | 通知标题                                      |
| `context`   | string  | 是                      | 通知内容                                      |
| `level`     | string  | 是                      | 通知等级：`default`（默认）、`warn`（警告）、`error`（错误） |
| `type`      | string  | 是                      | 通知类型：`default`（默认）、`interaction`（交互式）     |
| `timelimit` | integer | 否                      | 超时时间（秒），1-60，默认5秒                         |
| `icon`      | string  | 否                      | 图标文件路径                                    |
| `choice`    | array   | 当`type=interaction`时必需 | 选项列表，最多4个选项                               |
| `wait`      | boolean | 否                      | 是否等待用户选择，仅对交互式通知有效，默认false                |

### 响应格式

所有请求都返回JSON格式的响应：

#### 成功响应

```json
{
  "status": "success",
  "message": "Notification received"
}
```

#### 交互式通知等待响应

当`wait=true`且`type=interaction`时，服务器会等待用户选择后返回：

```json
{
  "status": "success",
  "choice": "用户选择的选项"
}
```

#### 超时响应

```json
{
  "status": "timeout",
  "message": "No choice made before timeout"
}
```

#### 错误响应

```json
{
  "status": "error",
  "message": "错误描述"
}
```

## 使用示例

### Python示例

#### 使用GET请求（已弃用）

```python
import requests

# 默认通知（5秒后自动关闭）
response = requests.get("http://127.0.0.2:8848/notify", params={
    "title": "测试通知",
    "context": "这是一个测试通知内容",
    "level": "default",
    "type": "default",
    "timelimit": "5"
})

# 警告通知
response = requests.get("http://127.0.0.2:8848/notify", params={
    "title": "警告",
    "context": "这是一个警告通知，请注意！",
    "level": "warn",
    "type": "default",
    "timelimit": "3"
})

# 错误通知
response = requests.get("http://127.0.0.2:8848/notify", params={
    "title": "错误",
    "context": "发生了一个错误，请检查！",
    "level": "error",
    "type": "default"
})

# 交互式通知（不等待）
response = requests.get("http://127.0.0.2:8848/notify", params={
    "title": "请选择",
    "context": "请选择一个选项",
    "level": "default",
    "type": "interaction",
    "choice": "确认+取消+稍后提醒"
})

# 交互式通知（等待用户选择）
response = requests.get("http://127.0.0.2:8848/notify", params={
    "title": "请选择",
    "context": "请选择一个选项",
    "level": "default",
    "type": "interaction",
    "choice": "是+否",
    "wait": "true",
    "timelimit": "30"
})
print(f"用户选择: {response.json().get('choice')}")
```

#### 使用POST请求（推荐）

```python
import requests
import json

# 默认通知
response = requests.post(
    "http://127.0.0.2:8848/notify",
    json={
        "title": "测试通知",
        "context": "这是一个测试通知内容",
        "level": "default",
        "type": "default",
        "timelimit": 5
    }
)

# 交互式通知（等待用户选择）
response = requests.post(
    "http://127.0.0.2:8848/notify",
    json={
        "title": "请确认",
        "context": "您确定要执行此操作吗？",
        "level": "warn",
        "type": "interaction",
        "choice": ["确认", "取消", "稍后提醒"],
        "wait": True,
        "timelimit": 30
    }
)

result = response.json()
if result["status"] == "success":
    if "choice" in result:
        print(f"用户选择了: {result['choice']}")
    else:
        print("通知已发送")
elif result["status"] == "timeout":
    print("用户未在时间内做出选择")
```

### 命令行示例

#### curl GET请求

```bash
# 默认通知
curl "http://127.0.0.2:8848/notify?title=测试&context=这是一个测试&level=default&type=default&timelimit=5"

# 交互式通知
curl "http://127.0.0.2:8848/notify?title=请选择&context=请选择选项&level=default&type=interaction&choice=是+否"

# 交互式通知（等待选择）
curl "http://127.0.0.2:8848/notify?title=请选择&context=请选择选项&level=default&type=interaction&choice=是+否&wait=true&timelimit=30"
```

#### curl POST请求

```bash
# 默认通知
curl -X POST http://127.0.0.2:8848/notify \
  -H "Content-Type: application/json" \
  -d '{"title":"测试","context":"这是一个测试","level":"default","type":"default","timelimit":5}'

# 交互式通知（等待选择）
curl -X POST http://127.0.0.2:8848/notify \
  -H "Content-Type: application/json" \
  -d '{"title":"请确认","context":"您确定要执行此操作吗？","level":"warn","type":"interaction","choice":["确认","取消"],"wait":true,"timelimit":30}'
```

## 通知样式

通知系统根据不同的等级显示不同的样式：

- **default**: 蓝色背景，表示普通通知
- **warn**: 黄色背景，表示警告通知
- **error**: 红色背景，表示错误通知

特别地，当通知类型为`interaction`时，通知会显示交互按钮。用户点击按钮后，通知会关闭，并返回用户的选择（如果启用了等待功能）。

## 错误码

- `400 Bad Request`: 参数缺失或无效
- `404 Not Found`: 请求的路径不存在
- `411 Length Required`: POST请求缺少Content-Length头
- `500 Internal Server Error`: 服务器内部错误

## 系统架构

### 组件说明

1. **NotificationRequestHandler**: HTTP请求处理器，处理GET/POST请求
2. **NotificationServer**: 通知服务器，管理HTTP服务器线程
3. **NotificationWindow**: 通知窗口，负责UI显示和用户交互
4. **NotificationManager**: 通知管理器，协调服务器和UI，集成到线程管理器

### 线程管理

通知系统使用线程管理器进行生命周期管理：

```python
# 在dock.py中的集成
from Lib.features.notification_system import NotificationManager
self.notification_manager = NotificationManager(parent=self)
notification_system_id = self.thread_manager.create(
    name=self.notification_manager.get_name(),
    start_when_create=True,
    worker=self.notification_manager
)
```

### 等待机制

当启用`wait=true`参数时，交互式通知会使用线程同步机制等待用户选择：

1. 服务器创建`threading.Event`对象
2. 显示通知窗口
3. 用户点击按钮时，设置选择结果并触发事件
4. 服务器线程等待事件触发或超时
5. 返回用户选择或超时结果

## 高级功能

### 超时控制

- 默认超时时间：5秒
- 最大超时时间：60秒
- 交互式通知等待超时：使用`timelimit`参数指定

### 图标支持

可以通过`icon`参数指定通知图标路径，支持本地文件路径。

### 批量通知

可以同时发送多个通知，系统会按顺序显示。

## 测试

项目包含一个测试脚本 `test_notification.py`，可以用于测试通知系统的各项功能。

```bash
python test_notification.py
```

## 与线程管理器的集成

通知系统已完全集成到线程管理器中，支持以下功能：

- **线程状态管理**: 可以通过线程管理器监控通知系统的状态
- **暂停/恢复**: 支持通过线程管理器暂停和恢复通知服务
- **统一生命周期管理**: 与dock.py中其他线程统一管理

具体使用方法请参考[线程管理器文档](thread_manager.md)。
