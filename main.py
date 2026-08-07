# sitdetecter - 久坐提醒器 (MicroPython for micro:bit)
# 版本:v1.0.0(单机版)
# 硬件：薄膜压力座椅传感器 (DJ7021-5.3-11, 常开型)
# 接线：传感器红线 → 3.3V，黑线 → P0；P0 启用内部下拉电阻
# 按键：A 键循环切换阈值（15/30/45/60 分钟），B 键手动重置
# 显示：5x5 LED 接力式进度条（总时长均分到 25 颗，每颗持续闪烁 N 次后转常亮）+ 超时骷髅闪烁 + 站立后小人走路动画

# 版本号(语义化版本 SemVer:主版本.次版本.修订号)
VERSION = "1.0.0"
EDITION = "单机版"

from microbit import (
    pin1,
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
LEAVE_TOLERANCE_MS = 30000      # 短暂离开容差：30 秒内回来算还在坐,累加计时接续
                                # 超过 30 秒才认为真的离开,清空 sit_start_ms

# ============== 进度条 ==============
LED_FILL_ORDER = [(x, y) for y in range(4, -1, -1) for x in range(5)]
TOTAL_LEDS = 25

# ============== 状态 ==============
config_idx = 2                  # 默认 45 分钟(THRESHOLDS 索引 2)
sit_start_ms = None             # 本次坐下起始时刻
last_warn_ms = None             # 上次大叉提醒时刻
stand_start_ms = None           # 用户站起来(开始冷却)的时刻
actual_sit_ms = None            # 本次坐下实际坐的总时长(用于计算冷却 = 实际坐 × 20%)
leave_start_ms = None           # 短暂离开的开始时刻;超过 LEAVE_TOLERANCE_MS 才视为真离开
frozen_elapsed_ms = None        # 短暂离开时的进度快照(已坐多久);离开期间保持不变
raw_state = 0                   # 当前原始读数 (0=无人, 1=有人)
stable_state = 0                # 去抖后的稳定状态
same_count = 0                  # 连续相同采样次数
alerting = False                # 是否处于大叉强提醒期间

# ============== 自定义图像 ==============
# 走路动画第二帧(STICKFIGURE + 双脚左右分开)
WALK_FRAME_2 = Image("09090:90909:90909:09090:09090")
WALK_FRAMES = (Image.STICKFIGURE, WALK_FRAME_2)
WALK_FRAME_COUNT = len(WALK_FRAMES)


def get_threshold():
    return THRESHOLDS[config_idx]


def reset_progress():
    """坐下或离开时清空计时状态。"""
    global sit_start_ms, last_warn_ms, leave_start_ms, frozen_elapsed_ms
    sit_start_ms = None
    last_warn_ms = None
    leave_start_ms = None
    frozen_elapsed_ms = None


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
    - 闪烁相位取墙钟 now_ms,所以短暂离开冻结进度时当前那颗 LED 仍按 1 Hz 闪烁
    """
    if elapsed_ms >= total_ms:
        for x, y in LED_FILL_ORDER:
            display.set_pixel(x, y, 9)
        return

    per_led_ms = total_ms // TOTAL_LEDS
    led_idx = elapsed_ms // per_led_ms
    flicker_on = ((now_ms // 500) % 2) == 0

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
    """小人走路动画:两帧交替,每 WALK_FRAME_MS 切一次。"""
    idx = (now_ms // WALK_FRAME_MS) % WALK_FRAME_COUNT
    display.show(WALK_FRAMES[idx])


# ============== 初始化 ==============
pin1.set_pull(pin1.PULL_DOWN)
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
    sample = 1 if pin1.read_digital() == 1 else 0
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
            # 首次坐下 OR 真离开后重新坐下 → 重新开始计时
            sit_start_ms = now
        elif leave_start_ms is not None:
            # 短暂离开后回来 → 把离开时长补偿掉,保持累计计时连续
            pause_ms = now - leave_start_ms
            sit_start_ms += pause_ms
            leave_start_ms = None

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
        # 区分"短暂离开"(容差内)和"真离开"
        # - 未超时 + 短暂离开:画面冻在离开瞬间,等用户回来接续
        # - 已超时 + 任何离开:立即进冷却,显示走路动画
        #   (只要人起来了,就不再纠缠他,让他走起来休息)
        # - 真离开:走原有 reset_progress / 冷却流程
        if sit_start_ms is not None or last_warn_ms is not None:
            had_timed_out = last_warn_ms is not None
            leave_dur = None
            if sit_start_ms is not None and leave_start_ms is None:
                # 刚从坐下进入离开状态:记下离开起点,顺便冻结当前已坐时长
                # (只对未超时场景有意义;已超时场景立刻走冷却,稍后会被真离开分支清掉)
                leave_start_ms = now
                if not had_timed_out:
                    frozen_elapsed_ms = now - sit_start_ms
            if leave_start_ms is not None:
                leave_dur = now - leave_start_ms

            # 已超时 → 不走短暂离开,立刻当真离开处理(进冷却)
            is_short = (
                not had_timed_out
                and leave_dur is not None
                and leave_dur < LEAVE_TOLERANCE_MS
            )

            if is_short:
                # 未超时 + 短暂离开:用冻结的 elapsed,画面"冻在"离开瞬间那颗 LED
                draw_progress(now, frozen_elapsed_ms, threshold_ms)
            else:
                # 真离开(含已超时后任何站起):走原有清理 + 冷却流程
                if sit_start_ms is not None:
                    actual_sit_ms = now - sit_start_ms
                reset_progress()
                if had_timed_out and stand_start_ms is None:
                    stand_start_ms = now
                elif not had_timed_out:
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