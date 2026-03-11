# SmartDNS Manager

一个基于 Python 和 Tkinter 构建的，在Windows下使用的 SmartDNS 管理工具。旨在简化 SmartDNS 的日常使用流程，自动处理进程启动与系统 DNS 切换，方便管理。


> 程序可能不能完全符合需求，正在进行完善。或者使用官方的[仪表盘插件](https://pymumu.github.io/smartdns/config/dashboard/)。

> 有更专业的需求，推荐使用[almightyYantao](https://github.com/almightyYantao/smartdns-manager)的SmartDNS Manager项目


### 必看说明
1. 程序通过静默启动的方式隐藏SmartDNS的运行窗口,暂时没有指定配置文件路径  
   默认启动命令：``` smartdns run ```
   
2. 程序会备份原有非SmartDNS的DNS服务器，备份配置在：
```bash 
%AppData%\smartdns_manager
```
3. 程序默认使用官方的[msi安装包](https://github.com/mokeyish/smartdns-rs/releases/download/v0.13.0/smartdns-x86_64-pc-windows-msvc-v0.13.0.msi)，配置文件目录在：
```bash 
C:\ProgramData\SmartDNS
```
4. 有需要替换程序图标的，将favicon.ico替换成自己的图标，文件名相同即可

5. 需要本地配置好SmartDNS  
即：打开cmd执行`smartdns --help`能正常执行

## 核心功能

- **🚀 一键启动/停止**：自动管理 `smartdns.exe` 后台进程，无需手动操作命令行。
- **🛡️ 智能 DNS 切换**：
  - 启动时自动备份当前网卡 DNS，并切换为本地回环地址 (`127.0.0.1`)。
  - 停止时引导用户恢复原始 DNS 设置。
- **🔍 自动识别活动网卡**：智能检测当前正在使用的网络适配器，避免手动配置。
- **⚠️ 容错保护机制**：
  - **后备方案**：若 DNS 备份文件意外丢失，程序会自动将 DNS 重置为“自动获取 (DHCP)”，确保不会因 SmartDNS 关闭而断网。
  - **异常检测**：启动时若发现 DNS 处于异常状态（如残留的 127.0.0.1），会优先尝试修复。
- **📋 实时操作日志**：图形化显示操作状态与系统反馈，方便排查问题。
- **🎨 现代感 UI**：采用深色模式设计，流畅的视觉交互与状态提示。

## 运行与编译

### SmartDNS相关配置
- Windows系统参考:[官方文档](https://github.com/mokeyish/smartdns-rs/blob/main/README_zh-CN.md)
- [配置文档](https://github.com/pymumu/smartdns/blob/doc/docs/configuration.md)

### 环境要求
- Windows 10/11 (需要管理员权限)
- Python 3.10+
- 依赖库：`psutil` (用于进程管理)
- 已安装PyInstaller

### 安装依赖
```bash
pip install psutil pyinstaller
```


### 方法一：使用 PyInstaller 编译（推荐）
1. 下载源码压缩包

2. 文件编译：
```
bash pyinstaller --noconsole --onefile --uac-admin --icon="favicon.ico" --add-data "favicon.ico;." smartdns_manager.py
```

### 方法二：下载预编译文件
> 前往[release](https://github.com/lsersc/SmartDNS_Manager/releases)页面下载

### 运行界面

![程序界面](https://cdn.jsdelivr.net/gh/lsersc/SmartDNS_Manager@refs/heads/main/src/1.png)


## 注意事项
- 本工具主要配合 `smartdns.exe` 使用，请确保安装和配置好了SmartDNS。


---
## 更新记录

### [v1.0](https://github.com/lsersc/SmartDNS_Manager/releases/tag/v1.0)
- 简单的SmartDNS管理
- 还算看得过去的界面
- 不知道有没有bug
- 需要本地配置好SmartDNS
  即：打开cmd执行smartdns --help能正常执行
- 程序运行需要**管理员权限**，以便执行 `netsh` 命令修改系统网络设置。  
---
*注：本项目作为 SmartDNS 的辅助管理前端，剩余部分可根据实际需求进一步完善。*
