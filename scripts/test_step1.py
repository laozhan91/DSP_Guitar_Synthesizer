import os
import sys

# 确保项目根目录在路径中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dsp_guitar_core.utils import load_wav, plot_waveform, plot_spectrum_with_envelope

if __name__ == "__main__":
    assets_dir = os.path.join(project_root, "assets")
    
    # 1. 获取文件夹中所有的 wav 文件
    wav_files = [f for f in os.listdir(assets_dir) if f.endswith(".wav")]
    
    if not wav_files:
        print(f"未在 '{assets_dir}' 文件夹中找到 wav 文件，请检查路径。")
    else:
        for file_name in wav_files:
            full_path = os.path.join(assets_dir, file_name)
            print(f"\n{'='*50}")
            print(f"正在分析文件: {file_name}")
            print(f"{'='*50}")
            
            try:
                sample_rate, data = load_wav(full_path)
                
                # 如果音频太长，先截取前2秒用于测试
                if len(data) > sample_rate * 2:
                    data = data[:sample_rate * 2]
                
                # 2. 智能截取中间的延音部分，避开开头的拨弦噪音（Attack）
                # 截取第 0.5秒 到 第 1.5秒 之间的片段
                start_time = 0.5 
                end_time = 1.5   
                
                start_index = int(sample_rate * start_time)
                end_index = int(sample_rate * end_time)
                
                if end_index <= len(data):
                    data_slice = data[start_index:end_index]
                    print(f"截取时间段: {start_time}s ~ {end_time}s")
                else:
                    # 如果音频较短，默认截取最后 1 秒作为延音
                    data_slice = data[-sample_rate:]
                    print("音频较短，已自动截取最后 1 秒进行分析。")
                    
                # 3. 绘制切片后的波形和包络
                print("正在绘制波形图...")
                plot_waveform(data_slice, sample_rate)
                
                print("正在绘制带包络线的频谱图...")
                plot_spectrum_with_envelope(data_slice, sample_rate)
                
                print(f"文件 {file_name} 分析完成！")
                
            except Exception as e:
                print(f"处理 {file_name} 时出错: {e}")

    print("\n所有音频文件分析完毕！")