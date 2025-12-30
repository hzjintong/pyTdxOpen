import struct, os, math
from collections import Counter


def analyze_binary_patterns(file_path):
    """
    核心分析函数：通过统计和模式匹配，寻找二进制文件中的固定记录长度和规律。
    """
    print(f"🔍 开始对文件进行二进制模式分析: {os.path.basename(file_path)}")
    print("=" * 70)

    file_size = os.path.getsize(file_path)
    print(f"文件大小: {file_size:,} 字节")

    # 1. 读取文件进行分析
    with open(file_path, 'rb') as f:
        # 读取文件中部的一大块数据进行分析，避免文件头尾特殊结构的干扰
        sample_offset = min(1024, file_size // 10)  # 跳过可能较长的文件头
        f.seek(sample_offset)
        sample_data = f.read(min(1024 * 1024, file_size - sample_offset))  # 最多分析1MB

    print(f"分析样本: 从偏移 {sample_offset:,} 开始，共 {len(sample_data):,} 字节\n")

    # 2. 寻找可能的记录长度（关键步骤）
    print("2. 分析可能的固定记录长度...")
    candidate_lengths = find_record_length_candidates(sample_data)

    if not candidate_lengths:
        print("   ❌ 未检测到明显的固定记录长度。文件可能无固定结构或被深度混淆。")
        return None

    print(f"   ✅ 发现 {len(candidate_lengths)} 个候选记录长度:")
    for length, score in candidate_lengths[:5]:  # 显示前5个最佳候选
        record_count = len(sample_data) // length
        print(f"     候选: {length:3d} 字节 | 得分: {score:.2f} | 样本内约 {record_count} 条记录")

    best_length = candidate_lengths[0][0]
    print(f"\n   🎯 将优先分析最佳候选: {best_length} 字节\n")

    # 3. 基于最佳记录长度，进行详细结构分析
    print("3. 基于候选记录长度进行结构分析...")
    analyze_records_with_length(file_path, sample_offset, best_length, sample_data)

    return best_length


def find_record_length_candidates(data, max_len=200):
    """
    通过分析数据自相关性来寻找可能的固定记录长度。
    原理：如果记录长度固定为L，那么偏移0和偏移L的字节在统计上会比其他偏移更相似。
    """
    candidates = []
    search_range = min(max_len, len(data) // 2)

    for L in range(4, search_range + 1, 2):  # 假设记录长度是偶数
        if L < 8:  # 跳过太小的长度
            continue

        # 计算自相关分数：比较偏移0和偏移L开始的多个字节
        correlation = 0
        compare_positions = min(20, L)  # 在每个记录开头比较多个位置
        num_records_to_check = min(50, len(data) // L)

        for i in range(compare_positions):
            byte_positions = []
            for rec in range(num_records_to_check):
                pos = rec * L + i
                if pos < len(data):
                    byte_positions.append(data[pos])

            # 计算这些字节的“一致性”分数（值越集中，分数越高）
            if byte_positions:
                byte_counts = Counter(byte_positions)
                most_common_count = byte_counts.most_common(1)[0][1]
                correlation += most_common_count / len(byte_positions)

        avg_correlation = correlation / compare_positions if compare_positions > 0 else 0

        # 额外的检查：记录边界处是否有规律（例如很多0x00）
        boundary_zero_ratio = 0
        for rec in range(1, num_records_to_check):
            boundary_pos = rec * L
            if boundary_pos < len(data):
                if data[boundary_pos] == 0 or data[boundary_pos - 1] == 0:
                    boundary_zero_ratio += 1
        boundary_zero_ratio /= (num_records_to_check - 1) if num_records_to_check > 1 else 1

        # 综合得分
        final_score = avg_correlation * 0.7 + boundary_zero_ratio * 0.3

        if final_score > 0.25:  # 经验阈值
            candidates.append((L, final_score))

    # 按得分排序
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates


def analyze_records_with_length(file_path, start_offset, record_length, sample_data):
    """
    假设记录为指定长度，进行详细分析。
    """
    # 将样本数据切分为记录
    num_records = len(sample_data) // record_length
    records = [sample_data[i * record_length:(i + 1) * record_length] for i in range(min(20, num_records))]

    print(f"   分析前 {len(records)} 条记录的结构:\n")

    # a. 显示每条记录的前16字节，观察规律
    print("   a. 记录头部字节模式:")
    for i, rec in enumerate(records[:5]):
        hex_str = ' '.join(f'{b:02x}' for b in rec[:16])
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in rec[:16])
        print(f"      记录{i + 1}: {hex_str}  |  {ascii_str}")

    # b. 分析特定位置的字节值（例如，假设前4字节可能是日期）
    print(f"\n   b. 分析前4字节作为日期字段的可能性:")
    for i, rec in enumerate(records[:5]):
        if len(rec) >= 4:
            # 尝试以小端序和大端序解读为整数
            as_le = struct.unpack('<I', rec[:4])[0]
            as_be = struct.unpack('>I', rec[:4])[0]

            # 应用通达信公式（假设这是日期编码）
            for val, order in [(as_le, '小端'), (as_be, '大端')]:
                year = (val // 2048) + 2004
                md = val % 2048
                month = md // 100
                day = md % 100
                # 仅打印看起来合理的日期
                if 2004 <= year <= 2030 and 1 <= month <= 12 and 1 <= day <= 31:
                    print(f"      记录{i + 1} [{order}]: 原始值 {val} -> {year:04d}-{month:02d}-{day:02d}")

    # c. 分析记录中哪些位置经常是0（可能是填充或空字段）
    print(f"\n   c. 分析记录中的常零字节位置（可能为字段分隔）:")
    zero_positions = []
    for pos in range(min(record_length, 32)):
        zero_count = sum(1 for rec in records if pos < len(rec) and rec[pos] == 0)
        if zero_count > len(records) * 0.8:  # 80%以上的记录在该位置为0
            zero_positions.append(pos)
    if zero_positions:
        print(f"      常零位置: {zero_positions} (可能为预留字段或整数0)")
    else:
        print("      未发现明显的常零位置")

    # d. 尝试将记录解读为一系列短整数(2字节)或单精度浮点数(4字节)
    print(f"\n   d. 将记录解读为短整数(2字节)序列:")
    for i, rec in enumerate(records[:2]):
        shorts = []
        for j in range(0, min(16, len(rec)), 2):
            if j + 2 <= len(rec):
                short_val = struct.unpack('<H', rec[j:j + 2])[0]
                shorts.append(short_val)
        print(f"      记录{i + 1} 前{len(shorts)}个短整型: {shorts}")

    print(f"\n   e. 将记录解读为单精度浮点数(4字节)序列:")
    for i, rec in enumerate(records[:2]):
        floats = []
        for j in range(0, min(16, len(rec)), 4):
            if j + 4 <= len(rec):
                try:
                    float_val = struct.unpack('<f', rec[j:j + 4])[0]
                    floats.append(float_val)
                except:
                    floats.append(float('nan'))
        print(
            f"      记录{i + 1} 前{len(floats)}个浮点数: {[f'{x:.6f}' if not math.isnan(x) else 'NaN' for x in floats]}")


def decode_with_custom_formats(file_path, start_offset, record_length):
    """
    如果找到候选长度，尝试用几种常见的数据组合格式来解码。
    """
    print("\n" + "=" * 70)
    print("4. 尝试自定义格式解码")
    print("=" * 70)

    # 几种可能的字段组合（基于通达信和其他金融数据格式）
    # 格式: (总字节数, 类型字符串, 描述)
    possible_formats = [
        (record_length, f'{record_length}s', "原始字节"),
    ]

    # 根据记录长度动态添加可能的格式
    if record_length % 2 == 0:
        half = record_length // 2
        possible_formats.append((record_length, f'{half}H', f"{half}个无符号短整型(2字节)"))

    if record_length % 4 == 0:
        quarter = record_length // 4
        possible_formats.append((record_length, f'{quarter}I', f"{quarter}个无符号整型(4字节)"))
        possible_formats.append((record_length, f'{quarter}f', f"{quarter}个单精度浮点数(4字节)"))

    # 特别测试一些常见的组合（例如：2个短整型 + 4个浮点数 = 20字节）
    if record_length == 20:
        possible_formats.append((20, 'HHffff', "2短整型+4浮点数 (可能为:日期,时间,开,高,低,收)"))

    if record_length == 32:
        possible_formats.append((32, 'IIffffII', "2整型+4浮点数+2整型 (可能为:日期,时间,开,高,低,收,成交量,成交额)"))
        possible_formats.append((32, 'HHffffQQ', "2短整型+4浮点数+2长整型"))

    with open(file_path, 'rb') as f:
        f.seek(start_offset)
        test_data = f.read(record_length * 3)  # 读取3条记录

    print(f"基于记录长度 {record_length} 字节，尝试以下格式:\n")

    for fmt_size, fmt_str, description in possible_formats:
        if fmt_size != record_length:
            continue

        print(f"  格式: {description}")
        print(f"  结构: {fmt_str}")

        try:
            # 尝试解码前3条记录
            for rec_num in range(3):
                start = rec_num * record_length
                end = start + record_length
                if end > len(test_data):
                    break

                record = test_data[start:end]
                unpacked = struct.unpack('<' + fmt_str, record)  # 先尝试小端序

                # 显示结果
                if 'H' in fmt_str or 'I' in fmt_str:  # 包含整数
                    print(f"      记录{rec_num + 1}: {unpacked[:6]}...")  # 只显示前几个值
                else:
                    print(f"      记录{rec_num + 1}: 解码成功，共 {len(unpacked)} 个值")

        except struct.error as e:
            print(f"      解码失败: {e}")
        print()


def main():
    file_path = r"G:\D盘备份1\证券股票\分钟数据\wstock_SHSZ_201701_5Min.wdz"

    if not os.path.exists(file_path):
        print("文件不存在!")
        return

    print("=" * 70)
    print("WDZ文件二进制模式深度分析")
    print("=" * 70)

    # 第一步：分析二进制模式，寻找记录长度
    best_length = analyze_binary_patterns(file_path)

    if best_length:
        # 第二步：尝试用该长度进行解码
        decode_with_custom_formats(file_path, start_offset=1024, record_length=best_length)

        print("=" * 70)
        print("分析完成！下一步建议:")
        print("=" * 70)
        print("1. 查看步骤2的输出，观察是否有明显规律（如某些字节位置总是0）")
        print("2. 查看步骤3b，是否有解码出合理的日期（如2017-XX-XX）")
        print("3. 查看步骤3e，浮点数中是否有看起来像价格的值（如15.23）")
        print("\n请将观察到的任何规律反馈给我，特别是：")
        print("  - 是否发现固定的记录长度？是多少？")
        print("  - 是否有位置能解码出合理日期？")
        print("  - 浮点数中是否有看似合理的价格？")
    else:
        print("\n分析未能确定文件结构。可能需要更专业的逆向工程工具或原始软件的更多信息。")


if __name__ == "__main__":
    main()