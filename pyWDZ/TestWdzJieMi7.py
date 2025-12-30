import struct, os, math
from collections import Counter


def systematic_crack(file_path):
    """
    系统化破解WDZ文件：联合搜索记录长度和XOR密钥。
    """
    print("🧬 开始系统化联合搜索破解参数")
    print("=" * 70)

    file_size = os.path.getsize(file_path)
    print(f"文件大小: {file_size:,} 字节")

    with open(file_path, 'rb') as f:
        # 读取文件前部较大一块用于分析（避开可能很长的非标准头）
        f.seek(0)
        data_block = f.read(min(1024 * 64, file_size))  # 读取64KB

    print(f"分析数据块: {len(data_block):,} 字节\n")

    # 步骤1: 改进的候选记录长度探测
    print("1. 改进的候选记录长度探测...")
    length_candidates = advanced_length_detection(data_block)

    if not length_candidates:
        print("   ❌ 未找到候选记录长度，文件可能无固定结构或需更大数据块。")
        return

    print(f"   ✅ 找到 {len(length_candidates)} 个候选长度:")
    for i, (length, score) in enumerate(length_candidates[:10]):
        print(f"      {i + 1:2d}. 长度: {length:3d} 字节 | 置信度: {score:.3f}")

    # 步骤2: 对每个候选长度，搜索最佳XOR密钥
    print("\n2. 对每个候选长度，搜索最佳XOR密钥并评分...")
    print("-" * 70)

    all_candidates = []

    for rec_len, len_score in length_candidates[:15]:  # 测试前15个候选长度
        print(f"\n   正在测试记录长度: {rec_len} 字节")

        # 确保有足够数据
        if len(data_block) < rec_len * 5:
            continue

        # 尝试所有可能的单字节XOR密钥 (0-255)
        for xor_key in range(256):
            # 尝试解码前几条记录
            decoded_records = []
            valid = True

            for i in range(0, 5):
                start = i * rec_len
                end = start + rec_len
                if end > len(data_block):
                    valid = False
                    break

                encrypted_record = data_block[start:end]
                # 应用XOR解码
                decoded = bytes([b ^ xor_key for b in encrypted_record])
                decoded_records.append(decoded)

            if not valid or len(decoded_records) < 3:
                continue

            # 对解码后的记录进行评分
            score = evaluate_decoded_records(decoded_records, rec_len)

            if score > 20:  # 设定一个阈值
                all_candidates.append({
                    'length': rec_len,
                    'xor_key': xor_key,
                    'score': score,
                    'sample': decoded_records[0][:min(16, rec_len)]  # 保存第一条记录样本
                })

    # 步骤3: 汇总并排序所有候选
    if not all_candidates:
        print("\n❌ 未找到任何有希望的（长度 + XOR密钥）组合。")
        print("   可能需要考虑：")
        print("     - 多字节XOR密钥或更复杂的编码")
        print("     - 文件使用非XOR的编码（如加减法、位移）")
        print("     - 文件已被压缩")
        return

    # 按评分排序
    all_candidates.sort(key=lambda x: x['score'], reverse=True)

    print("\n" + "=" * 70)
    print("🎯 发现的有效候选组合 (按评分排序):")
    print("=" * 70)

    for i, cand in enumerate(all_candidates[:20]):  # 显示前20个最佳
        print(
            f"#{i + 1:2d}: 长度={cand['length']:3d} 字节, XOR密钥=0x{cand['xor_key']:02x}({cand['xor_key']:3d}), 评分={cand['score']:6.1f}")
        print(f"    第一条记录样本 (HEX): {cand['sample'].hex()[:32]}...")

        # 尝试将样本解读为常见的通达信结构
        if cand['length'] == 32:
            try:
                # 尝试解读为: 日期(4), 时间(4), 开高低收(4*4), 成交量(4), 成交额(4), ...
                fields = struct.unpack('<IIffffII', cand['sample'][:32])
                date_code = fields[0]
                year = (date_code // 2048) + 2004
                month_day = date_code % 2048
                month = month_day // 100
                day = month_day % 100
                print(f"    假设为32字节格式 -> 日期:{year:04d}-{month:02d}-{day:02d}, "
                      f"开:{fields[2]:.2f}, 高:{fields[3]:.2f}")
            except:
                pass
        elif cand['length'] == 40:
            try:
                # 尝试解读为: 日期(4), 时间(4), 开高低收(4*4), 成交量(8), 成交额(8)
                fields = struct.unpack('<IIffffQQ', cand['sample'][:32])
                date_code = fields[0]
                year = (date_code // 2048) + 2004
                month_day = date_code % 2048
                month = month_day // 100
                day = month_day % 100
                print(f"    假设为40字节格式 -> 日期:{year:04d}-{month:02d}-{day:02d}, "
                      f"开:{fields[2]:.2f}, 量:{fields[6]:.0f}")
            except:
                pass

        # 显示可读ASCII字符（如果有的话）
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in cand['sample'][:16])
        print(f"    ASCII预览: '{ascii_part}'")
        print()

    # 步骤4: 使用最佳候选进行详细解码测试
    if all_candidates:
        best = all_candidates[0]
        print("\n" + "=" * 70)
        print(f"💡 使用最佳候选进行详细测试 [长度={best['length']}, 密钥=0x{best['xor_key']:02x}]")
        print("=" * 70)

        detailed_decode_test(file_path, best['length'], best['xor_key'], test_records=10)


def advanced_length_detection(data, max_len=200):
    """
    使用改进的自相关和熵分析来探测记录长度。
    """
    candidates = []
    data_len = len(data)

    for L in range(4, max_len + 1, 2):
        if L < 8 or data_len < L * 10:
            continue

        # 方法1: 字节位置模L的熵值分析
        # 如果L是正确长度，那么每个记录的同位置字节可能具有较低的熵（更相似）
        position_entropy = 0
        positions_to_check = min(16, L)

        for pos in range(positions_to_check):
            bytes_at_pos = []
            for rec in range(0, min(100, data_len // L)):
                idx = rec * L + pos
                if idx < data_len:
                    bytes_at_pos.append(data[idx])

            if len(bytes_at_pos) > 10:
                # 计算这些字节的熵
                counter = Counter(bytes_at_pos)
                entropy = 0
                total = len(bytes_at_pos)
                for count in counter.values():
                    p = count / total
                    entropy -= p * math.log2(p)
                position_entropy += entropy

        avg_entropy = position_entropy / positions_to_check if positions_to_check > 0 else 8

        # 方法2: 自相关性（之前的方法）
        correlation = 0
        for offset in range(0, min(50, data_len - L), L):
            # 简单比较两个"记录"开头部分
            cmp_len = min(16, L)
            if offset + cmp_len < data_len and offset + L + cmp_len < data_len:
                match = 0
                for i in range(cmp_len):
                    if data[offset + i] == data[offset + L + i]:
                        match += 1
                correlation += match / cmp_len

        avg_correlation = correlation / 50 if correlation > 0 else 0

        # 综合评分：熵越低越好，相关性越高越好
        score = (8 - avg_entropy) * 0.6 + avg_correlation * 0.4

        if score > 0.5:  # 调整阈值
            candidates.append((L, score))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates


def evaluate_decoded_records(records, rec_len):
    """
    评估解码后的记录是否像通达信K线数据。
    返回评分，越高越好。
    """
    if len(records) < 3:
        return 0

    score = 0

    # 1. 检查前几个记录的第一个字段（可能是日期）是否连续或相近
    first_fields = []
    for rec in records[:5]:
        if len(rec) >= 4:
            # 尝试以小端序解读为整数
            val = struct.unpack('<I', rec[:4])[0]
            first_fields.append(val)

    if len(first_fields) >= 3:
        # 计算连续性
        diffs = [abs(first_fields[i + 1] - first_fields[i]) for i in range(len(first_fields) - 1)]
        avg_diff = sum(diffs) / len(diffs)
        if avg_diff < 100:  # 字段值相近
            score += 30 - min(avg_diff, 30)

    # 2. 检查是否有合理的价格字段（假设从第8字节开始是4字节浮点价格）
    for rec in records[:3]:
        if len(rec) >= 16:
            try:
                # 尝试读取可能的开盘价（第9-12字节？）
                open_price = struct.unpack('<f', rec[8:12])[0]
                # 合理的股价范围：0.01 到 10000
                if 0.01 < open_price < 10000:
                    score += 20
                # 如果是0，也可能是合理的（停牌）
                elif open_price == 0:
                    score += 5
            except:
                pass

    # 3. 检查记录中是否有大量0x00或0xFF（可能表示填充或未使用字段）
    for rec in records[:2]:
        zero_count = rec.count(0)
        ff_count = rec.count(255)
        zero_ratio = zero_count / len(rec)
        ff_ratio = ff_count / len(rec)
        # 适当的零值比例可能表示空字段
        if 0.1 < zero_ratio < 0.5:
            score += 10
        if 0.1 < ff_ratio < 0.5:
            score += 10

    # 4. 检查是否有可读的ASCII文本（如股票代码、标识）
    ascii_score = 0
    for rec in records[:2]:
        ascii_chars = sum(1 for b in rec[:20] if 32 <= b < 127)
        ascii_ratio = ascii_chars / 20
        ascii_score += ascii_ratio * 10

    score += ascii_score

    return score


def detailed_decode_test(file_path, rec_len, xor_key, test_records=10):
    """
    使用给定的参数详细解码并显示记录。
    """
    print(f"正在解码，参数: 长度={rec_len}, XOR密钥=0x{xor_key:02x}({xor_key})\n")

    with open(file_path, 'rb') as f:
        # 尝试从文件的不同位置开始，寻找数据区
        for start_offset in [0, 64, 128, 256, 512, 1024]:
            f.seek(start_offset)
            test_data = f.read(rec_len * test_records)

            if len(test_data) < rec_len * 3:
                continue

            # 解码
            decoded_data = bytes([b ^ xor_key for b in test_data])

            # 尝试多种格式解读
            print(f"从偏移 {start_offset} 开始解码:")
            print("-" * 50)

            # 尝试几种常见的通达信结构
            test_formats = [
                ('<IIffffII', "32字节: 日期,时间,开,高,低,收,量,额"),
                ('<IIffffQQ', "40字节: 日期,时间,开,高,低,收,量(8),额(8)"),
                ('<HHffff', "20字节: 日期(短),时间(短),开,高,低,收"),
                ('<Iffffff', "28字节: 日期,开,高,低,收,量,额"),
            ]

            for fmt, desc in test_formats:
                fmt_len = struct.calcsize(fmt)
                if fmt_len != rec_len:
                    continue

                print(f"  尝试格式: {desc}")
                try:
                    for i in range(min(3, test_records)):
                        start = i * rec_len
                        end = start + rec_len
                        if end > len(decoded_data):
                            break

                        record = decoded_data[start:end]
                        fields = struct.unpack(fmt, record)

                        # 显示第一条记录
                        if i == 0:
                            # 如果是包含日期的格式
                            if fmt.startswith(('<I', '<H')):
                                date_code = fields[0]
                                year = (date_code // 2048) + 2004
                                month_day = date_code % 2048
                                month = month_day // 100
                                day = month_day % 100
                                print(f"      记录1 -> 日期: {year:04d}-{month:02d}-{day:02d}, "
                                      f"开: {fields[2] if len(fields) > 2 else 0:.2f}, "
                                      f"高: {fields[3] if len(fields) > 3 else 0:.2f}")
                            else:
                                print(f"      记录1 -> 字段: {fields[:6]}...")
                except struct.error:
                    print(f"      格式不匹配")
                print()

            # 如果没有格式匹配，显示原始HEX
            print(f"  原始解码数据 (HEX): {decoded_data[:min(32, len(decoded_data))].hex()}...")
            print()


def main():
    file_path = r"G:\D盘备份1\证券股票\分钟数据\wstock_SHSZ_201701_5Min.wdz"

    if not os.path.exists(file_path):
        print("文件不存在!")
        return

    print("=" * 70)
    print("WDZ文件系统化联合参数破解")
    print("=" * 70)

    systematic_crack(file_path)

    print("\n" + "=" * 70)
    print("分析完成。如果以上方法仍未找到有效参数，说明文件可能:")
    print("  1. 使用多字节或流式XOR密钥")
    print("  2. 采用了非XOR的编码（如AES加密）")
    print("  3. 文件结构异常复杂")
    print("=" * 70)


if __name__ == "__main__":
    main()