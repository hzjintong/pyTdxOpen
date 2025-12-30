import os, math, struct
from collections import Counter

def deep_analyze_wdz(file_path, sample_size=10240):
    """
    深度分析WDZ文件结构
    """
    print(f"深度分析文件: {os.path.basename(file_path)}")
    file_size = os.path.getsize(file_path)
    print(f"文件总大小: {file_size:,} 字节\n")

    with open(file_path, 'rb') as f:
        # 1. 计算文件头部区域的熵值 (判断随机性/加密强度)
        data = f.read(min(4096, file_size))
        entropy = calculate_entropy(data)
        print(f"1. 文件头4096字节的熵值: {entropy:.4f}")
        print("   (熵值接近8.0表示高度随机，可能已加密；较低则可能为压缩或未加密文本)\n")

        # 2. 在整个文件采样中寻找可能的固定记录长度
        f.seek(0)
        sample = f.read(min(sample_size, file_size))

        # 寻找重复的间隔模式（启发式方法）
        print("2. 正在分析可能的记录长度...")
        record_lengths = guess_record_length(sample, file_size)
        if record_lengths:
            print(f"   推测的可能记录长度: {record_lengths} 字节")
            # 如果找到候选长度，尝试用其解析几条记录看看
            for rl in record_lengths[:2]:  # 测试前两个候选
                test_record_parsing(file_path, rl)
        else:
            print("   未检测到明显的固定记录长度模式。\n")

        # 3. 在不同偏移量尝试解读为数字，寻找“合理值”
        print("3. 尝试在不同文件偏移处寻找'合理'的数值（如小整数、合理日期）...")
        scan_for_plausible_values(file_path)

def calculate_entropy(data):
    """计算字节数据的香农熵"""
    if not data:
        return 0.0
    counter = Counter(data)
    entropy = 0.0
    total = len(data)
    for count in counter.values():
        p = count / total
        entropy -= p * math.log2(p)
    return entropy

def guess_record_length(sample, file_size, max_len=200):
    """
    通过分析字节样本，猜测固定记录长度。
    原理：寻找使文件大小能整除的、并且在样本中周期性出现差异较小的长度。
    """
    candidates = []
    for length in range(4, max_len + 1, 4):  # 假设记录长度是4的倍数
        if file_size % length == 0:
            # 简单检查：比较样本中每个“记录”第一个字节的方差
            num_records_in_sample = len(sample) // length
            if num_records_in_sample < 2:
                continue
            first_bytes = [sample[i * length] for i in range(num_records_in_sample)]
            variance = sum((b - sum(first_bytes)/len(first_bytes)) ** 2 for b in first_bytes)
            if variance < 10000:  # 阈值，可调整
                candidates.append((length, variance))
    # 按方差排序，返回长度
    candidates.sort(key=lambda x: x[1])
    return [length for length, _ in candidates[:5]]

def test_record_parsing(file_path, record_length):
    """用给定的记录长度尝试解析前几条记录"""
    print(f"\n   尝试用记录长度 {record_length} 解析:")
    with open(file_path, 'rb') as f:
        f.seek(0)
        # 跳过可能存在的文件头（假设前256字节为头）
        f.seek(min(256, os.path.getsize(file_path)))
        for i in range(3):  # 试3条
            record_data = f.read(record_length)
            if not record_data:
                break
            # 尝试解读为多种数字组合
            formats = ['<I', '>I', '<f', '>f', '<d', '>d']
            print(f"     记录{i+1} 前16字节: {record_data[:16].hex()}")
            for fmt in formats:
                try:
                    size = struct.calcsize(fmt)
                    if len(record_data) >= size:
                        val = struct.unpack(fmt, record_data[:size])[0]
                        # 打印“合理”的值
                        if fmt in ['<I', '>I'] and 20000000 < val < 21000000:
                            print(f"       -> 作为{fmt}整数解读: {val} (像日期)")
                        elif fmt in ['<f', '>f'] and 0 < val < 10000:
                            print(f"       -> 作为{fmt}浮点数解读: {val:.2f} (像价格)")
                except:
                    pass

def scan_for_plausible_values(file_path, num_points=10):
    """在文件不同位置采样，解读为整数或浮点数，过滤出看似合理的值"""
    file_size = os.path.getsize(file_path)
    step = file_size // num_points
    with open(file_path, 'rb') as f:
        for i in range(num_points):
            offset = i * step
            f.seek(offset)
            data = f.read(8)  # 读8字节足够尝试多种格式
            for fmt in ['<I', '>I', '<f', '>f']:  # 尝试4种格式
                try:
                    val = struct.unpack(fmt, data[:struct.calcsize(fmt)])[0]
                    # 定义“合理”：整数像日期或小计数，浮点数像价格
                    is_plausible = False
                    if fmt in ['<I', '>I']:
                        if 20170000 < val < 20180000:  # 可能在2017年日期范围内
                            print(f"      在偏移量 {offset:08x} 处: {val} -> 可能为日期 (格式: {fmt})")
                            is_plausible = True
                    elif fmt in ['<f', '>f']:
                        if 0 < val < 10000:  # 合理的股价范围
                            print(f"      在偏移量 {offset:08x} 处: {val:.2f} -> 可能为价格 (格式: {fmt})")
                            is_plausible = True
                except:
                    pass

# 运行分析
file_path = r"G:\D盘备份1\证券股票\分钟数据\wstock_SHSZ_201701_5Min.wdz"
if os.path.exists(file_path):
    deep_analyze_wdz(file_path)
else:
    print("文件不存在。")