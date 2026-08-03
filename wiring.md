# 座椅传感器 × micro:bit 硬件连线示意图

下面这张图用 mermaid 描述了 micro:bit V2 与薄膜压力座椅传感器之间的接线关系。可以用 VS Code / Typora / GitHub 等支持 mermaid 的编辑器直接预览。

## 接线示意图

```mermaid
graph LR
    subgraph SENSOR["🎬 薄膜压力座椅传感器<br/>(DJ7021-5.3-11, 常开型)"]
        S_RED["🔴 红线<br/>(信号)"]
        S_BLACK["⚫ 黑线<br/>(信号)"]
        S_PAD["📍 感应区<br/>300×240mm<br/>52 触点"]
    end

    subgraph MB["🟧 micro:bit V2"]
        V33["3.3V 引脚"]
        P0["P0 引脚<br/>(启用内部下拉电阻)"]
        LED["5×5 LED 点阵"]
        BTN_A["A 键"]
        BTN_B["B 键"]
    end

    S_RED ==>|"1. 红线"| V33
    S_BLACK ==>|"2. 黑线"| P0
    S_PAD -.->|"受压时闭合<br/>电阻 ≤100Ω"| S_RED
    S_PAD -.->|"受压时闭合<br/>电阻 ≤100Ω"| S_BLACK

    P0 -.->|"读 1=有人<br/>读 0=无人"| LED
    BTN_A -.->|"循环切换<br/>30/45/60 分钟"| LED
    BTN_B -.->|"手动重置计时"| LED

    classDef sensor fill:#ffcccc,stroke:#cc0000,stroke-width:2px,color:#000
    classDef mb fill:#ffe0b3,stroke:#cc6600,stroke-width:2px,color:#000
    classDef pin fill:#fff5cc,stroke:#aa8800,stroke-width:1px,color:#000

    class S_RED,S_BLACK,S_PAD sensor
    class V33,P0,LED,BTN_A,BTN_B mb
    class P0 pin
```

## 物理接线一览

```mermaid
graph TB
    subgraph POWER["电源"]
        USB["USB / 电池盒<br/>3.3V"]
    end

    subgraph WIRE["接线"]
        W1["① 红线<br/>3.3V → 传感器"]
        W2["② 黑线<br/>P0 ← 传感器"]
    end

    subgraph SENSOR["传感器内部"]
        NO["常开触点 NO<br/>无人: 断开 (∞)<br/>有人: 闭合 (≤100Ω)"]
    end

    USB -->|"+3.3V"| W1
    W1 --> NO
    NO --> W2
    W2 -->|"P0 内部下拉"| GND["GND (内部)"]

    classDef wire fill:#cce5ff,stroke:#0066cc,stroke-width:2px
    classDef sensor fill:#ffcccc,stroke:#cc0000,stroke-width:2px
    class W1,W2 wire
    class NO sensor
```

## 状态机时序

```mermaid
stateDiagram-v2
    [*] --> 启动
    启动 --> 无人: 显示阈值 (30/45/60)
    无人 --> 坐下: 连续 2 次读到 1
    坐下 --> 计时中: 记录起始时间
    计时中 --> 计时中: 整分钟切换<br/>滚动剩余分钟
    计时中 --> 超时: 达到阈值
    超时 --> 超时: 每 5 分钟<br/>大叉 + 箭头闪烁
    超时 --> 无人: 连续 2 次读到 0
    计时中 --> 无人: 连续 2 次读到 0
    坐下 --> 无人: A 键 / B 键重置

    无人 --> 无人: A 键切换阈值
```

## 关键说明

| 项 | 详情 |
|----|------|
| 接线数量 | 仅 2 根线（红 + 黑） |
| 所需外接元件 | **无**（用 P0 内部下拉电阻） |
| 极性 | **无**——两根线可对调，若 P0 一直读到 0 则反过来接 |
| 接口处理 | DJ7021-5.3-11 汽车插头可剪掉，露出线芯接鳄鱼夹或杜邦线 |
| 传感器安装 | 蒙皮与海绵之间（参考产品说明书图示） |

## 实物摆放参考

```
      座椅剖面图（侧面）

        ┌─────┐
        │蒙皮 │ ← 皮革/布料面
        ├─────┤
        │传感 │ ← 传感器垫在这里
        │器片 │    (300×240mm 感应区)
        ├─────┤
        │海绵 │ ← 缓冲层
        └─────┘
        ══════  座椅底板
```
