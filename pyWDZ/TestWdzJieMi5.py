import struct, os, sys

def test_all_combinations(file_path):
    """
    系统性地测试字节顺序、偏移量和记录格式的所有合理组合。
    筛选标准：1. 价格为正且合理；2. 日期连续或相近。
    """
    print("🧪 开始系统化组合测试...")
    print("="*70)

    with open(file_path, 'rb') as f:
        raw_data = f.read(5000)  # 读取足够数据用于测试

    # 定义要测试的参数
    byte_orders = ['<', '>']  # 小端序，大端序
    offsets = [0, 64, 128]
    # 定义不同的记录格式: (记录长度, 格式字符串, 描述)
    record_formats = [
        (20, 'HHffff', "20字节紧凑 (日2,时2,开4,高4,低4,收4)"),
        (32, 'IIffffQQ', "32字节标准 (日4,时4,开4,高4,低4,收4,量8,额8)"),
        (40, 'IIffffQQQ', "40字节扩展 (在32字节后加8字节扩展)"),
    ]

    valid_candidates = []

    for offset in offsets:
        data = raw_data[offset:]
        for order in byte_orders:
            for rec_len, fmt, desc in record_formats:
                fmt_str = order + fmt
                try:
                    record_size = struct.calcsize(fmt_str)
                except struct.error:
                    continue

                if len(data) < record_size * 5:
                    continue  # 数据不够测试5条记录

                dates = []
                prices_ok = True
                sample_records = []

                # 尝试解析前5条记录
                for i in range(5):
                    start = i * rec_len
                    end = start + rec_len
                    if end > len(data):
                        break
                    record = data[start:end]

                    try:
                        # 解包记录
                        unpacked = struct.unpack(fmt_str, record[:record_size])
                        date_code = unpacked[0]
                        open_price = unpacked[2] if len(unpacked) > 2 else 0

                        # 应用通达信日期公式解码（假设A）
                        year = (date_code // 2048) + 2004
                        month_day = date_code % 2048
                        month = month_day // 100
                        day = month_day % 100

                        # 合理性检查
                        # 1. 年份在合理范围
                        # 2. 价格为正且小于一个极大值（例如1000）
                        if not (2004 <= year <= 2030):
                            prices_ok = False
                            break
                        if open_price <= 0 or open_price > 1000:
                            prices_ok = False
                            break

                        dates.append(date_code)
                        sample_records.append((year, month, day, open_price))

                    except struct.error:
                        prices_ok = False
                        break

                # 评估该组合
                if prices_ok and len(dates) >= 3:
                    # 检查日期连续性：前几个日期码应该是相同或递增的
                    date_diff = [dates[i+1] - dates[i] for i in range(len(dates)-1)]
                    # 允许差值很小（同一分钟的不同时刻或相邻日期）
                    is_sequential = all(abs(diff) < 10 for diff in date_diff)

                    if is_sequential:
                        score = len(dates)
                        valid_candidates.append({
                            'offset': offset,
                            'order': order,
                            'rec_len': rec_len,
                            'desc': desc,
                            'score': score,
                            'sample': sample_records,
                            'dates_raw': dates
                        })

    # 输出结果
    if not valid_candidates:
        print("❌ 未找到任何能产生合理日期和价格的组合。")
        print("可能的原因：")
        print("  1. 文件头非常长，或数据被加密/混淆")
        print("  2. 价格字段不是标准IEEE浮点数")
        print("  3. 通达信日期公式的参数需要调整（例如起始年份非2004）")
        return None

    # 按分数排序并显示最佳结果
    valid_candidates.sort(key=lambda x: x['score'], reverse=True)
    print(f"✅ 找到 {len(valid_candidates)} 个有效候选组合。最佳结果如下：\n")
    for i, cand in enumerate(valid_candidates[:3]):  # 显示前3个最佳
        print(f"【候选{i+1}】 偏移:{cand['offset']} | 字节序:{cand['order']} | {cand['desc']}")
        print(f"    样例数据（年-月-日, 开盘价）:")
        for j, rec in enumerate(cand['sample'][:2]):  # 显示前2条样例
            print(f"      记录{j+1}: {rec[0]}-{rec[1]:02d}-{rec[2]:02d}, 开盘价={rec[3]:.4f}")
        print(f"    原始日期码序列: {cand['dates_raw'][:5]}")
        print()

    best = valid_candidates[0]
    return best

def decode_with_best_combination(file_path, best_params, num_records=20):
    """使用找到的最佳参数解码并显示更多记录"""
    print("\n" + "="*70)
    print(f"使用最佳参数进行详细解码 [偏移={best_params['offset']}, 字节序={best_params['order']}, {best_params['desc']}]")
    print("="*70)

    record_fmt = best_params['order'] + best_params['desc'].split('(')[1].split(')')[0].replace('日', 'H').replace('时', 'H').replace('开', 'f').replace('高', 'f').replace('低', 'f').replace('收', 'f').replace('量', 'Q').replace('额', 'Q').replace('扩展', 'Q').replace(',', '').replace('2', 'H').replace('4', 'I').replace('8', 'Q')
    # 简化处理：如果格式字符串太复杂，我们直接使用已知的几种格式
    if best_params['rec_len'] == 20:
        record_fmt = best_params['order'] + 'HHffff'
    elif best_params['rec_len'] == 32:
        record_fmt = best_params['order'] + 'IIffffQQ'
    elif best_params['rec_len'] == 40:
        record_fmt = best_params['order'] + 'IIffffQQQ'

    with open(file_path, 'rb') as f:
        f.seek(best_params['offset'])
        # 读取足够的数据
        data_to_decode = f.read(best_params['rec_len'] * num_records)

    record_size = struct.calcsize(record_fmt)
    num = min(num_records, len(data_to_decode) // best_params['rec_len'])

    print(f"解析前 {num} 条记录:\n")
    print("序号 | 日期 (原始码) | 年-月-日 | 时间/开盘价 | 最高价 | 最低价 | 收盘价 | 成交量 | 成交额")
    print("-" * 90)

    for i in range(num):
        start = i * best_params['rec_len']
        end = start + best_params['rec_len']
        record = data_to_decode[start:end]

        try:
            fields = struct.unpack(record_fmt, record[:record_size])
            date_code = fields[0]

            # 通达信日期解码
            year = (date_code // 2048) + 2004
            month_day = date_code % 2048
            month = month_day // 100
            day = month_day % 100

            # 根据格式显示不同的字段
            if best_params['rec_len'] == 20:
                # HHffff 格式: 日期, 时间, 开, 高, 低, 收
                time_val = fields[1]
                open_price, high, low, close = fields[2:6]
                vol, amount = 0, 0  # 紧凑格式可能不包含成交量和成交额
                print(f"{i+1:3d} | {date_code:10d} | {year:04d}-{month:02d}-{day:02d} | {time_val:6d} | {open_price:8.4f} | {high:8.4f} | {low:8.4f} | {close:8.4f} | {'N/A':>8} | {'N/A':>8}")
            elif best_params['rec_len'] == 32:
                # IIffffQQ 格式: 日期, 时间, 开, 高, 低, 收, 成交量, 成交额
                time_val = fields[1]
                open_price, high, low, close = fields[2:6]
                vol, amount = fields[6:8]
                print(f"{i+1:3d} | {date_code:10d} | {year:04d}-{month:02d}-{day:02d} | {time_val:6d} | {open_price:8.4f} | {high:8.4f} | {low:8.4f} | {close:8.4f} | {vol:8.0f} | {amount:8.0f}")
            elif best_params['rec_len'] == 40:
                # IIffffQQQ 格式: 日期, 时间, 开, 高, 低, 收, 成交量, 成交额, 扩展
                time_val = fields[1]
                open_price, high, low, close = fields[2:6]
                vol, amount, _ = fields[6:9]
                print(f"{i+1:3d} | {date_code:10d} | {year:04d}-{month:02d}-{day:02d} | {time_val:6d} | {open_price:8.4f} | {high:8.4f} | {low:8.4f} | {close:8.4f} | {vol:8.0f} | {amount:8.0f}")

        except struct.error as e:
            print(f"{i+1:3d} | 解析错误: {e}")
            continue

# 主程序
def main():
    file_path = r"G:\D盘备份1\证券股票\分钟数据\wstock_SHSZ_201701_5Min.wdz"

    if not os.path.exists(file_path):
        print("文件不存在!")
        return

    print("="*70)
    print("WDZ文件格式最终验证脚本")
    print("="*70)

    # 第一步：系统测试所有组合
    best_params = test_all_combinations(file_path)

    if best_params:
        # 第二步：使用最佳参数详细解码
        decode_with_best_combination(file_path, best_params, num_records=15)

        print(f"\n🎯 最佳参数已找到！")
        print(f"   文件头偏移: {best_params['offset']}")
        print(f"   字节顺序: {'小端序' if best_params['order'] == '<' else '大端序'}")
        print(f"   记录格式: {best_params['desc']}")
        print(f"   记录长度: {best_params['rec_len']} 字节")

        # 询问是否保存为CSV
        save = input("\n是否将解析结果保存为CSV文件? (y/N): ").strip().lower()
        if save == 'y':
            # 这里可以添加保存CSV的代码
            print("CSV保存功能需要根据具体字段实现。")
    else:
        print("\n⚠️ 未能自动确定正确格式。")
        print("建议手动检查以下可能性：")
        print("  1. 价格字段可能是整数（单位：分），需要除以100")
        print("  2. 尝试其他文件偏移量（如 256, 512）")
        print("  3. 日期编码的起始年份可能不是2004")

if __name__ == "__main__":
    main()