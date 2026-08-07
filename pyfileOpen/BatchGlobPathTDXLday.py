# import struct
import os
import glob
import keyboard
from pathlib import Path
from datetime import datetime # , time,timedelta
from MergeTDXday import merge_day_data, read_tdx_day_file, sort_day_time_data, write_tdx_day_file
from MergeTDXLC1 import merge_minute_data, sort_min_time_data, read_tdx_min_file, write_tdx_min_file
from tqdm import tqdm
import concurrent.futures
import threading
# import random
# import sys
# import time as time_module

# 线程安全的计数器
file_counter = 0
counter_lock = threading.Lock()

# 判断按'Esc'键中断处理过程，可保证不破坏文件
def check_for_exit():
    """检查是否按下了退出键"""
    # if keyboard.is_pressed('CTRL+q') or keyboard.is_pressed('esc'):
    try:
        if keyboard.is_pressed('CTRL+q') :
            return True
    except Exception as error:
        # keyboard库在某些环境下可能出错，忽略
        print(f"检查退出键时出错: {error}")
        pass
    return False

# 假设这是您之前写好的合并两个文件的数据函数
def merge_min_data(input_filename, output_filename):
    """
    合并通达信分钟线.lc1或.lc5文件
    :param input_filename: 需要合并的文件路径列表
    :param output_filename: 合并后输出的文件路径
    """
    # 这里填入您之前已经写好的合并逻辑
    # print("正在读取第一个文件...")
    file1_data = read_tdx_min_file(input_filename)

    # print("正在读取第二个文件...")
    file2_data = read_tdx_min_file(output_filename)

    if not file1_data and not file2_data:
        print("文件1、2都没有数据，程序退出")
        return None

    # 合并数据
    # print("正在合并文件1、2数据...")
    merged_data = merge_minute_data(file1_data, file2_data)
    del file1_data, file2_data  # 显式提示内存回收，减轻 3.14t 在多线程下的 GC 压力
    sorted_data = sort_min_time_data(merged_data)
    # 写入合并后的文件
    success = write_tdx_min_file(sorted_data, output_filename)
# -------++++++++=============================================================================++++++++-------
    # 例如：逐个读取input_files中的文件，解析并合并数据，最后也写入input_filename
    # 写入合并后的文件,作为一种备份。
    #print(f"正在写入合并后的数据到输入文件{input_filename}...")
    #success1 = write_tdx_min_file(sorted_data, input_filename)
    #if success1:
    #    print("合并数据文件写入指定 输入 目录完成。")
    #else:
    #    print(f"合并数据文件写入到输入目录 {input_filename} 失败！")
    return success

def merge_lday_data(input_filename, output_filename):
    """
    合并通达信日线.day文件
    :param input_filename: 需要合并的文件路径列表
    :param output_filename: 合并后输出的文件路径
    """
    # 这里填入您之前已经写好的合并逻辑
    # print("正在读取第一个文件...")
    file1_data = read_tdx_day_file(input_filename)

    # print("正在读取第二个文件...")
    file2_data = read_tdx_day_file(output_filename)

    if not file1_data and not file2_data:
        # print("文件1、2都没有数据，程序退出")
        return None

    # 合并数据
    # print("正在合并文件1、2数据...")
    merged_data = merge_day_data(file1_data, file2_data)
    del file1_data, file2_data  # 显式提示内存回收，减轻 3.14t 在多线程下的 GC 压力

    # print("正在做时间排序，并剔除重复数据...")
    sorted_data = sort_day_time_data(merged_data)

    # 例如：逐个读取input_files中的文件，解析并合并数据，最后写入output_filename
    # 写入合并后的文件
    # print("正在写入合并后的文件...")
    success = write_tdx_day_file(sorted_data, output_filename)
# -------++++++++=============================================================================++++++++-------
    # 例如：逐个读取input_files中的文件，解析并合并数据，最后也写入input_filename
    # 写入合并后的文件,作为一种备份。
    #print(f"正在写入合并后的数据到输入文件{input_filename}...")
    #success1 = write_tdx_day_file(sorted_data, input_filename)
    #if success1:
    #    print("合并数据文件写入指定 输入 目录完成。")
    #else:
    #    print(f"合并数据文件写入到输入目录 {input_filename} 失败！")
    return success

# 全局中断标志
interrupt_flag = False
interrupt_lock = threading.Lock()

def set_interrupt_flag(value):
    """设置全局中断标志"""
    global interrupt_flag
    with interrupt_lock:
        interrupt_flag = value

def get_interrupt_flag():
    """获取全局中断标志"""
    global interrupt_flag
    with interrupt_lock:
        return interrupt_flag

def process_min_file_group(args):
    """处理分钟文件组的线程函数"""
    global file_counter
    market, data_type, data_type_path, data_type_path2, filename, files = args

    # 检查是否被中断
    if get_interrupt_flag():
        return 0

    if not files:
        return 0

    input_filename = data_type_path / f"{filename}"
    output_filename = data_type_path2 / f"{filename}"

    try:
        # 在处理过程中定期检查中断标志
        if get_interrupt_flag():
            return 0

        merge_min_data(input_filename, output_filename)

        # 再次检查中断标志
        if get_interrupt_flag():
            return 0

        with counter_lock:
            file_counter += 1
        return 1
    except Exception as e:
        print(f"处理股票 {market}{filename} 时发生错误: {e}")
        return 0

def process_day_file_group(args):
    """处理日线文件组的线程函数"""
    global file_counter
    market, data_type, data_type_path, data_type_path2, filename, files = args

    # 检查是否被中断
    if get_interrupt_flag():
        return 0

    if not files:
        return 0

    input_filename = data_type_path / f"{filename}"
    output_filename = data_type_path2 / f"{filename}"

    try:
        # 在处理过程中定期检查中断标志
        if get_interrupt_flag():
            return 0

        merge_lday_data(input_filename, output_filename)

        # 再次检查中断标志
        if get_interrupt_flag():
            return 0

        with counter_lock:
            file_counter += 1
        return 1
    except Exception as e:
        print(f"处理股票 {market}{filename} 时发生错误：{e}")
        return 0

def batch_merge_vipdoc(vipdoc_root_path, vipdoc_home_path, target_structures):
    """
    批量处理VIPDOC目录下的所有分钟线数据
    :param vipdoc_root_path: VIPDOC的根目录路径，例如 'D:/new_tdx/vipdoc'
    :param vipdoc_home_path: VIPDOC的源目录路径 'D:/new_tdx/vipdoc'
    :param target_structures: VIPDOC目录下的结构,市场目录bj,ds,sh,sz,分类数据目录minline,fzline,lday
    """
    global file_counter
    file_counter = 0  # 重置计数器
    set_interrupt_flag(False)  # 重置中断标志

    vipdoc_path = Path(vipdoc_root_path)
    vipdoc_path2 = Path(vipdoc_home_path)

    # 收集所有需要处理的任务
    min_tasks = []
    day_tasks = []

    # 1. 收集分钟文件处理任务
    for market, data_types in tqdm(target_structures.items(), desc="扫描文件总体进度"):
        # 检查用户是否要中断扫描过程
        if check_for_exit():
            response = input("是否取消扫描文件过程？(y/n): ")
            if response.lower() == 'y':
                print("用户取消扫描操作")
                return file_counter

        market_path = vipdoc_path / market
        market_path2 = vipdoc_path2 / market

        if not market_path.exists():
            print(f"警告：市场目录 {market_path} 不存在，跳过。")
            continue

        if not market_path2.exists():
            print(f"警告：市场目录 {market_path2} 不存在，跳过。")
            continue

        for data_type in data_types:
            data_type_path = market_path / data_type
            data_type_path2 = market_path2 / data_type

            if not data_type_path.exists():
                print(f"警告：数据类型目录 {data_type_path} 不存在，跳过。")
                continue

            if not data_type_path2.exists():
                print(f"警告：数据类型目录 {data_type_path2} 不存在，跳过。")
                continue

            # 处理分钟文件
            if data_type in ['minline', 'fzline']:
                pattern_lc1 = os.path.join(data_type_path, '*.lc[15]')
                file_list_lc1 = glob.glob(pattern_lc1)

                # 按股票代码对文件进行分组
                file_groups = {}
                for file_path in file_list_lc1:
                    filename = os.path.basename(file_path)
                    stock_code = filename

                    if stock_code not in file_groups:
                        file_groups[stock_code] = []
                    file_groups[stock_code].append(file_path)

                # 添加任务到列表
                for filename, files in file_groups.items():
                    if files:
                        min_tasks.append((market, data_type, data_type_path, data_type_path2, filename, files))

            # 处理日线文件
            elif data_type == 'lday':
                pattern_lday = os.path.join(data_type_path, '*.day')
                file_list_day = glob.glob(pattern_lday)

                # 按股票代码对文件进行分组
                file_groups = {}
                for file_path in file_list_day:
                    filename = os.path.basename(file_path)
                    stock_code = filename

                    if stock_code not in file_groups:
                        file_groups[stock_code] = []
                    file_groups[stock_code].append(file_path)

                # 添加任务到列表
                for filename, files in file_groups.items():
                    if files:
                        day_tasks.append((market, data_type, data_type_path, data_type_path2, filename, files))

    print(f"找到 {len(min_tasks)} 个分钟文件处理任务和 {len(day_tasks)} 个日线文件处理任务")

    # 因为涉及多个市场，bj, ds, sh, sz 等多个市场。不同市场的文件大小差异巨大（比如沪深 vs 北交所）
    # 打乱任务顺序。这样可以避免程序在某一段时间集中处理一堆超大文件，导致某些线程空转等待，让 CPU 负载更平滑
    # random.shuffle(min_tasks)
    # random.shuffle(day_tasks)

    # 询问用户是否开始处理
    if min_tasks or day_tasks:
        print("按 Ctrl+Q 可以随时中断处理过程")
        response = input("是否开始处理文件？(y/n): ")
        if response.lower() != 'y':
            print("用户取消处理操作")
            return file_counter

    # 2. 使用线程池并行处理任务
    # Gemini建议 2：针对双核 CPU 和 3.14t 调整线程数
    # 你的 i3-5010U 有 4 个逻辑核心，建议 4-6 个线程
    # max_workers = os.cpu_count() + 1
    max_workers = min(48, (os.cpu_count() or 1) * 4)  # 根据i7 CPU核心数设置线程数，最小32测试过
    # max_workers = 24  # 根据i7 CPU核心数设置线程数 24

    # 处理分钟文件
    user_interrupted = False  # 将变量声明移到if语句外部

    if min_tasks:
        print(f"开始并行处理分钟文件，使用 {max_workers} 个线程...")

        success_count = 0
        fail_count = 0

        # 使用可中断的线程池
        with tqdm(total=len(min_tasks), desc="处理分钟文件进度") as pbar:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                futures = [executor.submit(process_min_file_group, task) for task in min_tasks]

                try:
                    # 处理已完成的任务，同时检查用户中断
                    for future in concurrent.futures.as_completed(futures):
                        # 检查用户是否要中断
                        if check_for_exit():
                            response = input("是否取消处理分钟文件？(y/n): ")
                            if response.lower() == 'y':
                                print("用户取消分钟文件处理操作")
                                user_interrupted = True
                                set_interrupt_flag(True)  # 设置全局中断标志
                                # 强制关闭线程池
                                executor.shutdown(wait=False, cancel_futures=True)
                                break

                        try:
                            # 设置超时，防止单个任务卡死（每个任务最多5分钟）
                            result = future.result(timeout=300)
                            if result == 1:
                                success_count += 1
                            else:
                                fail_count += 1
                            pbar.update(1)
                        except concurrent.futures.TimeoutError:
                            print(f"\n警告：某个分钟文件处理任务超时（超过5分钟），已跳过")
                            fail_count += 1
                            pbar.update(1)
                        except concurrent.futures.CancelledError:
                            # 任务被取消
                            pbar.update(1)
                            continue
                        except Exception as e:
                            print(f"\n处理任务时发生错误: {e}")
                            fail_count += 1
                            pbar.update(1)

                except KeyboardInterrupt:
                    print("\n收到中断信号，正在终止程序...")
                    user_interrupted = True
                    set_interrupt_flag(True)  # 设置全局中断标志
                    executor.shutdown(wait=False, cancel_futures=True)

        if user_interrupted:
            print(f"分钟文件处理已中断：成功 {success_count} 个，失败 {fail_count} 个")
            # 重置中断标志
            set_interrupt_flag(False)
            user_interrupted = False
            # 立即返回，不继续处理日线文件
            # return file_counter # 不返回继续询问是否处理日线文件
        else:
            print(f"分钟文件处理完成：成功 {success_count} 个，失败 {fail_count} 个")

    # 如果分钟文件处理被中断，询问是否继续处理日线文件
    if day_tasks and not user_interrupted:
        print("\n" + "="*60)
        print(f"分钟文件处理已完成！接下来还有 {len(day_tasks)} 个日线文件待处理。")
        print("="*60)
        print("【注意】程序正在等待您的输入确认...")
        print("如果没有任何反应，请在下方输入 y 或 n 后按回车键")
        print("="*60)
        response = input("是否继续处理日线文件？(y/n): ")
        if response.lower() != 'y':
            print("用户取消日线文件处理")
            return file_counter
        print("="*60)
        print("开始处理日线文件...")
        print("="*60)

    # 处理日线文件
    if day_tasks and not user_interrupted:
        print(f"开始并行处理日线文件，使用 {max_workers} 个线程...")
        print(f"共 {len(day_tasks)} 个日线文件任务")
        success_count = 0
        fail_count = 0

        with tqdm(total=len(day_tasks), desc="处理日线文件进度") as pbar:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                futures = [executor.submit(process_day_file_group, task) for task in day_tasks]

                try:
                    # 处理已完成的任务，同时检查用户中断
                    for future in concurrent.futures.as_completed(futures):
                        # 检查用户是否要中断
                        if check_for_exit():
                            response = input("是否取消处理日线文件？(y/n): ")
                            if response.lower() == 'y':
                                print("用户取消日线文件处理操作")
                                user_interrupted = True
                                set_interrupt_flag(True)  # 设置全局中断标志
                                # 强制关闭线程池
                                executor.shutdown(wait=False, cancel_futures=True)
                                break

                        try:
                            # 设置超时，防止单个任务卡死（每个任务最多5分钟）
                            result = future.result(timeout=300)
                            if result == 1:
                                success_count += 1
                            else:
                                fail_count += 1
                            pbar.update(1)
                        except concurrent.futures.TimeoutError:
                            print(f"\n警告：某个日线文件处理任务超时（超过5分钟），已跳过")
                            fail_count += 1
                            pbar.update(1)
                        except concurrent.futures.CancelledError:
                            # 任务被取消
                            pbar.update(1)
                            continue
                        except Exception as e:
                            print(f"\n处理任务时发生错误: {e}")
                            fail_count += 1
                            pbar.update(1)

                except KeyboardInterrupt:
                    print("\n收到中断信号，正在终止程序...")
                    user_interrupted = True
                    set_interrupt_flag(True)  # 设置全局中断标志
                    executor.shutdown(wait=False, cancel_futures=True)

        if user_interrupted:
            print(f"日线文件处理已中断：成功 {success_count} 个，失败 {fail_count} 个")
        else:
            print(f"日线文件处理完成：成功 {success_count} 个，失败 {fail_count} 个")

    # 重置中断标志
    set_interrupt_flag(False)
    return file_counter

# 使用示例
def main():
    tdx_vipdoc_dir = "D:/new_hxzq_hc/vipdoc"  # 请修改为您的通达信VIPDOC实际路径
    taget_vipdoc_path = 'F:/D盘备份1/new_hxzq_hc/vipdoc' # 请修改为您的其他数据的实际路径
    # 键：市场目录名 (e.g., 'sh', 'sz')
    # 值：一个列表，包含要处理的数据类型子目录名 (e.g., 'minline', 'fzline', 'lday')
    path_structures = {
        'bj': ['minline', 'fzline', 'lday'],
        'ds': ['minline', 'fzline', 'lday'],
        'sh': ['minline', 'fzline', 'lday'],
        'sz': ['minline', 'fzline', 'lday']
        # 如果您还有其他市场，例如北京交易所('bj')，可以在这里添加
    }

    print(f"读取数据目录： {tdx_vipdoc_dir} ， 并入数据的目标目录：{taget_vipdoc_path} 。")
    response = input("是否确认执行上述两个目录数据的合并、融合与清洗(y/n): ")
    if response.lower() != 'y':
        print("用户取消了操作，程序退出。")
        return False

    try:
        # 为计算整体作业所花费的时间，先记录开始作业的时间
        begin_time = datetime.now()
        file_op_num = batch_merge_vipdoc(tdx_vipdoc_dir, taget_vipdoc_path, path_structures)
        end_time = datetime.now()
        print("\n" + "="*60)
        print(f"✅ 所有处理已完成！共处理了 {file_op_num} 个文件。")
        print("="*60)
        delta_time = abs( end_time - begin_time )
        print(f"处理开始时间 {begin_time.strftime('%Y/%m/%d %H:%M')}，结束时间 {end_time.strftime('%Y/%m/%d %H:%M:%S')}, 共用时 { delta_time }")
        print("="*60)
        print("程序即将正常退出...")
        print("="*60)
    except Exception as er:
        print(f"❌ 文件处理异常，错误为：{er}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()