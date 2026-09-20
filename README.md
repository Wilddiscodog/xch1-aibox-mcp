# XCH1-AI-BOX MCP Server

供 AI 编程 / 自动化调试软件通过 **Model Context Protocol (MCP)** 控制 XCH1-AI-BOX：

| 能力 | MCP 工具 | 底层 |
|---|---|---|
| 双路电源开关 / 脉冲复位 | `power_*` | HID **XCHP** |
| 目标板 UART 收发 | `serial_*` | USB **CDC ACM** |
| 设备发现 / 能力说明 | `device_*` | HID + 串口枚举 |
| SWD 下载调试指引 | `dap_guidance` | 外部 pyOCD / OpenOCD |

> CMSIS-DAP 协议本身由 IDE / pyOCD 驱动；本 MCP 负责供电与串口侧自动化闭环。

## 环境要求

- Python **3.10+**
- Windows / macOS / Linux（需能访问 USB HID）
- 已烧录支持 XCHP 的 XCH1-AI-BOX，且处于**工作模式**（勿开机按住 A 进升级盘）

## 安装

```bat
git clone <本仓库 URL>
cd xch1-aibox-mcp
python -m pip install -e .
```

依赖由 `pyproject.toml` 自动安装：`mcp`（`<2`）、`hidapi`、`pyserial`。

## 在 Cursor 中配置

安装完成后，将下列片段加入 Cursor MCP 设置（与本机路径无关）：

```json
{
  "mcpServers": {
    "xch1-aibox": {
      "command": "xch1-aibox-mcp"
    }
  }
}
```

若未把 Scripts 目录加入 PATH，可改用模块方式：

```json
{
  "mcpServers": {
    "xch1-aibox": {
      "command": "python",
      "args": ["-m", "xch1_aibox_mcp"]
    }
  }
}
```

也可直接参考仓库内 `mcp.json.example`。

## 推荐 AI 工作流

1. `device_list` / `power_connect` / `power_ping`
2. `power_set(channel=1, on=true)` 给目标板上电
3. 用 pyOCD 经 CMSIS-DAP 烧录（见 `dap_guidance`）
4. `serial_open` → `serial_read` 抓日志
5. `power_pulse(channel=1, off_ms=200)` 断电复位
6. 结束：`power_set(..., on=false)` / `power_disconnect`

## 手动试跑

```bat
python -m xch1_aibox_mcp
```

进程通过 **stdio** 与 MCP 宿主通信；不要在普通终端里当交互程序使用。

## 协议文档

- [`docs/XCHP-HID-Protocol.md`](docs/XCHP-HID-Protocol.md) — HID **XCHP** 电源控制协议（帧格式、命令、示例）
