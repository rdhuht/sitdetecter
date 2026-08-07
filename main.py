# sitdetecter - 久坐提醒器 (MicroPython for micro:bit)
# 硬件：薄膜压力座椅传感器 (DJ7021-5.3-11, 常开型)
# 接线：传感器红线 → 3.3V，黑线 → P0；P0 启用内部下拉电阻
# 按键：A 键循环切换阈值（15/30/45/60 分钟），B 键手动重置
# 显示：5x5 LED 接力式进度条（总时长均分到 25 颗，每颗持续闪烁 N 次后转常亮）+ 超时骷髅闪烁 + 站立后小人走路动画

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
THRESHOLDS = [15, 30, 45, 60]   # 久坐阈值档位（分钟），按 A 键循环切换
WARN_REPEAT_MIN = 5             # 超时后每 N 分钟再叠加一次 X + 箭头
# 冷却时长 = 实际坐的时长 × COOLDOWN_RATIO(默认 20%)
# 阈值 45 分钟准时站起 → 冷却 9 分钟;坐 60 分钟才起 → 冷却 12 分钟
COOLDOWN_RATIO = 0.2
SAMPLE_MS = 100                 # 主循环周期（毫秒）—— 10 Hz,确保 1 Hz 闪烁可见
DEBOUNCE_COUNT = 2              # 去抖：连续 N 次采样一致才认定状态改变
WALK_FRAME_MS = 200             # 走路动画每帧切换间隔

# ============== 进度条 ==============
LED_FILL_ORDER = [(x, y) for y in range(4, -1, -1) for x in range(5)]
TOTAL_LEDS = 25

# ============== 状态 ==============
config_idx = 2                  # 默认 45 分钟(THRESHOLDS 索引 2)
sit_start_ms = None             # 本次坐下起始时刻
last_warn_ms = None             # 上次大叉提醒时刻
stand_start_ms = None           # 用户站起来(开始冷却)的时刻
actual_sit_ms = None            # 本次坐下实际坐的总时长(用于计算冷却 = 实际坐 × 20%)
raw_state = 0                   # 当前原始读数 (0=无人, 1=有人)
stable_state = 0                # 去抖后的稳定状态
same_count = 0                  # 连续相同采样次数
alerting = False                # 是否处于大叉强提醒期间

# ============== 自定义图像 ==============
# 走路动画第二帧(STICKFIGURE + 双脚分开)
WALK_FRAME_2 = Image("09090:90909:90909:09090:09090")


def get_threshold():
    return THRESHOLDS[config_idx]


def reset_progress():
    """坐下或离开时清空计时状态。"""
    global sit_start_ms, last_warn_ms
    sit_start_ms = None
    last_warn_ms = None


def reset_cooldown():
    """用户主动按键或进入正常状态时清空冷却状态。"""
    global stand_start_ms, actual_sit_ms
    stand_start_ms = None
    actual_sit_ms = None


def draw_progress(now_ms, elapsed_ms, total_ms):
    """画接力式均匀闪烁进度条:
    - 总时长 total_ms 平均分配给 25 颗 LED,每颗分到 per_led_ms = total_ms // 25 毫秒
    - 每颗 LED 在自己的 per_led_ms 时段内持续 1 Hz 闪烁(亮 0.5s / 灭 0.5s)
    - 闪烁结束后立刻转常亮,作为累计进度
    - 任意时刻只有 1 颗正在闪烁,之前完成的常亮,未开始的灭
    - 填充方向:从下往上、每行从左到右(LED_FILL_ORDER)
    """
    if elapsed_ms >= total_ms:
        for x, y in LED_FILL_ORDER:
            display.set_pixel(x, y, 9)
        return

    per_led_ms = total_ms // TOTAL_LEDS
    led_idx = elapsed_ms // per_led_ms
    flicker_on = ((elapsed_ms // 500) % 2) == 0

    for i, (x, y) in enumerate(LED_FILL_ORDER):
        if i < led_idx:
            display.set_pixel(x, y, 9)
        elif i == led_idx:
            display.set_pixel(x, y, 9 if flicker_on else 0)
        else:
            display.set_pixel(x, y, 0)


def draw_skull_blink(now_ms):
    """超时持续阶段:全屏骷髅 1 Hz 闪烁。"""
    phase_on = ((now_ms // 500) % 2) == 0
    if phase_on:
        display.show(Image.SKULL)
    else:
        display.clear()


def flash_alert():
    """大叉 X 闪 3 次 + 箭头 1 次,期间 alerting=True 阻止其他画图干扰。"""
    global alerting
    alerting = True
    for _ in range(3):
        display.show(Image.NO)
        sleep(300)
        display.clear()
        sleep(200)
    display.show(Image.ARROW_NE)
    sleep(800)
    display.clear()
    alerting = False


def draw_walk_anim(now_ms):
    """小人走路动画:两帧交替切换,每 WALK_FRAME_MS 切一次。"""
    if (now_ms // WALK_FRAME_MS) % 2 == 0:
        display.show(Image.STICKFIGURE)
    else:
        display.show(WALK_FRAME_2)


# ============== 初始化 ==============
pin0.set_pull(pin0.PULL_DOWN)
display.show(Image.YES)
sleep(500)
display.clear()
display.scroll(str(get_threshold()))


# ============== 主循环 ==============
while True:
    now = running_time()
    threshold_min = get_threshold()
    threshold_ms = threshold_min * 60 * 1000

    # 读取引脚并去抖
    sample = 1 if pin0.read_digital() == 1 else 0
    if sample == raw_state:
        same_count += 1
    else:
        raw_state = sample
        same_count = 1
    if same_count >= DEBOUNCE_COUNT and stable_state != raw_state:
        stable_state = raw_state
    occupied = (stable_state == 1)

    # A 键:循环切换阈值(任意时刻都允许)
    if button_a.was_pressed():
        config_idx = (config_idx + 1) % len(THRESHOLDS)
        display.scroll(str(THRESHOLDS[config_idx]))
        reset_progress()
        reset_cooldown()

    # B 键:手动重置(任意时刻都允许)
    if button_b.was_pressed():
        reset_progress()
        reset_cooldown()
        display.show(Image.HAPPY)
        sleep(500)
        display.clear()
        # 滚动显示当前挡位,让用户确认选中哪个阈值
        display.scroll(str(get_threshold()), delay=80)
        display.clear()

    # 大叉期间不画图,让 X 完整闪完
    if occupied and alerting:
        sleep(SAMPLE_MS)
        continue

    if occupied:
        # 用户坐下
        reset_cooldown()    # 坐下立即取消冷却状态
        if sit_start_ms is None:
            sit_start_ms = now

        elapsed_ms = now - sit_start_ms

        if elapsed_ms >= threshold_ms:
            # 超时:X 闪 3 次 + 箭头 + 持续骷髅闪烁
            should_warn = (
                last_warn_ms is None
                or (now - last_warn_ms) >= WARN_REPEAT_MIN * 60 * 1000
            )
            if should_warn:
                flash_alert()
                last_warn_ms = running_time()
                draw_skull_blink(last_warn_ms)
            else:
                draw_skull_blink(now)
        else:
            # 倒计时:画进度条
            draw_progress(now, elapsed_ms, threshold_ms)
    else:
        # 无人坐
        # 只有"超时后站起来"才进入冷却期(走路动画);
        # 未超时就短暂离开,直接清屏等待用户回来,不走冷却流程
        if sit_start_ms is not None or last_warn_ms is not None:
            had_timed_out = last_warn_ms is not None
            # 记录本次实际坐的总时长(坐下到站起的总时间,含超时部分)
            if sit_start_ms is not None:
                actual_sit_ms = now - sit_start_ms
            reset_progress()
            if had_timed_out and stand_start_ms is None:
                # 超时后才站起来 → 进入冷却(时长 = 实际坐的时长 × 20%)
                stand_start_ms = now
            elif not had_timed_out:
                # 未超时就离开 → 不进入冷却
                reset_cooldown()
            display.clear()

        if stand_start_ms is not None:
            cooldown_ms = now - stand_start_ms
            # 冷却时长 = 实际坐的总时长 × 20%
            # 若没有记录到(异常情况),用当前阈值 × 20% 作为兜底
            if actual_sit_ms is not None:
                cooldown_total = int(actual_sit_ms * COOLDOWN_RATIO)
            else:
                cooldown_total = int(threshold_ms * COOLDOWN_RATIO)

            if cooldown_ms < cooldown_total:
                # 冷却期内:显示走路动画
                draw_walk_anim(now)
            else:
                # 冷却结束:保持黑屏,等待用户按 A 键切换阈值或坐下
                # (A/B 键在主循环开头已经处理,这里只需保证屏幕黑)
                display.clear()

    sleep(SAMPLE_MS)