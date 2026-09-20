# XCHP HID 电源控制协议

面向 AI 自动化编程 / 自动化测试终端：通过 USB **HID** 控制 XCH1-AI-BOX 上两路 HR8833 负载电源开关（断电、上电、脉冲复位），与 **CMSIS-DAP**（下载/调试）和 **CDC**（目标串口）同机共存。

| 项 | 值 |
|---|---|
| 协议名 / Magic | `XCHP`（`0x58 0x43 0x48 0x50`） |
| 版本 | `0x01` |
| USB VID:PID | `0x0D28:0x0204`（CMSIS-DAP 复合设备） |
| HID 接口号 | Interface **3**（DAP=0，CDC=1/2，HID=3，WebUSB=4） |
| 端点 | OUT `0x04`，IN `0x84`，包长 **64** 字节（全速） |
| OUT Report ID | `0x01`（主机 → 设备） |
| IN Report ID | `0x02`（设备 → 主机） |
| 通道数 | 2（CH1 / CH2），默认上电均为 **OFF** |

> Windows：通常以 **HID raw**（`HidD_SetOutputReport` / `ReadFile`）或 [hidapi](https://github.com/libusb/hidapi) 访问。  
> Linux：`/dev/hidrawN`；写时一般 **带 Report ID**，读回也带 Report ID。

---

## 1. 设备能力分工（给 AI Agent）

| 通道 | 用途 | 本协议？ |
|---|---|---|
| CMSIS-DAP（WinUSB/Bulk） | 下载固件、SWD 调试 | 否，用标准 DAP |
| CDC ACM | 读目标板 UART 日志 | 否，当串口打开 |
| **HID XCHP** | 控制目标供电 / 断电复位 | **是** |

典型自动化流程：

1. `PING` / `GET_INFO` 确认设备在线  
2. `SET_CH` 给目标板上电  
3. 用 DAP 烧录 / 用 CDC 读日志  
4. 需要复位时用 `PULSE`（先断后通）  
5. 结束可用 `SET_CH` 断电  

---

## 2. 报文格式

每帧固定写/读 **64 字节**（不足补 `0x00`）。

### 2.1 请求（Host → Device）

| 偏移 | 长度 | 字段 | 说明 |
|---|---|---|---|
| 0 | 1 | Report ID | 固定 `0x01` |
| 1..4 | 4 | Magic | `XCHP` |
| 5 | 1 | Ver | `0x01` |
| 6 | 1 | Cmd | 见命令表 |
| 7 | 1 | Seq | 主机自增序号，应答原样回显 |
| 8 | 1 | Len | payload 字节数（0～54） |
| 9.. | Len | Payload | 命令参数 |
| …63 | | Pad | `0x00` |

### 2.2 应答（Device → Host）

| 偏移 | 长度 | 字段 | 说明 |
|---|---|---|---|
| 0 | 1 | Report ID | 固定 `0x02` |
| 1..4 | 4 | Magic | `XCHP` |
| 5 | 1 | Ver | `0x01` |
| 6 | 1 | Cmd | 与请求相同 |
| 7 | 1 | Seq | 与请求相同 |
| 8 | 1 | **Status** | 见状态码 |
| 9 | 1 | Len | 应答 payload 长度 |
| 10.. | Len | Payload | 见各命令 |
| …63 | | Pad | `0x00` |

### 2.3 状态码 Status

| 值 | 名称 | 含义 |
|---|---|---|
| `0x00` | OK | 成功 |
| `0x01` | BAD_MAGIC | Magic 不是 XCHP |
| `0x02` | BAD_VER | 版本不支持 |
| `0x03` | BAD_CMD | 未知命令 |
| `0x04` | BAD_PARAM | 参数非法 |
| `0x05` | BUSY | 设备忙（队列满），请重试 |

---

## 3. 命令表

通道号：**1 = CH1，2 = CH2**（不要用 0）。  
开关：**0 = OFF，1 = ON**。

| Cmd | 名称 | 请求 Payload | 成功应答 Payload | 说明 |
|---|---|---|---|---|
| `0x00` | PING | （空） | `'O''K'`（2 字节） | 连通性检测 |
| `0x01` | GET_STATUS | （空） | `[ch1, ch2]` | 读两路状态 |
| `0x02` | SET_CH | `[ch, on]` | `[ch1, ch2]` | 设置单路 |
| `0x03` | SET_ALL | `[ch1, ch2]` | `[ch1, ch2]` | 同时设置两路 |
| `0x04` | PULSE | `[ch, off_lo, off_hi]` 或再加 `[on_lo, on_hi]` | `[ch1, ch2]` | 断电 `off_ms` 再上电；可选再保持 `on_ms`（见下） |
| `0x05` | GET_INFO | （空） | `[ver, ch_num, flags]` | `ver=1`，`ch_num=2`，`flags bit0=支持 PULSE` |

### PULSE 细节

- `off_ms`：小端 `uint16`，断电持续时间；`0` 时按 **100 ms**；上限钳位 **10000 ms**  
- `on_ms`：可选；省略或为 0 表示上电后立即返回（保持 ON）；非 0 则上电后再延时该毫秒（上限 10000）  
- 时序：`OFF → delay(off_ms) → ON → [delay(on_ms)]`  
- 用于目标板 **断电复位**，无需人工按复位键  

### 硬件对应（实现参考）

| 通道 | AIN1 | AIN2 | EN（XL9555） |
|---|---|---|---|
| CH1 | GPIO2 | GPIO38 | `MOTOR_EN_IO` |
| CH2 | GPIO40 | GPIO41 | `MOTOR2_EN_IO` |

导通：AIN1=1，AIN2=0，EN=1 → AOUT1≈VCC，AOUT2≈GND。

---

## 4. 示例帧（十六进制）

Seq 均用 `0x01`。每帧共 64 字节，下表只列有效头，其余 `00`。

### PING

```
01 58 43 48 50 01 00 01 00
```

期望应答头：`02 58 43 48 50 01 00 01 00 02 4F 4B …`

### GET_STATUS

```
01 58 43 48 50 01 01 01 00
```

### SET_CH：CH1 上电

```
01 58 43 48 50 01 02 01 02 01 01
```

### SET_CH：CH1 断电

```
01 58 43 48 50 01 02 01 02 01 00
```

### SET_ALL：CH1=ON，CH2=OFF

```
01 58 43 48 50 01 03 01 02 01 00
```

### PULSE：CH1 断电 200ms 再上电

`200 = 0x00C8` → `C8 00`

```
01 58 43 48 50 01 04 01 03 01 C8 00
```

---

## 5. 主机侧伪代码（Python + hidapi）

```python
import hid  # pip install hidapi

VID, PID = 0x0D28, 0x0204
REPORT_OUT, REPORT_IN = 0x01, 0x02
MAGIC = bytes([0x58, 0x43, 0x48, 0x50])  # XCHP

def open_xchp():
    for d in hid.enumerate(VID, PID):
        # 选 Usage Page 0xFF00 的 vendor HID（非键盘等）
        if d.get("usage_page") == 0xFF00:
            h = hid.device()
            h.open_path(d["path"])
            h.set_nonblocking(False)
            return h
    raise RuntimeError("XCHP HID not found")

def xchp_xfer(dev, cmd, payload=b"", seq=1):
    pkt = bytearray(64)
    pkt[0] = REPORT_OUT
    pkt[1:5] = MAGIC
    pkt[5] = 0x01
    pkt[6] = cmd
    pkt[7] = seq & 0xFF
    pkt[8] = len(payload)
    pkt[9:9+len(payload)] = payload
    dev.write(pkt)
    rsp = bytes(dev.read(64, timeout_ms=2000))
    assert rsp[0] == REPORT_IN and rsp[1:5] == MAGIC
    status, plen = rsp[8], rsp[9]
    return status, rsp[10:10+plen]

dev = open_xchp()
assert xchp_xfer(dev, 0x00)[0] == 0          # PING
st, pl = xchp_xfer(dev, 0x02, bytes([1, 1])) # CH1 ON
assert st == 0 and pl[0] == 1
st, _ = xchp_xfer(dev, 0x04, bytes([1, 0xC8, 0x00]))  # PULSE 200ms
```

**注意：**

- 一次只发一帧，等应答再发下一帧（设备队列深度 4，溢出返回 BUSY）  
- `PULSE` 会阻塞至多约 10s+10s，读超时请设大一些  
- 枚举时复合设备有多个接口，务必按 **Usage Page `0xFF00`** 选中 vendor HID  

---

## 6. 固件接口（设备内）

应用层实现：`main/hid_pwr.c`，注册到 CherryUSB HID 队列处理。

```c
#include "pwr_switch.h"
pwr_switch_set(PWR_CH1, true);   /* 与 HID 共用 */
pwr_switch_get(PWR_CH2);
pwr_switch_toggle(PWR_CH1);
```

HID ISR 只入队；`dap_task` 中 `chry_hid_handle()` 调用 `hid_pwr_process()`（可安全做 XL9555 I2C 与 `vTaskDelay`）。

---

## 7. 版本与扩展

- 当前 **Ver = 1**：仅电源开关  
- 保留 Cmd `0x10+` 供后续扩展（勿占用）  
- 升级模式（开机按 A：MSC+CDC）**无 HID**，本协议不可用  

文档版本与固件协议版本一致：`XCHP v1`。
