# Sit Remoter - Chrome 扩展

PC 端的 micro:bit 蓝牙久坐提醒显示。

## 功能

- 通过 Web Bluetooth 连接 `sitdetecter` micro:bit
- 显示坐了多久(MM:SS 大数字)
- SVG 圆环进度
- 状态文字:空闲 / 计时中 / 超时 / 冷却
- 超时报警音
- A/B 按钮远程控制(等价于 micro:bit 上的物理按键)
- 5 秒自动重连

## 安装

1. 打开 Chrome 浏览器
2. 地址栏输入 `chrome://extensions/`,回车
3. 打开右上角的**开发者模式**
4. 点击左上角**加载已解压的扩展程序**
5. 选择本目录 `extension/`
6. 安装完成后,工具栏会出现 Sit Remoter 图标

## 使用

1. 把烧录了 v2.0.0 固件的 micro:bit 上电
2. 点击工具栏上的 Sit Remoter 图标,弹出 popup
3. 点击"连接 micro:bit",在弹窗里选择你的 micro:bit
4. 连接成功后即可看到实时状态

## 平台兼容性

| 平台 | 支持 |
|------|------|
| Chrome / Edge / Chromium on Windows / macOS / Linux / ChromeOS | ✅ |
| Chrome on Android (≥91) | ✅ |
| Firefox / Safari (含 iOS) | ❌ Web Bluetooth 不可用 |

## 自定义

- 替换 `audio/alert.mp3` 为其他 < 1 秒的 mp3/wav 即可改变超时提示音
- 修改 `popup.css` 中的颜色即可定制主题
- 阈值数组在 `popup.js` 顶部 `THRESHOLDS_MIN`,需与 micro:bit 端 `main.py` 的 `THRESHOLDS` 保持一致

## BLE 协议

详见仓库根目录的 `README.md`。

## 故障排查

| 现象 | 可能原因 | 解决 |
|------|---------|------|
| "连接 micro:bit" 按钮无反应 | 浏览器不支持 Web Bluetooth | 换 Chrome/Edge 浏览器 |
| 看不到 micro:bit 设备 | micro:bit 蓝牙固件未启用 | 检查 v2.0.0 固件是否成功烧录 |
| 连接后 popup 没反应 | BLE 协议不匹配 | 确认 micro:bit 与扩展都用本仓库最新代码 |
| 提示音不响 | Chrome 自动播放策略 | 用户首次点击 Connect 后会自动解锁 |