// Sit Remoter - Stage 3/4/5 合并版
// BLE 连接 + 18 字节状态解析 + 圆环 + 数字 + A/B 反向控制 + 自动重连 + 音频

const SERVICE_UUID = '6e400001-b5a3-f393-e0a9-e50e24dcca9e';
const TX_CHAR_UUID = '6e400003-b5a3-f393-e0a9-e50e24dcca9e';
const RX_CHAR_UUID = '6e400002-b5a3-f393-e0a9-e50e24dcca9e';

const RING_CIRCUM = 2 * Math.PI * 88;  // 圆环周长(对应 r=88)

const THRESHOLDS_MIN = [15, 30, 45, 60];
const STATE_NAMES = ['空闲', '计时中', '超时', '冷却'];

const statusEl  = document.getElementById('status');
const connectBtn = document.getElementById('connect');
const timeEl    = document.getElementById('time');
const threshEl  = document.getElementById('threshold');
const progressEl = document.getElementById('progress');
const btnA      = document.getElementById('btn-a');
const btnB      = document.getElementById('btn-b');
const audio     = document.getElementById('audio');

let bleDevice = null;
let server = null;
let txChar = null;
let rxChar = null;
let reconnectTimer = null;
let lastState = null;
let lastTimeoutAlertAt = 0;

// ============== 解析 18 字节 ==============
function parseState(buf) {
  const dv = new DataView(buf.buffer);
  return {
    state:        dv.getUint8(0),
    thresholdIdx: dv.getUint8(1),
    refTime:      dv.getUint32(2, true),
    sitStart:     dv.getUint32(6, true)  || null,
    lastWarn:     dv.getUint32(10, true) || null,
    standStart:   dv.getUint32(14, true) || null,
    actualSit:    dv.getUint32(18, true) || null,
  };
}

// ============== 渲染 ==============
function fmtMMSS(ms) {
  if (ms < 0) ms = 0;
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function setRing(ratio, color) {
  const offset = RING_CIRCUM * (1 - Math.max(0, Math.min(1, ratio)));
  progressEl.style.strokeDasharray  = String(RING_CIRCUM);
  progressEl.style.strokeDashoffset = String(offset);
  progressEl.style.stroke = color;
}

function render(s) {
  // 派生:本地时钟 + 收到的 ref_time 算"现在"
  // micro:bit running_time() 是开机以来毫秒数(无时钟漂移)
  const localNow = performance.now() + performance.timeOrigin;  // ms since epoch
  const elapsedSincePacket = Date.now() - (s._packetReceivedAt || Date.now());
  const now = s.refTime + elapsedSincePacket;

  let displayText = '';
  let ringRatio = 0;
  let color = '#6cf';

  if (s.state === 1 && s.sitStart) {
    // 计时中
    const elapsed = now - s.sitStart;
    const total = THRESHOLDS_MIN[s.thresholdIdx] * 60 * 1000;
    displayText = fmtMMSS(elapsed);
    ringRatio = elapsed / total;
    statusEl.textContent = `计时中 · 阈值 ${THRESHOLDS_MIN[s.thresholdIdx]} 分钟`;
    statusEl.className = 'timing';
    color = '#6cf';
  } else if (s.state === 2) {
    // 超时
    if (s.sitStart) {
      const elapsed = now - s.sitStart;
      displayText = fmtMMSS(elapsed);
      const total = THRESHOLDS_MIN[s.thresholdIdx] * 60 * 1000;
      ringRatio = elapsed / total;  // 持续增长 > 1,会被 setRing 截到 1
    }
    statusEl.textContent = `超时!阈值 ${THRESHOLDS_MIN[s.thresholdIdx]} 分钟`;
    statusEl.className = 'timeout';
    color = '#f66';

    // 每 5 分钟播放一次报警音(只在刚收到通知时触发一次,而不是每秒)
    if (s.lastWarn && s.lastWarn !== lastTimeoutAlertAt) {
      lastTimeoutAlertAt = s.lastWarn;
      playAlert();
    }
  } else if (s.state === 3 && s.standStart && s.actualSit) {
    // 冷却
    const cooldownTotal = s.actualSit * 0.2;
    const cooldownElapsed = now - s.standStart;
    const remaining = Math.max(0, cooldownTotal - cooldownElapsed);
    displayText = fmtMMSS(remaining);
    ringRatio = cooldownElapsed / cooldownTotal;
    statusEl.textContent = `冷却中 · 还剩 ${Math.ceil(remaining / 1000)} 秒`;
    statusEl.className = 'cooldown';
    color = '#fc6';
  } else {
    // 空闲
    displayText = '00:00';
    ringRatio = 0;
    statusEl.textContent = '空闲';
    statusEl.className = '';
    color = '#6cf';
  }

  timeEl.textContent = displayText;
  setRing(ringRatio, color);
  threshEl.textContent = `阈值: ${THRESHOLDS_MIN[s.thresholdIdx]} 分钟`;
}

// ============== 音频 ==============
function playAlert() {
  if (!audio) return;
  audio.currentTime = 0;
  audio.play().catch(() => {});
}

function unlockAudio() {
  // 用户首次点击时解锁音频自动播放
  audio.volume = 0;
  audio.play().then(() => {
    audio.pause();
    audio.currentTime = 0;
    audio.volume = 1;
  }).catch(() => {});
}

// ============== BLE ==============
async function connect() {
  try {
    unlockAudio();

    bleDevice = await navigator.bluetooth.requestDevice({
      filters: [{ namePrefix: 'BBC micro:bit' }],
      optionalServices: [SERVICE_UUID]
    });

    statusEl.textContent = `已选: ${bleDevice.name},正在连接...`;
    connectBtn.disabled = true;

    bleDevice.addEventListener('gattserverdisconnected', onDisconnected);

    server = await bleDevice.gatt.connect();
    const service = await server.getPrimaryService(SERVICE_UUID);
    txChar = await service.getCharacteristic(TX_CHAR_UUID);
    rxChar = await service.getCharacteristic(RX_CHAR_UUID);

    await txChar.startNotifications();
    txChar.addEventListener('characteristicvaluechanged', (event) => {
      const s = parseState(event.target.value);
      s._packetReceivedAt = Date.now();
      lastState = s;
      render(s);
    });

    statusEl.textContent = `已连接: ${bleDevice.name}`;
    connectBtn.textContent = '断开';
    connectBtn.disabled = false;
  } catch (e) {
    statusEl.textContent = `错误: ${e.name || '未知'}`;
    connectBtn.disabled = false;
  }
}

function onDisconnected() {
  statusEl.textContent = '已断开,5 秒后重连...';
  statusEl.className = '';
  connectBtn.textContent = '手动重连';
  connectBtn.disabled = false;
  txChar = null;
  rxChar = null;
  // 5 秒后自动重连(不需重新 requestDevice,授权仍有效)
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    if (bleDevice) {
      reconnectTimer = null;
      reconnect().catch(() => {});
    }
  }, 5000);
}

async function reconnect() {
  if (!bleDevice) return;
  try {
    server = await bleDevice.gatt.connect();
    const service = await server.getPrimaryService(SERVICE_UUID);
    txChar = await service.getCharacteristic(TX_CHAR_UUID);
    rxChar = await service.getCharacteristic(RX_CHAR_UUID);
    await txChar.startNotifications();
    txChar.addEventListener('characteristicvaluechanged', (event) => {
      const s = parseState(event.target.value);
      s._packetReceivedAt = Date.now();
      lastState = s;
      render(s);
    });
    statusEl.textContent = `已重连: ${bleDevice.name}`;
  } catch (e) {
    // 重连失败,继续等下个 5 秒再试
    onDisconnected();
  }
}

function disconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (bleDevice && bleDevice.gatt.connected) {
    bleDevice.gatt.disconnect();
  }
  bleDevice = null;
  txChar = null;
  rxChar = null;
  statusEl.textContent = '未连接';
  statusEl.className = '';
  connectBtn.textContent = '连接 micro:bit';
  setRing(0, '#6cf');
  timeEl.textContent = '00:00';
}

// ============== 反向控制 ==============
async function sendKey(byte) {
  if (!rxChar) return;
  try {
    await rxChar.writeValue(new Uint8Array([byte]));
  } catch (e) {
    console.error('writeValue failed', e);
  }
}

// ============== 事件绑定 ==============
connectBtn.addEventListener('click', () => {
  if (bleDevice && bleDevice.gatt.connected) {
    disconnect();
  } else {
    connect();
  }
});

btnA.addEventListener('click', () => sendKey(0x41));
btnB.addEventListener('click', () => sendKey(0x42));