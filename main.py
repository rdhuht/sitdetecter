# sitdetecter - 久坐提醒器 (MicroPython for micro:bit)
# 硬件：薄膜压力座椅传感器 (DJ7021-5.3-11, 常开型)
# 接线：传感器红线 → 3.3V，黑线 → P0；P0 启用内部下拉电阻
# 按键：A 键循环切换阈值（30/45/60 分钟），B 键手动重置
# 显示：5x5 LED 倒计时剩余分钟数；超时后大叉闪烁

from microbit import (
    pin0,
    button_a,
    button_b,
    display,
    Image,
    running_time,
    sleep,
)

# ============== 配置 ==============
# 久坐阈值档位（分钟），按 A 键循环切换
THRESHOLDS = [30, 45, 60]
# 提醒周期（分钟）：超时后每 N 分钟再次提醒一次
WARN_REPEAT_MIN = 5
# 采样周期（毫秒）
SAMPLE_MS = 1000
# 去抖阈值：连续 N 次采样一致才认定状态改变
DEBOUNCE_COUNT = 2

# ============== 状态 ==============
config_idx = 1  # 默认 45 分钟
sit_start_ms = None  # 本次坐下起始时刻
last_warn_ms = None  # 上次提醒时刻
raw_state = 0  # 当前原始读数 (0=无人, 1=有人)
stable_state = 0  # 去抖后的稳定状态
same_count = 0  # 连续相同采样次数


def get_threshold():
    return THRESHOLDS[config_idx]


def show_remaining(minutes_left):
    """在 5x5 LED 上显示剩余分钟数。"""
    if minutes_left <= 0:
        minutes_left = 0
    # 用滚动显示，避免同时显示两位数时混淆
    display.scroll(str(minutes_left), delay=120, wait=False)


def flash_alert():
    """超时提醒：大叉闪烁三次。"""
    for _ in range(3):
        display.show(Image.NO)
        sleep(300)
        display.clear()
        sleep(200)
    # 站起来的剪影图，提示用户起身
    display.show(Image.ARROW_NE)
    sleep(800)
    display.clear()


# ============== 初始化 ==============
# P0 启用内部下拉电阻：悬空时读 0，有人坐时由传感器把 3.3V 拉到 P0 → 读 1
pin0.set_pull(pin0.PULL_DOWN)
display.show(Image.YES)
sleep(500)
display.clear()
# 启动提示：滚动显示当前阈值
display.scroll(str(get_threshold()))


# ============== 主循环 ==============
while True:
    now = running_time()
    threshold_min = get_threshold()
    threshold_ms = threshold_min * 60 * 1000

    # ---- 读取引脚并去抖 ----
    sample = 1 if pin0.read_digital() == 1 else 0
    if sample == raw_state:
        same_count += 1
    else:
        raw_state = sample
        same_count = 1
    if same_count >= DEBOUNCE_COUNT and stable_state != raw_state:
        stable_state = raw_state

    occupied = (stable_state == 1)

    # ---- A 键：循环切换阈值 ----
    if button_a.was_pressed():
        config_idx = (config_idx + 1) % len(THRESHOLDS)
        display.scroll(str(THRESHOLDS[config_idx]))
        # 切换阈值时重置计时
        sit_start_ms = None
        last_warn_ms = None

    # ---- B 键：手动重置计时（人短暂离开时使用） ----
    if button_b.was_pressed():
        sit_start_ms = None
        last_warn_ms = None
        display.show(Image.HAPPY)
        sleep(800)
        display.clear()

    # ---- 主体状态机 ----
    if occupied:
        if sit_start_ms is None:
            # 刚刚坐下 → 记录起始时间
            sit_start_ms = now
            last_warn_ms = None

        elapsed_ms = now - sit_start_ms
        if elapsed_ms >= threshold_ms:
            # 超过阈值 → 周期性提醒
            should_warn = (
                last_warn_ms is None
                or (now - last_warn_ms) >= WARN_REPEAT_MIN * 60 * 1000
            )
            if should_warn:
                flash_alert()
                last_warn_ms = now
        else:
            # 未到阈值 → 显示剩余分钟倒计时
            minutes_left = threshold_min - int(elapsed_ms / 60000)
            if minutes_left != 0 or (elapsed_ms // 1000) % 5 == 0:
                # 整分钟切换时刷新一次（避免每秒闪烁）
                if (elapsed_ms // 1000) % 60 == 0:
                    show_remaining(minutes_left)
    else:
        # 无人 → 清空所有计时状态
        if sit_start_ms is not None or last_warn_ms is not None:
            sit_start_ms = None
            last_warn_ms = None
            display.clear()

    sleep(SAMPLE_MS)
