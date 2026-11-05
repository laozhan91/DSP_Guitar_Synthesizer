# DSP 吉他合成器 — 进度总结与后续任务清单

> 本文件供「新开对话」接力开发使用。**开始动手前请先通读全文**，尤其第 2 节「关键实现事实与坑」，避免臆测产生幻觉。

---

## 0. 项目环境（事实）

- 项目根目录：`c:\Users\12628\Desktop\DSP_Guitar_Synthesizer`
- Python 解释器（venv）：`c:/Users/12628/Desktop/DSP_Guitar_Synthesizer/.venv/Scripts/python.exe`（Python 3.13.13）
- 运行命令（PowerShell）：
  - `python main.py` —— 默认离线合成 A_minor 导出 WAV
  - `python main.py --play [--ir] [--alpha X] [--rho Y]` —— 键盘实时演奏
  - `python scripts/test_streaming.py` —— 无头流式合成测试（统计 xrun / CPU 负载）
- 依赖（`requirements.txt`）：numpy、scipy、matplotlib、sounddevice、pynput
- 平台：Windows / PowerShell

---

## 1. 当前进度总结（已完成）

### 已完成的 P0：流式实时合成

把「按键时一次性合成 2 秒完整 buffer 再播放」升级为「每根弦 KS 延迟线状态常驻音频回调、逐块推进」。

### 文件清单与职责（当前真实状态）

| 文件 | 职责 |
|---|---|
| `dsp_guitar_core/synthesizer.py` | 离线 KS 合成：`Synthesizer` 类、`synthesize_ks_note()`、`synthesize_ks_chord()`、`get_chord_frequencies()`、`CHORD_FREQUENCIES`、`OPEN_STRING_FREQUENCIES`（空弦 EADGBE）、`generate_synthetic_ir()` |
| `dsp_guitar_core/streaming_synth.py` | 流式引擎：`KSVoice`（单弦状态）、`StreamingGuitarSynth`（事件队列 + 逐块渲染） |
| `dsp_guitar_core/performance.py` | 演奏状态机：`PerformanceStateMachine`、`StrumCommand`、`MuteCommand`、`OPEN_GROUP = '__open__'` |
| `dsp_guitar_core/keyboard_controller.py` | `KeyboardController`：监听键盘 → 状态机 → 引擎 |
| `config.py` | 全局参数与路径 |
| `scripts/test_streaming.py` | 无头流式测试 |
| `README.MD` | 已同步更新 |

### 实时演奏数据流（准确链路）

```
键盘事件 → PerformanceStateMachine（handle_chord_press / handle_chord_release / handle_strum）
        → StrumCommand / MuteCommand
        → StreamingGuitarSynth.strum() / .mute()（只投递到事件队列，加锁 O(1)）
        → 音频回调 process(outdata, frames)：drain 队列 → _do_strum/_do_mute → KSVoice.render() 混音 → 软限幅 → 输出
```

### 演奏交互（已确认的键位语义）

| 操作 | 语义 |
|---|---|
| 左手 `A`/`S`/`D`/`F` 按下 | 按住和弦（A_minor / C_major / G_major / F_major），**不发声** |
| 左手松开 | 制音（该和弦余音快速衰减） |
| 右手 `.` | 下扫（低音弦先响 → 高音弦） |
| 右手 `,` | 上扫（高音弦先响 → 低音弦） |
| 未按和弦时按 `.` / `,` | 扫空弦（标准调弦 EADGBE） |
| 力度 | 固定 `config.DEFAULT_VELOCITY = 0.6` |

- `KEY_CHORD_MAP = {'a':'A_minor','s':'C_major','d':'G_major','f':'F_major'}`（`keyboard_controller.py`）
- `STRUM_UP_CHAR = ','`，`STRUM_DOWN_CHAR = '.'`（直接按，无需 Shift）
- 扫弦键与字母键都做了 `pressed_keys` 防连发（按一下触发一次）。

---

## 2. 关键实现事实与坑（防幻觉，务必遵守）

1. **KS 的 `rho` 是「每周期」衰减**（每 N 个样本乘一次），不是每样本。`rho=0.997` 余音约数秒，属正常。
2. **`KSVoice.render()` 是块级 numpy 向量化**，与逐样本递推**逐点等价**。实现时每段处理 `step = min(frames-done, n-idx)`，且**必须 `step <= n-1`**（若恰好等于 n 走完整圈，最后一个样本的「下一位置」会读到本段已写回的首元素，导致不等价）。
3. **高音弦 `n_delay` 可能小于 `blocksize`**（如 E4=329.6Hz → n=134 < 256），`render()` 必须按段循环处理跨圈情况。
4. **回调内禁止动态分配 numpy 数组**：`KSVoice` 预分配 `_seg`/`_seg_next`（各 4096）；引擎预分配混音缓冲 `_buf`（4096）；声部淘汰用倒序原地 `pop`。
5. **声部上限 `MAX_VOICES = 48`**（`config.py`）：超出按 `voice.energy` 淘汰最安静的声部。
6. **声部能量判断**：`render()` 里用 `float(np.dot(delay, delay)) / n`（整条延迟线能量，与块相位无关）。低于 `VOICE_ENERGY_THRESHOLD = 1e-5`（约 -50dB）即回收。
7. **线程模型**：按键线程只投命令（`strum()`/`mute()` 内 `self._lock` 保护 deque），DSP 全部在音频回调线程的 `process()` 里执行；`process()` 里先锁内 `list(self._queue)` + `clear()`，再锁外执行命令与渲染。
8. **pynput 的 `key.char` 不含 Shift 修饰**，故扫弦键已改为直接按 `,` / `.`（不再用 Shift+`<`/`>`）。
9. **实时路径不经过离线函数**：演奏用 `streaming_synth.py`，`synthesize_ks_chord()` / `synthesize_ks_note()` 只用于离线导出（`main.py` 默认模式、`scripts/generate_ks_audio.py`）。
10. **等价性验证方法**：改 KS 递推后，必须用「向量化 render 输出 vs 逐样本参考」逐点对比（差异应为 0.0），参考 `scripts/test_streaming.py` 之外的验证写法；高频弦（n<blocksize）也要覆盖。
11. **IR 实时实现**：`StreamingGuitarSynth.process()` 里用 `scipy.signal.lfilter(self._ir, [1.0], buf, zi=self._zi)` 分块 FIR（`self._zi` 长度 = `len(ir)-1`）；**回调内不要用 `fftconvolve`**。

---

## 3. 后续任务清单（按推荐优先级）

### 任务 1：实时频谱可视化（`--spectrum`）—— 最推荐，最贴 DSP

- **目标**：演奏时实时滚动显示频谱 / 语谱图（STFT），加 CLI 参数 `--spectrum`。
- **涉及文件**：`main.py`（加参数）、新建 `dsp_guitar_core/spectrum_display.py`（或并入 `keyboard_controller.py`）、`config.py`（FFT 参数）。
- **实现要点**：
  - 音频回调把每块输出写入预分配的环形缓冲（numpy 数组 + 写指针），**不阻塞回调**。
  - 单独绘图线程每隔 ~50–100ms 取一段做 `scipy.signal.stft` 或 `numpy.fft.rfft`，刷新图（`matplotlib.animation.FuncAnimation`；若允许加依赖，`pyqtgraph` 更流畅）。
  - 展示 FFT、窗函数、STFT、dB 刻度。
- **验收**：`python main.py --play --spectrum` 弹奏时频谱实时滚动，音频仍 0 xrun。

### 任务 2：P3 琴体 IR 深化 —— DSP 含量最高

- **目标**：真实/更长 IR 载入 + 演奏模式短 IR 保延迟 + 幅频/相频响应图。
- **涉及文件**：`synthesizer.py`（新增 `load_ir_wav(path)`，用 `scipy.io.wavfile` 读单声道 float32、归一化、可截断）、`streaming_synth.py`（IR 已接 `lfilter`，检查 `self._zi` 初值正确性）、`config.py`（IR 路径/长度上限）、新增脚本画频响图。
- **实现要点**：
  - 演奏模式 IR ≤ 2048 点（约 46ms @ 44.1k）保低延迟；离线导出可用长 IR。
  - 频响图：`numpy.fft.rfft(ir)` 画幅度（dB）+ 相位，合成 IR vs 真实 IR 对比。
- **验收**：开 IR 后音色更「木箱」，演奏无感知延迟；有频响对比图。

### 任务 3：P2 节奏引擎 —— 性价比高

- **目标**：扫弦方向（已有雏形）、节奏模板（8 分 / 16 分 / 附点）、力度→激励幅度、亮度→`alpha`。
- **涉及文件**：`streaming_synth.py`（`_do_strum` 已按方向排序）、`performance.py`（新增节奏模板，如 `RhythmPattern`）、`keyboard_controller.py`（按键语义：一次按键触发一串扫弦）。
- **实现要点**：
  - 扫弦方向已实现：`_do_strum` 里 `sorted(freqs, reverse=(direction=='up'))`（上扫高音先、下扫低音先）。
  - 节奏模板：定义时值序列，按 BPM 换算成样本偏移，一次按键按模板错位触发多根弦/多次扫。
  - 力度：`StrumCommand.velocity` 已存在，经 `KSVoice.excite()` 的 `EXCITE_GAIN * velocity` 生效。
  - 亮度：`alpha` 目前是引擎全局参数；若要 per-strum，`KSVoice` 已存 `self.alpha`，可让 `StrumCommand` 携带 alpha。
- **验收**：按节拍敲 `.`/`,` 能扫出有节奏、上下交替的伴奏。

### 任务 4：P1 和弦引擎（可选，乐理向）

- **目标**：转位/把位（同一和弦多种按法）+ voice leading（就近换把）+ 和弦进行状态机。
- **涉及文件**：`synthesizer.py`（`get_chord_frequencies` 扩展转位）、`performance.py`（新增 `ChordProgression`，按 BPM/拍自动切换）。
- **验收**：给定进行（Am–F–C–G）与速度，左手自动在正确时机换和弦，相邻和弦听感连贯。

### 任务 5：P4 半自动吉他 Demo（集成）

- **目标**：组合 P1–P3，产出 `main.py --demo`（实时）+ `scripts/generate_demo.py`（离线导出 WAV）。
- **涉及文件**：`main.py`、`scripts/generate_demo.py`（可参考 `scripts/generate_ks_audio.py` 的离线导出写法）。
- **验收**：一键演示「自动伴奏吉他」。

### 任务 6：ML 包络估计 vs 经典方法对照（加分项）

- **目标**：用 ML（如线性回归/SVR/小网络）估计频谱包络，与现有经典方法（`utils.py` 的 `extract_envelope`：峰值检测 + 插值 + 平滑）做 A/B 对比。
- **涉及文件**：新增 `scripts/` 下脚本。
- **验收**：对比图 + 结论（ML 更平滑 or 经典已够好）。
- **注意**：定位为「对照项」，不要喧宾夺主；DSP 大作业评分更看重 FFT/滤波/卷积/包络等经典 DSP 的正确理解。

---

## 4. 开发约定（改代码前必读）

1. 音频回调内禁止动态分配 numpy 数组、禁止 `fftconvolve`；IR 用 `lfilter` 保持状态。
2. 按键线程只投事件，DSP 全在回调线程。
3. 改 `KSVoice.render()` 后，必须做「向量化 vs 逐样本逐点等价」验证（含高音弦 n < blocksize 的情况）。
4. 每次改完跑 `python scripts/test_streaming.py`，确认 0 xrun。
5. 新功能加 CLI 参数优先，避免破坏现有 `--play/--ir/--alpha/--rho/--extract` 行为。
