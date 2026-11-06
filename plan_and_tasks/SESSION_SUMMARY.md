# 会话总结与明日任务（2026-11-05）

> 本次会话完成了 DSP 吉他合成器的 GUI 前端（任务1 扩展）大部分工作，以及《安和桥》伴奏弹唱流程的搭建。

## 一、本次完成的任务

### 1. GUI 前端骨架（T0/T1）
- 新建 `GUI/` 包：`app.py`（三屏状态机 main→song_select→play）、`app_context.py`、`theme.py`、`visual.py`（`VisualRingBuffer`）、`screens/`
- `main.py` 加 `--gui` 入口；`requirements.txt` 加 `pygame`
- 引擎运行时参数：`set_alpha / set_rho / set_master_gain / enable_ir`（IR 预生成、运行时切换）

### 2. 可视化
- 实时频谱：对数频率轴 + dB 刻度 + 频谱柱上下留空
- STFT 瀑布图：3D 级联瀑布（新切片在顶部、随时间向下流动、越新越亮）

### 3. 主界面（T2）
- IR 开关 + 4 个可拖滑杆（alpha/rho/力度/音量）+ 预设按钮（暖色/明亮/长余音）+「开始演奏」

### 4. 选歌界面（T3）
- Phigros 式滚动列表（缓动居中、选中放大高亮、滚轮/点击/键盘切换）
- 难度切换、P 键试听
- 最终只保留「安和桥」+「自由演奏」

### 5. 乐谱 + 音序器（T4，默认关闭）
- `dsp_guitar_core/sequencer.py`：`load_chart` + `SongSequencer`（样本时钟驱动、回调零分配）
- 自动演奏默认关闭（可选，后续加音频再启用）

### 6. 节奏引擎（P2）
- `dsp_guitar_core/rhythm.py`：`RhythmEngine` 按住和弦自动扫弦（16 分网格）
- 模板：民谣 / 8分 / 16分 / 附点 + 新增「安和桥」（下 下 下上）
- 多键换弦：`_held` 列表跟踪按住的键，松开回落上一个和弦

### 7. 演示动画（G-3）
- 吉他指板面板：和弦指法图 + 六弦振动 + 扫弦方向箭头
- 关键结论：合成器对和弦只发 3 个和弦音（非 6 弦），六弦振动用 GUI 侧拨弦模型

### 8. BGM 分析和弦提取
- `scripts/analyze_bgm.py`：chroma + 模板匹配 + 众数平滑 + onset 自相关测速
- 初步结果：Em / D / G / Bm（G 调）

### 9. 伴奏回调混音
- `AppContext.load_backing / _mix_backing`：伴奏混入输出，但**频谱环形缓冲在混音之前写好** → 频谱只显示自己弹奏的吉他
- 回调末尾 `np.tanh` 软限幅防削波
- 结论：`.ncm`（网易云加密）scipy 读不了，需先转 wav

### 10. 曲目绑定 + 和弦提示 + 进度条
- 选歌绑定 `assets/BGM/<歌名>.wav` + 和弦时间线
- 演奏界面：和弦提示（显示按键字母 A/S/D/F）、底部播放进度条（点击/拖拽跳转 + mm:ss/mm:ss）
- Esc 停止伴奏

### 11. 按用户功能谱重做《安和桥》
- 和弦：G / D / Em / C（键位 **A=Em、S=D、D=G、F=C**）
- 节奏：63 BPM「下 下 下上」
- 时间线：`assets/charts/安和桥_timeline.json`（按 62.5 BPM 功能谱推算的精确时间表，64 段，0.0~245.7s，全部有键位）

## 二、关键文件

| 文件 | 职责 |
|---|---|
| `GUI/app.py` | 屏幕状态机 + 主循环 |
| `GUI/app_context.py` | 引擎/环形缓冲/节奏/伴奏混音/进度 |
| `GUI/screens/play_screen.py` | 演奏界面：频谱+瀑布+吉他指板+和弦提示+进度条 |
| `GUI/screens/song_select.py` | 选歌（安和桥 + 自由演奏）与伴奏绑定 |
| `GUI/screens/main_screen.py` | 调参界面 |
| `dsp_guitar_core/rhythm.py` | 节奏引擎 |
| `dsp_guitar_core/sequencer.py` | 乐谱音序器（可选） |
| `dsp_guitar_core/fingering.py` | 和弦指法数据 |
| `scripts/analyze_bgm.py` / `reanalyze_anheqiao.py` | BGM 和弦/节奏分析 |
| `scripts/build_anheqiao_timeline.py` | 按功能谱生成《安和桥》精确和弦时间线 |
| `plan_and_tasks/TASK_PLAN.md` | 全部任务清单与状态 |

## 三、明日任务清单

- [x] **和弦时间线精确化（重要）**：✅ 已完成（2026-11-06）。用户提供 62.5 BPM 推算时间表，已用 `scripts/build_anheqiao_timeline.py` 生成 `assets/charts/安和桥_timeline.json`（64 段、0.0~245.7s、G/D/Em/C 全部有键位）。如需微调，改脚本里的 `DATA` 表即可。
- [ ] **谱面判定 G-4（可选）**：按键 vs 期望时间窗 → Perfect/Good/Miss + combo + 分数。
- [ ] **T6 收尾（可选）**：README 更新、UI 细节打磨、参数预设微调。
