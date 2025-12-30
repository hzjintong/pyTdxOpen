import struct, os, sys
from pathlib import Path


def find_data_start(file1_path, file2_path, max_check=256):
    """
    通过比较两个WDZ文件，找出自定义文件头之后的数据起始位置。
    原理：假设文件头包含代码、日期等变量信息，而数据区开始处可能相同（如同样的记录结构标识）。
    """
    print("🔍 通过文件对比确定数据区起始偏移...")
    with open(file1_path, 'rb') as f1, open(file2_path, 'rb') as f2:
        data1 = f1.read(max_check)
        data2 = f2.read(max_check)

    # 寻找第一个两者开始出现连续相同字节的位置（可能是数据区）
    for i in range(0, max_check, 4):
        if data1[i:i + 16] == data2[i:i + 16]:
            # 验证这个位置之后至少有32字节相同
            same_len = 0
            for j in range(i, min(len(data1), len(data2))):
                if data1[j] == data2[j]:
                    same_len += 1
                else:
                    break
            if same_len >= 32:
                print(f"  在偏移 {i} (0x{i:x}) 后找到连续 {same_len} 字节相同，可能是数据区开始。")
                return i
    print("  未找到明显的共同数据起始点，将尝试常见偏移。")
    return 32  # 退回一个合理的猜测


def xor_decode_data(file_path, data_start_offset, xor_key=32):
    """从指定偏移开始，用XOR密钥解码整个文件的数据部分"""
    print(f"\n🔑 使用 XOR 密钥 {xor_key} (0x{xor_key:02x}) 解码数据...")
    with open(file_path, 'rb') as f:
        f.seek(0)
        all_data = f.read()

    # 文件头部分保持原样
    header = all_data[:data_start_offset]
    # 数据部分进行XOR解码
    encoded_data = all_data[data_start_offset:]
    decoded_data = bytes([b ^ xor_key for b in encoded_data])

    print(f"  文件总大小: {len(all_data):,} 字节")
    print(f"  自定义头长度: {len(header):,} 字节")
    print(f"  编码数据长度: {len(encoded_data):,} 字节")
    print(f"  解码后数据长度: {len(decoded_data):,} 字节")

    # 检查解码后前100字节的可读性
    sample = decoded_data[:100]
    ascii_count = sum(32 <= b < 127 for b in sample)
    print(f"  解码后样本ASCII可读性: {ascii_count}%")
    print(f"  样本HEX预览: {sample[:32].hex()}")

    # 尝试以ASCII形式显示可读部分
    ascii_preview = ''.join(chr(b) if 32 <= b < 127 else '.' for b in sample)
    print(f"  样本ASCII预览: {ascii_preview}")

    return header, decoded_data


def parse_kline_records(decoded_data, record_format='<IIffffffIfI12s', max_records=10):
    """
    尝试用给定的结构体格式解析解码后的二进制数据为K线记录。
    """
    print(f"\n📊 尝试解析K线记录 (格式: {record_format})...")

    record_size = struct.calcsize(record_format)
    total_records = len(decoded_data) // record_size
    print(f"  记录大小: {record_size} 字节")
    print(f"  理论最大记录数: {total_records}")

    records = []
    field_names = ['date', 'time', 'open', 'high', 'low', 'close', 'volume', 'amount', 'trade_count', 'pre_close',
                   'open_interest', 'reserved']

    for i in range(min(max_records, total_records)):
        try:
            start = i * record_size
            end = start + record_size
            record_bytes = decoded_data[start:end]

            if len(record_bytes) < record_size:
                break

            fields = struct.unpack(record_format, record_bytes)
            record_dict = {name: value for name, value in zip(field_names, fields)}

            # 处理日期和时间
            date_int = record_dict['date']
            time_int = record_dict['time']
            date_str = f"{date_int // 10000:04d}-{(date_int % 10000) // 100:02d}-{date_int % 100:02d}" if date_int > 0 else "N/A"
            time_str = f"{time_int // 10000:02d}:{(time_int % 10000) // 100:02d}:{time_int % 100:02d}" if time_int > 0 else "N/A"

            records.append({
                'datetime': f"{date_str} {time_str}".strip(),
                'date_int': date_int,
                'time_int': time_int,
                'open': record_dict['open'],
                'high': record_dict['high'],
                'low': record_dict['low'],
                'close': record_dict['close'],
                'volume': record_dict['volume'],
                'amount': record_dict['amount'],
                'pre_close': record_dict['pre_close']
            })

            # 显示前几条记录
            if i < 3:
                print(f"\n  记录 {i + 1}:")
                print(f"    日期: {date_str}, 时间: {time_str}")
                print(
                    f"    开: {record_dict['open']:.4f}, 高: {record_dict['high']:.4f}, 低: {record_dict['low']:.4f}, 收: {record_dict['close']:.4f}")
                print(f"    成交量: {record_dict['volume']:.2f}, 成交额: {record_dict['amount']:.2f}")

        except struct.error as e:
            print(f"  解析记录 {i + 1} 时出错: {e}")
            break

    return records, record_size


def try_multiple_offsets_and_keys(file_path, reference_file_path):
    """如果首次尝试失败，系统性地尝试不同的文件头偏移和XOR密钥"""
    print("\n" + "=" * 70)
    print("系统尝试不同参数组合")
    print("=" * 70)

    base_offsets = [0, 4, 8, 16, 32, 48, 64]
    xor_keys = [32, 0, 255, 128]  # 32是主要怀疑对象，0表示不解码，255是常用反向

    best_result = None
    best_score = 0

    for offset in base_offsets:
        for xor_key in xor_keys:
            print(f"\n尝试 偏移={offset:3d}, XOR密钥={xor_key:3d}...", end=' ')
            with open(file_path, 'rb') as f:
                f.seek(offset)
                sample = f.read(200)  # 读取样本测试
                decoded = bytes([b ^ xor_key for b in sample])

            # 评分标准：包含合理的日期（2015-2018）和正价格
            score = 0
            # 检查是否有可能的日期（YYYYMMDD格式的整数）
            for i in range(0, len(decoded) - 4, 4):
                try:
                    val = struct.unpack('<I', decoded[i:i + 4])[0]
                    if 20150000 < val < 20190000:  # 合理日期范围
                        score += 10
                        # 检查后面是否跟着看起来像价格的数据
                        if i + 8 < len(decoded):
                            price = struct.unpack('<f', decoded[i + 4:i + 8])[0]
                            if 0 < price < 10000:  # 合理股价
                                score += 5
                except:
                    pass

            # 检查是否有大量可读ASCII
            ascii_count = sum(32 <= b < 127 for b in decoded[:100])
            score += ascii_count

            print(f"评分: {score}")

            if score > best_score:
                best_score = score
                best_result = (offset, xor_key, decoded[:50])

    if best_result:
        offset, xor_key, sample = best_result
        print(f"\n🎯 最佳组合: 偏移={offset}, XOR密钥={xor_key}, 评分={best_score}")
        print(f"   样本预览: {sample.hex()[:40]}...")
        return offset, xor_key

    return None, None


def main():
    # 文件路径 - 请确认这两个文件在同一目录
    file1 = r"G:\D盘备份1\证券股票\分钟数据\wstock_SHSZ_201701_5Min.wdz"
    file2 = r"G:\D盘备份1\证券股票\分钟数据\wstock_SHSZ_201502_5Min.wdz"

    if not os.path.exists(file1) or not os.path.exists(file2):
        print("请确认两个WDZ文件都存在。")
        return

    print("=" * 70)
    print("WDZ文件综合解码与解析")
    print("=" * 70)

    # 1. 确定数据起始偏移
    data_start = find_data_start(file1, file2)

    # 2. 解码第一个文件的数据部分
    header, decoded_data = xor_decode_data(file1, data_start, xor_key=32)

    # 3. 尝试解析为K线记录
    records, record_size = parse_kline_records(decoded_data, max_records=20)

    if records and len(records) > 5:
        print(f"\n✅ 初步解析成功！发现 {len(records)} 条记录。")
        print(f"   第一条记录: {records[0]['datetime']} O:{records[0]['open']:.4f} H:{records[0]['high']:.4f}")
        print(f"   最后一条记录: {records[-1]['datetime']} C:{records[-1]['close']:.4f}")

        # 4. 验证：检查日期是否在合理范围（2017年左右）
        valid_dates = [r for r in records if 20170000 < r['date_int'] < 20180000]
        if len(valid_dates) > len(records) * 0.5:
            print(f"\n📅 日期验证通过！{len(valid_dates)}/{len(records)} 条记录在2017年范围内。")
        else:
            print(f"\n⚠️  日期验证失败。只有 {len(valid_dates)}/{len(records)} 条记录在2017年范围内。")
            print("   将尝试其他偏移和密钥组合...")
            new_offset, new_key = try_multiple_offsets_and_keys(file1, file2)
            if new_offset is not None:
                print(f"\n🔄 使用新参数重新解码: 偏移={new_offset}, 密钥={new_key}")
                header, decoded_data = xor_decode_data(file1, new_offset, xor_key=new_key)
                records, record_size = parse_kline_records(decoded_data, max_records=20)

    else:
        print("\n❌ 初步解析未得到合理数据。尝试其他参数组合...")
        new_offset, new_key = try_multiple_offsets_and_keys(file1, file2)
        if new_offset is not None:
            print(f"\n🔄 使用新参数重新解码: 偏移={new_offset}, 密钥={new_key}")
            header, decoded_data = xor_decode_data(file1, new_offset, xor_key=new_key)
            records, record_size = parse_kline_records(decoded_data, max_records=20)

    # 5. 如果成功，保存解码后的数据供进一步分析
    if 'decoded_data' in locals() and len(decoded_data) > 1000:
        output_file = file1.replace('.wdz', '_decoded.bin')
        with open(output_file, 'wb') as f:
            f.write(decoded_data)
        print(f"\n💾 解码后的数据已保存到: {output_file}")

        # 同时保存解析的CSV
        if records:
            import csv
            csv_file = file1.replace('.wdz', '_parsed.csv')
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=records[0].keys())
                writer.writeheader()
                writer.writerows(records)
            print(f"📄 解析的CSV数据已保存到: {csv_file}")


if __name__ == "__main__":
    main()