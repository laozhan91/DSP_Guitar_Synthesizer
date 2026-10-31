# DSP 吉他合成器

一个基于 Python + NumPy/SciPy 的吉他拨弦音频合成器，核心采用 **Karplus-Strong 物理建模**算法。

## 项目简介

项目流程分为两个阶段：

1. **频谱包络提取**：从吉他 WAV 中提取「音色指纹」（频谱包络）
2. **拨弦合成**：Karplus-Strong 延迟线算法合成吉他拨弦/扫弦声音，可选琴体 IR 卷积

## 快速开始

```powershell
# 激活虚拟环境（项目自带 .venv，包含 sounddevice / pynput 等依赖）
.venv\Scripts\Activate.ps1

# 默认模式：合成 A_minor 和弦并导出 WAV
python main.py

# 键盘实时演奏
python main.py --play
```

> 全新环境请先安装依赖：`pip install -r requirements.txt`

## 运行方式

| 命令 | 说明 |
|---|---|
| `python main.py` | 默认模式：合成 A_minor 和弦导出 WAV |
| `python main.py --play` | 键盘实时演奏（无 IR） |
| `python main.py --play --ir` | 键盘实时演奏（带短促暖色 IR） |
| `python main.py --extract` | 单独执行频谱包络提取 |
| `python scripts/generate_ks_audio.py` | 生成 KS 合成 WAV（供 A/B 听感对比） |

```powershell
# 演奏模式完整参数示例
python main.py --play --alpha 0.4 --rho 0.995 --ir
```

### 键盘演奏键位

| 按键 | 和弦 |
|---|---|
| `A` | A_minor |
| `S` | C_major |
| `D` | G_major |
| `F` | F_major |

按 `Esc` 退出演奏模式。

## 核心流程

```
┌─────────────────────────────────────────────────────┐
│  阶段一：频谱包络提取（extract_envelope.py）          │
│  吉他 WAV → 截延音段 → FFT → 峰值检测 → 插值包络      │
│        → assets/guitar_envelope_data.npz            │
└─────────────────────────────────────────────────────┘
                          │（当前 KS 模型暂不使用，保留扩展）
                          ▼
┌─────────────────────────────────────────────────────┐
│  阶段二：Karplus-Strong 拨弦合成（synthesizer.py）    │
│  白噪声激励 → 延迟线(N=fs/f0) → 低通(alpha)          │
│        → 增益衰减(rho) → 弦振动信号                  │
│        → [可选] 琴体 IR 卷积(ir) → 归一化           │
└─────────────────────────────────────────────────────┘
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
   WAV 导出（generate_ks_audio.py）  实时演奏（keyboard_controller.py）
```

**演奏模式调用链**：

```
main.py --play [--ir] [--alpha X] [--rho Y]
  └─▶ KeyboardController(use_ir=..., alpha=..., rho=...)
        └─▶ _play_chord() 按键触发
              └─▶ synthesize_ks_chord(freqs, 2.0, alpha=..., rho=..., ir=...)
                    └─▶ synthesize_ks_note() × N（每根弦）
                          └─▶ [整体卷积 IR 一次] → 混音 → 音频流输出
```

## Karplus-Strong 算法原理

Karplus-Strong 是经典的物理建模弦乐合成算法，用一个**循环延迟线**模拟弦的振动。

### 核心思想

1. **激励**：拨弦瞬间弦上激发宽带振动，用一段**白噪声**填充延迟线模拟这一瞬态。
2. **循环**：延迟线中的样本循环流转，模拟弦上行波的来回传播：
   - 延迟线长度 $N = \text{round}(f_s / f_0)$，即一个基频周期，决定音高；
   - 每循环一步，样本经过**低通滤波**，模拟高频能量耗散；
   - 再乘以**增益系数** $\rho$，模拟能量衰减。
3. **输出**：每一步取延迟线当前样本作为输出。

### 一步更新的数学表达

记延迟线当前样本为 $x_i$、下一个样本为 $x_{i+1}$，则：

$$
x_i \leftarrow \rho \cdot \big[(1-\alpha)\,x_i + \alpha\,x_{i+1}\big]
$$

- 方括号内是**相邻两点加权平均**（低通）：$\alpha$ 越大，高频衰减越快，音色越暗；
- $\rho$ 是**增益衰减**：越接近 1，余音越长；
- 更新后指针前移一位，如此循环，直到输出长度满足要求。

### 两个关键参数

| 参数 | 范围 | 作用 | 听感 |
|---|---|---|---|
| `alpha` | 0.0 ~ 1.0 | 低通系数 | 越大越暗，越小越亮 |
| `rho` | 0.0 ~ 1.0 | 增益衰减 | 越接近 1 余音越长 |

> 实现见 `dsp_guitar_core/synthesizer.py` 的 `synthesize_ks_note()`，使用**索引式环形缓冲**做到每采样 O(1)，避免 `np.roll` 的 O(N) 开销。

## 琴体 IR 卷积

### 目的

Karplus-Strong 只建模了**弦**的振动；真实吉他的声音还会经过**琴体共鸣箱**的滤波与共振。IR（Impulse Response，脉冲响应）是琴体对单位冲激的响应，用它卷积可给弦声加上「箱体感」。

### 本项目中的使用方式

- IR 是**可选**的，默认关闭：纯 KS 弦声即最自然的拨弦音色。
- 开关方式：
  - 生成 WAV：`python scripts/generate_ks_audio.py --ir`
  - 键盘演奏：`python main.py --play --ir`
- 实现位置：
  - `synthesize_ks_note(..., ir=None)`：单音合成后可做卷积（保留扩展）
  - `synthesize_ks_chord(..., ir=None)`：**对混好的和弦整体卷积一次**（更符合物理，避免逐弦固定梳状滤波）
- IR 由 `generate_synthetic_ir()` 生成：短促（4ms）、低频为主、快速衰减的合成冲激。

### 调参经验（本项目实测）

| 方案 | 听感 | 结论 |
|---|---|---|
| 纯 KS（无 IR） | 自然拨弦、扫弦感 | ✅ 推荐默认 |
| 4 个离散正弦 IR | 像钢琴/钟声 | ❌ 淘汰 |
| 0.2s 密集模态 IR | 空灵、像混响 | ❌ 淘汰 |
| 4ms 短促低频 IR | 木头暖色、不拖尾 | ✅ 可选 |

## 可调参数

### 1. KS 合成参数（生成 WAV 时命令行可调）

| 参数 | 含义 | 默认值 | 终端调节 |
|---|---|---|---|
| `alpha` | 低通系数，控制亮度（越大越暗） | 0.7 | `--alpha 0.4` |
| `rho` | 增益衰减，控制余音长度（越接近 1 越长） | 0.997 | `--rho 0.995` |
| `chord` | 和弦 | A_minor | `--chord C_major` |
| `duration` | 时长（秒） | 3.0 | `--duration 2.5` |
| `ir` | 琴体 IR 卷积开关 | 关 | `--ir` |

```powershell
python scripts/generate_ks_audio.py --alpha 0.4 --rho 0.995 --chord A_minor --ir
```

### 2. IR 内部参数（`synthesizer.py` 的 `generate_synthetic_ir()` 内，需改代码）

| 参数 | 含义 | 默认值 |
|---|---|---|
| `duration` | IR 时长，越短越不拖尾 | 0.004s |
| `n_modes` | 共振模态数量 | 16 |
| `f_min` / `f_max` | 共振频率范围 | 100 / 1500 Hz |
| 振幅指数 | 低频占比（越小低频越突出） | -0.7 |
| 衰减率 | 400~1200（越大衰减越快） | 400~1200 |

### 3. 演奏模式参数

| 参数 | 含义 | 默认值 | 调节方式 |
|---|---|---|---|
| `ir` | 琴体 IR 开关 | 关 | `--ir` 命令行 |
| `alpha` | 亮度（低通系数） | 0.7 | `--alpha 0.4` 命令行 |
| `rho` | 余音长度 | 0.997 | `--rho 0.995` 命令行 |

## 目录结构

```
DSP_Guitar_Synthesizer/
├── main.py                        # 主入口（命令行分发）
├── config.py                      # 全局配置与路径
├── audio_engine.py                # 核心算法聚合入口
├── requirements.txt               # 依赖清单
├── README.MD                      # 本文件
├── dsp_guitar_core/               # 核心 DSP 包
│   ├── _init_.py                  # 包聚合导出
│   ├── synthesizer.py             # 合成器核心（KS 算法）
│   ├── extract_envelope.py        # 频谱包络提取
│   ├── keyboard_controller.py     # 实时键盘演奏
│   └── utils.py                   # 通用工具（读写/FFT/绘图）
├── scripts/                       # 生成与测试脚本
│   ├── generate_ks_audio.py       # KS 合成 WAV（本轮新增）
│   ├── generate_simulated_guitar.py
│   ├── generate_synthesized_audio.py
│   ├── generate_test_audio.py
│   ├── test_step1.py
│   └── test_step2.py
└── assets/                        # 素材与输出
    ├── *.wav                      # 真实吉他采样
    ├── guitar_envelope_data.npz   # 提取的频谱包络
    ├── simulated_guitar_A_minor.wav
    └── synthesized/               # 合成音频输出
        └── ks_A_minor.wav
```

## 脚本说明

| 脚本 | 用途 |
|---|---|
| `generate_ks_audio.py` | Karplus-Strong 拨弦合成，导出 WAV |
| `generate_simulated_guitar.py` | 生成模拟吉他扫弦 WAV |
| `generate_synthesized_audio.py` | 基于频谱包络合成（旧流程） |
| `generate_test_audio.py` | 生成含泛音的测试音频 |
| `test_step1.py` | 分析 WAV 并画频谱包络图 |
| `test_step2.py` | 对比真实 vs 合成音频频谱 |

## 依赖

```txt
numpy>=1.24.0
scipy>=1.10.0
matplotlib>=3.7.0
sounddevice>=0.4.0   # 实时音频输出
pynput>=1.7.0        # 键盘监听
```
