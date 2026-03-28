# 通知系统使用指南

## 概述

通知系统是一个基于HTTP API的通知处理与显示系统，随dock.py一起启动。它提供了一个简单的API接口，允许其他应用程序发送通知到屏幕上显示。

## 快速开始

1. 启动dock.py应用程序
2. 通知系统会自动启动，监听在 `127.0.0.2:8848`
3. 使用HTTP GET请求发送通知

## API接口

### 发送通知

**端点**: `GET http://127.0.0.2:8848/notify`

**必要参数**:
- `title`: 通知标题（字符串）
- `context`: 通知内容（字符串）
- `level`: 通知等级，可选值：`default`、`warn`、`error`
- `type`: 通知类型，可选值：`default`、`interaction`

**可选参数**:
- `timelimit`: 超时时间（秒），正整数，默认5秒，最多60秒
- `icon`: 通知图标路径（字符串）
- `choice`: 当`type`为`interaction`时必需，选项字符串，使用"+"分隔，最多4个选项

## 使用示例

### Python示例

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

# 交互式通知
response = requests.get("http://127.0.0.2:8848/notify", params={
    "title": "请选择",
    "context": "请选择一个选项",
    "level": "default",
    "type": "interaction",
    "choice": "确认+取消+稍后提醒"
})
```

### 命令行示例（curl）

```bash
# 默认通知
curl "http://127.0.0.2:8848/notify?title=测试&context=这是一个测试&level=default&type=default&timelimit=5"

# 交互式通知
curl "http://127.0.0.2:8848/notify?title=请选择&context=请选择选项&level=default&type=interaction&choice=是+否"
```

## 通知样式

通知系统根据不同的等级显示不同的样式：

- **default**: 蓝色背景，表示普通通知
- **warn**: 黄色背景，表示警告通知
- **error**: 红色背景，表示错误通知

特别地，当通知类型为`interaction`时，通知会显示交互按钮。用户点击按钮后，通知会关闭，并在日志中记录用户的选择。


## 错误码

- `400 Bad Request`: 参数缺失或无效
- `404 Not Found`: 请求的路径不存在
- `500 Internal Server Error`: 服务器内部错误

## 测试

项目包含一个测试脚本 `test_notification.py`，可以用于测试通知系统的各项功能。

```bash
python test_notification.py
```