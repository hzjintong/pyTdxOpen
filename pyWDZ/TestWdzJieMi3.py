import struct, os, sys
from pathlib import Path


def decode_tdx_date(date_code):
    """通达信日期解码函数 (来自您提供的公式)"""
    try:
        year = int(date_code / 2048) + 2004
        month_day = date_code % 2048
        month = int(month_day / 100)
        day = month_day % 100
        # 返回一个简单的日期字符串和用于验证的年份
        return f"{year:04d}-{month:02d}-{day:02d}", year
    except:
        return "INVALID", 0


def explore_tdx_structure(file_path, reference_year=2017):
    """
    智能探索通达信格式WDZ文件的结构。
    核心思路：通过寻找能产生合理年份（如2017）的XOR密钥和偏移量，反推正确解码方式。
    """
    print(f"🔬 智能探索通达信WDZ文件结构")
    print(f"目标年份参考: {reference_year}")
    print("=" * 70)

    file_size = os.path.getsize(file_path)
    print(f"文件大小: {file_size:,} 字节")

    with open(file_path, 'rb') as f:
        full_data = f.read()

    # 第一阶段：测试XOR解码和寻找日期
    print("\n1. 测试不同XOR密钥寻找有效日期 (在偏移100之后搜索)...")

    # 更广泛的XOR密钥尝试（重点关注0-255，但特别关注32、128及其补码）
    test_keys = [32, 128, 0, 255, 1, 127, 64, 192] + list(range(0, 256, 16))
    test_keys = list(dict.fromkeys(test_keys))  # 去重保持顺序

    # 我们将从文件的不同偏移开始测试数据，因为真正的数据可能藏在自定义头后面
    test_offsets = [0, 4, 8, 16, 32, 64, 100]

    best_combinations = []

    for offset in test_offsets:
        if offset >= file_size - 200:
            continue

        data_start = offset
        encoded_chunk = full_data[data_start:data_start + 1000]  # 取1KB测试

        for xor_key in test_keys:
            # 解码测试块
            decoded = bytes([b ^ xor_key for b in encoded_chunk])

            # 在整个解码块中搜索可能的日期编码（2字节或4字节整数）
            valid_years_found = []

            # 尝试将每4字节解读为整数（小端序）
            for i in range(0, len(decoded) - 3, 4):
                try:
                    potential_date_code = struct.unpack('<I', decoded[i:i + 4])[0]
                    # 通达信日期码通常不会太大，过滤明显过大的值
                    if 0 < potential_date_code < 50000:  # 合理范围
                        date_str, year = decode_tdx_date(potential_date_code)
                        if 2004 <= year <= 2030:  # 合理的年份范围
                            valid_years_found.append((i, potential_date_code, year, date_str))
                except:
                    pass

            # 如果在这个密钥下找到了合理年份的日期编码
            if valid_years_found:
                # 统计找到的2017年附近的日期数量
                target_year_count = sum(1 for _, _, year, _ in valid_years_found
                                        if abs(year - reference_year) <= 2)
                total_found = len(valid_years_found)

                if target_year_count > 0:
                    score = target_year_count * 10 + total_found
                    # 取第一个找到的日期作为示例
                    example_pos, example_code, example_year, example_date = valid_years_found[0]
                    best_combinations.append({
                        'offset': offset,
                        'xor_key': xor_key,
                        'score': score,
                        'example_pos': example_pos,
                        'example_date': f"{example_date} (编码: {example_code})",
                        'target_year_count': target_year_count,
                        'total_dates': total_found
                    })

    # 按评分排序并展示最佳结果
    if best_combinations:
        best_combinations.sort(key=lambda x: x['score'], reverse=True)
        print("\n✅ 发现可能有效的解码参数组合:")
        print("-" * 70)
        for i, combo in enumerate(best_combinations[:5]):  # 显示前5个最佳组合
            print(f"组合 {i + 1}: 文件偏移={combo['offset']:3d}, XOR密钥={combo['xor_key']:3d}, "
                  f"评分={combo['score']:3d}")
            print(f"      找到{combo['target_year_count']}个目标年份日期，共{combo['total_dates']}个有效日期")
            print(f"      示例日期: {combo['example_date']} (相对位置: {combo['example_pos']})")
            print()

        # 使用最佳组合进行完整解码尝试
        best = best_combinations[0]
        print(f"\n🎯 使用最佳组合进行深入分析:")
        print(f"   文件偏移: {best['offset']}, XOR密钥: {best['xor_key']}")

        return best['offset'], best['xor_key']
    else:
        print("\n❌ 未找到能解码出合理日期的参数组合。")
        print("可能原因: 1) 文件头更长 2) 编码方式更复杂 3) 数据结构不同")
        return None, None


def analyze_decoded_structure(file_path, data_offset, xor_key):
    """使用找到的最佳参数解码并分析数据结构"""
    print(f"\n2. 使用参数解码并分析数据结构 (偏移={data_offset}, 密钥={xor_key})")
    print("-" * 70)

    with open(file_path, 'rb') as f:
        f.seek(data_offset)
        encoded_data = f.read()

    # 解码全部数据
    decoded_data = bytes([b ^ xor_key for b in encoded_data])
    print(f"解码后数据大小: {len(decoded_data):,} 字节")

    # 寻找可能的记录长度（通过寻找重复模式）
    print("\n搜索可能的记录长度 (通过分析前1KB数据的自相关性)...")

    # 取前1KB数据进行分析
    sample = decoded_data[:1024]

    # 尝试常见的记录长度（通达信常见长度）
    common_lengths = [32, 36, 40, 44, 48, 52, 56, 60]

    candidate_lengths = []
    for rec_len in common_lengths:
        if len(sample) > rec_len * 3:
            # 检查前几个"记录"的第一个字段（假设是日期）是否相似
            first_fields = []
            for i in range(0, min(5 * rec_len, len(sample)), rec_len):
                if i + 4 <= len(sample):
                    field = struct.unpack('<I', sample[i:i + 4])[0]
                    first_fields.append(field)

            # 如果前几个记录的第一个字段值接近（可能是相近的日期）
            if len(first_fields) >= 3:
                # 计算第一个字段的差异
                diffs = [abs(first_fields[i] - first_fields[0]) for i in range(1, len(first_fields))]
                avg_diff = sum(diffs) / len(diffs) if diffs else 0
                # 如果平均差异较小（可能是连续的日期），则是一个候选
                if avg_diff < 1000 and all(0 < f < 50000 for f in first_fields):
                    candidate_lengths.append((rec_len, avg_diff, first_fields))

    if candidate_lengths:
        print("可能的记录长度候选:")
        for rec_len, avg_diff, first_fields in sorted(candidate_lengths, key=lambda x: x[1])[:3]:
            print(f"  {rec_len} 字节: 前几个日期编码 {first_fields[:3]}, 平均差异 {avg_diff:.1f}")

        # 使用第一个候选长度尝试解析一些记录
        rec_len = candidate_lengths[0][0]
        print(f"\n尝试使用记录长度 {rec_len} 字节解析前几条记录...")

        # 通达信分钟线常见字段：日期(4), 时间(4), 开盘价(4), 最高价(4), 最低价(4), 收盘价(4), 成交量(4), 成交额(4)
        # 总共可能是 32 字节，但也可能有其他变体

        num_records_to_parse = min(10, len(decoded_data) // rec_len)

        for i in range(num_records_to_parse):
            start = i * rec_len
            end = start + rec_len
            if end > len(decoded_data):
                break

            record = decoded_data[start:end]

            # 尝试不同的字段组合方式
            if rec_len >= 32:
                # 常见32字节结构：8个4字节字段
                try:
                    fields = struct.unpack('<IIIIIIII', record[:32])
                    date_str, year = decode_tdx_date(fields[0])
                    # 将时间字段（秒数）转换为时分秒
                    time_seconds = fields[1]
                    hours = time_seconds // 3600
                    minutes = (time_seconds % 3600) // 60
                    seconds = time_seconds % 60
                    time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

                    print(f"\n记录 {i + 1}:")
                    print(f"  日期: {date_str} (原始码: {fields[0]})")
                    print(f"  时间: {time_str} ({fields[1]}秒)")
                    print(f"  开: {fields[2] / 100:.2f}, 高: {fields[3] / 100:.2f}, "
                          f"低: {fields[4] / 100:.2f}, 收: {fields[5] / 100:.2f}")
                    print(f"  成交量: {fields[6]:.0f}手, 成交额: {fields[7] / 10000:.2f}万元")

                    # 如果价格看起来不合理（太大或太小），尝试不同的价格缩放因子
                    if abs(fields[2]) > 1000000:
                        print(f"  注意: 价格值异常，可能缩放因子不是100")
                except:
                    # 如果32字节解析失败，尝试其他格式
                    print(f"记录 {i + 1}: 32字节格式解析失败")

            elif rec_len >= 20:
                # 尝试更紧凑的结构
                try:
                    fields = struct.unpack('<IIffff', record[:24])
                    date_str, year = decode_tdx_date(fields[0])
                    print(f"\n记录 {i + 1} (紧凑格式):")
                    print(f"  日期: {date_str} (原始码: {fields[0]})")
                    print(f"  时间: {fields[1]}秒")
                    print(f"  开: {fields[2]:.2f}, 高: {fields[3]:.2f}, "
                          f"低: {fields[4]:.2f}, 收: {fields[5]:.2f}")
                except:
                    pass

    else:
        print("未检测到明显的固定记录长度模式。")

    return decoded_data


def brute_force_structure(file_path, decoded_bin_path=None):
    """如果自动探索失败，进行更暴力的结构尝试"""
    print("\n3. 备用方案: 暴力尝试常见通达信结构")
    print("-" * 70)

    # 常见的通达信分钟线结构（字节数: 字段描述）
    tdx_structures = [
        (32, "日期(4),时间(4),开(4),高(4),低(4),收(4),成交量(4),成交额(4)"),
        (40, "日期(4),时间(4),开(4),高(4),低(4),收(4),成交量(8),成交额(8)"),
        (36, "日期(4),时间(4),开(4),高(4),低(4),收(4),成交量(4),成交额(4),扩展(4)"),
        (44, "日期(4),时间(4),开(4),高(4),低(4),收(4),成交量(8),成交额(8),扩展(4)"),
        (20, "日期(2),时间(2),开(4),高(4),低(4),收(4)"),  # 非常紧凑的格式
    ]

    # 如果有之前保存的解码后文件，直接使用
    if decoded_bin_path and os.path.exists(decoded_bin_path):
        print(f"使用之前解码的文件: {decoded_bin_path}")
        with open(decoded_bin_path, 'rb') as f:
            decoded_data = f.read()
    else:
        # 否则尝试用最常见的参数解码
        with open(file_path, 'rb') as f:
            # 尝试跳过可能的长文件头
            f.seek(100)
            encoded_data = f.read(5000)  # 取5KB测试
        decoded_data = bytes([b ^ 32 for b in encoded_data])

    print(f"测试数据大小: {len(decoded_data):,} 字节")

    for rec_len, desc in tdx_structures:
        if len(decoded_data) < rec_len * 3:
            continue

        print(f"\n尝试结构: {rec_len}字节 ({desc})")

        # 测试前3条记录
        valid_records = 0
        for i in range(3):
            start = i * rec_len
            end = start + rec_len
            if end > len(decoded_data):
                break

            record = decoded_data[start:end]

            try:
                # 根据长度选择不同的解析方式
                if rec_len == 32:
                    fields = struct.unpack('<IIIIIIII', record)
                    date_code = fields[0]
                    time_seconds = fields[1]
                elif rec_len == 40:
                    fields = struct.unpack('<IIIIIIQQ', record)
                    date_code = fields[0]
                    time_seconds = fields[1]
                elif rec_len == 20:
                    # 紧凑格式：日期和时间可能是2字节
                    date_code, time_seconds = struct.unpack('<HH', record[:4])
                else:
                    continue

                # 使用通达信日期公式解码
                date_str, year = decode_tdx_date(date_code)

                # 检查是否合理
                if 2004 <= year <= 2030 and 0 <= time_seconds < 86400:
                    valid_records += 1
                    if i == 0:
                        print(f"  记录1: 日期={date_str}, 时间={time_seconds}秒, 年={year}")
            except:
                continue

        if valid_records >= 2:
            print(f"  ✅ 可能匹配! {valid_records}/3 条记录有效")
            return rec_len
        else:
            print(f"  ❌ 不匹配")

    print("\n❌ 所有常见结构尝试均失败。")
    return None


def main():
    file_path = r"G:\D盘备份1\证券股票\分钟数据\wstock_SHSZ_201701_5Min.wdz"
    decoded_bin_path = file_path.replace('.wdz', '_decoded.bin')

    if not os.path.exists(file_path):
        print("文件不存在!")
        return

    print("=" * 70)
    print("通达信格式WDZ文件深度解析")
    print("=" * 70)

    # 首先尝试智能探索
    data_offset, xor_key = explore_tdx_structure(file_path, reference_year=2017)

    if data_offset is not None and xor_key is not None:
        # 使用找到的最佳参数分析
        decoded_data = analyze_decoded_structure(file_path, data_offset, xor_key)

        # 保存找到的正确解码数据
        output_path = file_path.replace('.wdz', '_proper_decoded.bin')
        with open(output_path, 'wb') as f:
            f.write(decoded_data)
        print(f"\n💾 正确解码的数据已保存到: {output_path}")
    else:
        print("\n⚠️  智能探索未找到明确参数，尝试备用方案...")
        # 尝试暴力破解常见结构
        rec_len = brute_force_structure(file_path, decoded_bin_path)

        if rec_len:
            print(f"\n🎯 建议尝试记录长度: {rec_len} 字节")
            print("接下来可以:")
            print("1. 使用这个记录长度解析整个文件")
            print("2. 尝试不同的价格缩放因子（100, 1000, 10000等）")
            print("3. 检查成交量/成交额字段的缩放")
        else:
            print("\n❌ 所有方法都未能确定文件结构。")
            print("建议:")
            print("1. 查找原始软件的其他WDZ文件，分析多个文件的共性")
            print("2. 如果有原始软件残留，尝试恢复或反编译相关代码")
            print("3. 在金融数据技术论坛寻求帮助，可能有其他人遇到过相同格式")


if __name__ == "__main__":
    main()