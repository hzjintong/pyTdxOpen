import struct, os, sys
from pathlib import Path


def verify_20byte_structure_directly(file_path, start_offset=0):
    """
    不依赖任何XOR解码，直接读取原始文件，验证20字节记录结构的假设。
    核心：寻找原始二进制流中，以20字节为周期的规律性。
    """
    print(f"🔍 直接验证原始文件的20字节结构 (从偏移 {start_offset} 开始)")
    print("=" * 60)

    with open(file_path, 'rb') as f:
        f.seek(start_offset)
        # 读取足够多的数据来分析模式
        chunk_size = 1024  # 先分析1KB
        raw_data = f.read(chunk_size)

    if len(raw_data) < 60:  # 至少3条记录
        print("数据太少，无法分析。")
        return

    # 1. 检查原始数据的20字节周期性
    record_length = 20
    num_records = len(raw_data) // record_length

    print(f"分析前 {num_records} 条潜在记录...")
    print("-" * 60)

    # 将数据按20字节切分
    records = [raw_data[i * record_length:(i + 1) * record_length] for i in range(num_records)]

    # 2. 分析每条记录的前4个字节（假设是日期和时间）
    for i, rec in enumerate(records[:5]):  # 只看前5条
        if len(rec) >= 4:
            # 尝试解读为两个16位整数（可能是日期编码和时间）
            try:
                field1, field2 = struct.unpack('<HH', rec[:4])  # 小端序，两个无符号短整型
            except:
                print(f"记录 {i + 1}: 无法解析前4字节")
                continue

            # 尝试多种可能的日期解码方式
            print(f"\n记录 {i + 1} (原始HEX): {rec[:8].hex()}...")
            print(f"  字段1 (2字节): {field1} (0x{field1:04x})")
            print(f"  字段2 (2字节): {field2} (0x{field2:04x})")

            # 假设字段1是某种日期编码，尝试不同解码
            # 方式A：直接作为通达信日期码（可能需调整）
            date_code = field1
            test_year = (date_code // 2048) + 2004
            test_month_day = date_code % 2048
            test_month = test_month_day // 100
            test_day = test_month_day % 100
            print(
                f"  假设A (通达信公式): 年={test_year}, 月日码={test_month_day} -> {test_year:04d}-{test_month:02d}-{test_day:02d}")

            # 方式B：字段1可能是自某个起始日以来的天数（如2004-01-01）
            days_since_base = field1
            # 简单估算年份：2004 + 天数/365
            est_year = 2004 + days_since_base // 365
            print(f"  假设B (累计天数): 从2004年起 {days_since_base} 天 -> 约{est_year}年")

            # 方式C：字段1和字段2共同组成日期（如field1=年偏移, field2=年内天数）
            combined = (field2 << 16) | field1  # 组合成4字节
            test_year_c = (combined // 2048) + 2004
            test_month_day_c = combined % 2048
            print(f"  假设C (组合4字节): 组合值={combined} -> 年={test_year_c}")

            # 解读后面的价格字段（4字节浮点数）
            if len(rec) >= 20:
                open_price, high_price, low_price, close_price = struct.unpack('<ffff', rec[4:20])
                print(
                    f"  价格字段 (4字节浮点): 开={open_price:.4f}, 高={high_price:.4f}, 低={low_price:.4f}, 收={close_price:.4f}")
                # 如果价格看起来异常大/小，提示可能的缩放因子
                if abs(open_price) > 10000 or abs(open_price) < 0.001:
                    print(f"  注意：价格值异常，可能不是标准浮点，或是缩放因子非100。")

    # 3. 检查数据整体的规律性（前几个记录的第一个字段是否相近）
    print(f"\n{'=' * 60}")
    print("分析数据整体规律性...")

    first_fields = []
    for i in range(min(10, num_records)):
        if len(records[i]) >= 2:
            val = struct.unpack('<H', records[i][:2])[0]
            first_fields.append(val)

    if first_fields:
        print(f"前{len(first_fields)}条记录的第一个字段值: {first_fields}")
        diff = max(first_fields) - min(first_fields)
        print(f"  最大值-最小值差异: {diff}")
        if diff < 100:  # 如果前几个记录的第一个字段值很接近
            print(f"  ⚠️ 前几个记录的第一个字段非常接近，这符合K线数据日期连续的特点！")

    # 4. 检查是否存在简单的XOR模式（在20字节结构内部）
    print(f"\n{'=' * 60}")
    print("检查记录内部的字节模式...")
    sample_record = records[0] if records else None
    if sample_record and len(sample_record) == 20:
        print(f"第一条记录的字节值: {' '.join(f'{b:02x}' for b in sample_record)}")
        # 检查是否有大量0x00或0xFF
        zero_count = sample_record.count(0)
        ff_count = sample_record.count(255)
        print(f"  0x00字节数: {zero_count}, 0xFF字节数: {ff_count}")
        if zero_count > 5:
            print(f"  ⚠️ 包含大量0x00，可能表示整数0或空字段")

    return raw_data


def try_find_structure_by_bruteforce(file_path, max_offset=200):
    """
    暴力尝试：在不同文件偏移处，测试20字节结构是否能产生连续、合理的日期。
    """
    print(f"\n{'=' * 60}")
    print(f"暴力搜索正确的数据起始偏移 (测试范围 0-{max_offset})")
    print(f"{'=' * 60}")

    with open(file_path, 'rb') as f:
        full_data = f.read(max_offset + 1024)  # 多读一点数据

    best_offset = None
    best_sequence_score = 0

    for offset in range(0, max_offset + 1, 4):  # 按4字节对齐尝试
        data = full_data[offset:]
        if len(data) < 60:
            continue

        # 测试以20字节为单位解读时，前几个“日期字段”是否连续
        date_codes = []
        for i in range(0, min(80, len(data)), 20):  # 看前4条记录
            if i + 2 <= len(data):
                code = struct.unpack('<H', data[i:i + 2])[0]
                date_codes.append(code)

        if len(date_codes) >= 4:
            # 计算连续性得分：日期编码应该是递增或相近的
            score = 0
            for j in range(1, len(date_codes)):
                diff = date_codes[j] - date_codes[j - 1]
                if 0 < diff < 10:  # 小幅正向增长（如连续几天）
                    score += 5
                elif diff == 0:  # 同一天（多条分钟线）
                    score += 3
                elif -5 < diff < 0:  # 轻微反向（可能是时间顺序问题）
                    score += 1

            if score > best_sequence_score:
                best_sequence_score = score
                best_offset = offset

                if score > 10:  # 找到看起来连续的好序列
                    print(f"  偏移 {offset:3d}: 发现连续日期序列 {date_codes[:4]}, 得分={score}")
                    # 可以提前详细检查这个偏移
                    year_guess = (date_codes[0] // 2048) + 2004
                    print(f"      首日期码 {date_codes[0]} 推测年份约 {year_guess}")

    if best_offset is not None:
        print(f"\n🎯 最佳偏移候选: {best_offset} (连续性得分: {best_sequence_score})")
        return best_offset
    else:
        print("未找到明显连续的日期序列。")
        return None


def analyze_multiple_wdz_files(file_dir):
    """
    分析同一目录下的多个WDZ文件，寻找共同规律。
    """
    print(f"\n{'=' * 60}")
    print("分析同一目录下的多个WDZ文件")
    print(f"{'=' * 60}")

    wdz_files = list(Path(file_dir).glob("wstock_SHSZ_*.wdz"))
    print(f"找到 {len(wdz_files)} 个WDZ文件")

    if len(wdz_files) < 2:
        print("文件数量不足，跳过对比分析。")
        return

    # 读取每个文件的前128字节进行对比
    file_headers = {}
    for file in wdz_files[:5]:  # 最多分析5个
        with open(file, 'rb') as f:
            header = f.read(128)
        file_headers[file.name] = header

    # 寻找所有文件相同的部分（可能是固定格式头）
    common_bytes = None
    for name, header in file_headers.items():
        if common_bytes is None:
            common_bytes = header
        else:
            # 找出相同的前缀
            min_len = min(len(common_bytes), len(header))
            for i in range(min_len):
                if common_bytes[i] != header[i]:
                    common_bytes = common_bytes[:i]
                    break

    if common_bytes and len(common_bytes) > 4:
        print(f"所有文件共同的前 {len(common_bytes)} 字节 (可能是文件头):")
        print(f"  HEX: {common_bytes.hex()[:64]}...")
        ascii_repr = ''.join(chr(b) if 32 <= b < 127 else '.' for b in common_bytes)
        print(f"  ASCII: {ascii_repr}")
        print(f"推测数据区可能从偏移 {len(common_bytes)} 开始。")
        return len(common_bytes)
    else:
        print("未发现显著的共同文件头。")
        return 0


# 主程序
def main():
    file_path = r"G:\D盘备份1\证券股票\分钟数据\wstock_SHSZ_201701_5Min.wdz"
    file_dir = os.path.dirname(file_path)

    if not os.path.exists(file_path):
        print("文件不存在!")
        return

    print("=" * 60)
    print("WDZ文件深度分析 - 20字节结构专项验证")
    print("=" * 60)

    # 步骤1：分析多个文件，寻找共同文件头长度
    print("\n1. 分析多个WDZ文件的共性...")
    common_header_len = analyze_multiple_wdz_files(file_dir)

    # 步骤2：基于文件头长度，直接验证20字节结构
    test_offset = common_header_len if common_header_len > 0 else 0
    print(f"\n2. 基于推测的文件头长度 {test_offset} 进行验证...")
    raw_data = verify_20byte_structure_directly(file_path, start_offset=test_offset)

    # 步骤3：如果上一步不理想，暴力搜索最佳偏移
    print(f"\n3. 暴力搜索最佳数据起始偏移...")
    found_offset = try_find_structure_by_bruteforce(file_path, max_offset=200)

    # 步骤4：使用找到的最佳偏移再次验证
    if found_offset is not None and found_offset != test_offset:
        print(f"\n4. 使用暴力搜索找到的偏移 {found_offset} 重新验证...")
        verify_20byte_structure_directly(file_path, start_offset=found_offset)

    print(f"\n{'=' * 60}")
    print("分析完成！下一步建议：")
    print(f"{'=' * 60}")
    print("根据上述输出，请关注：")
    print("1. 哪种日期解码假设（A/B/C）产生的日期最合理？")
    print("2. 价格字段的值是否在合理范围（如0-100）？")
    print("3. 前几条记录的第一个字段是否呈现连续或接近的规律？")
    print("\n请将最合理的解码方式反馈给我，我将生成最终解析器。")


if __name__ == "__main__":
    main()