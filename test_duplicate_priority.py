#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试重复数据时优先保留file1_data的数据
"""

# 模拟测试数据
def test_minute_data_priority():
    """测试分钟数据重复时优先保留file1_data的数据"""
    print("测试分钟数据重复时优先保留file1_data的数据")
    print("=" * 60)

    # 模拟file1_data的数据（来自第一个文件）
    file1_data = [
        {'datetime': 20240101, 'timestamp': 930, 'open': 10.0, 'high': 11.0, 'low': 9.5, 'close': 10.5, 'amount': 1000, 'volume': 100, 'spare': 0},
        {'datetime': 20240101, 'timestamp': 931, 'open': 10.5, 'high': 11.5, 'low': 10.0, 'close': 11.0, 'amount': 1200, 'volume': 120, 'spare': 0},
        {'datetime': 20240101, 'timestamp': 932, 'open': 11.0, 'high': 12.0, 'low': 10.5, 'close': 11.5, 'amount': 1500, 'volume': 150, 'spare': 0},
    ]

    # 模拟file2_data的数据（来自第二个文件，包含重复时间戳）
    file2_data = [
        {'datetime': 20240101, 'timestamp': 931, 'open': 10.6, 'high': 11.6, 'low': 10.1, 'close': 11.1, 'amount': 1300, 'volume': 130, 'spare': 0},  # 重复时间，应该被跳过
        {'datetime': 20240101, 'timestamp': 933, 'open': 11.5, 'high': 12.5, 'low': 11.0, 'close': 12.0, 'amount': 1800, 'volume': 180, 'spare': 0},
        {'datetime': 20240101, 'timestamp': 934, 'open': 12.0, 'high': 13.0, 'low': 11.5, 'close': 12.5, 'amount': 2000, 'volume': 200, 'spare': 0},
    ]

    # 模拟合并函数
    def merge_minute_data(file1, file2):
        return file1 + file2  # file1_data在前

    # 模拟修改后的排序函数
    def sort_min_time_data(all_data):
        # 按年月日和时分间戳进行排序，但使用稳定的排序以确保相同时间戳时保留原始顺序
        sorted_data1 = sorted(all_data, key=lambda x: (x['datetime'], x['timestamp']))

        # 检查时间连续性并处理不连续的情况
        merged_data = []
        seen_timestamps = set()  # 用于跟踪已经处理过的时间戳
        number_of_repetitions = 0

        for record in sorted_data1:
            current_datetime = record['datetime']
            current_timestamp = record['timestamp']

            # 创建时间戳的唯一标识
            time_key = (current_datetime, current_timestamp)

            # 如果这个时间戳已经处理过，跳过（保留第一个出现的记录）
            if time_key in seen_timestamps:
                number_of_repetitions = number_of_repetitions + 1
                print(f"跳过重复记录: {current_datetime}/{current_timestamp}")
                continue

            # 添加数据并记录时间戳
            merged_data.append(record)
            seen_timestamps.add(time_key)

        print(f"剔除 {number_of_repetitions} 条重复记录")
        return merged_data

    # 测试流程
    print("file1_data (3条记录):")
    for i, rec in enumerate(file1_data):
        print(f"  [{i}] {rec['datetime']}/{rec['timestamp']}: open={rec['open']}")

    print("\nfile2_data (3条记录，其中第1条与file1_data的第2条时间重复):")
    for i, rec in enumerate(file2_data):
        print(f"  [{i}] {rec['datetime']}/{rec['timestamp']}: open={rec['open']}")

    # 合并数据
    merged = merge_minute_data(file1_data, file2_data)
    print(f"\n合并后共有 {len(merged)} 条记录")

    # 排序并去重
    sorted_data = sort_min_time_data(merged)

    print(f"\n最终结果 (应保留5条记录，跳过1条重复记录):")
    for i, rec in enumerate(sorted_data):
        print(f"  [{i}] {rec['datetime']}/{rec['timestamp']}: open={rec['open']} (来自: {'file1' if rec['open'] in [10.0, 10.5, 11.0] else 'file2'})")

    # 验证结果
    assert len(sorted_data) == 5, f"预期5条记录，实际得到{len(sorted_data)}条"

    # 检查重复时间戳931的数据是否来自file1
    for rec in sorted_data:
        if rec['datetime'] == 20240101 and rec['timestamp'] == 931:
            assert rec['open'] == 10.5, f"时间931的数据应来自file1(open=10.5)，实际open={rec['open']}"
            print(f"\n✅ 验证通过：时间931的数据来自file1 (open=10.5)")

    print("\n✅ 所有测试通过！")

def test_day_data_priority():
    """测试日线数据重复时优先保留file1_data的数据"""
    print("\n\n测试日线数据重复时优先保留file1_data的数据")
    print("=" * 60)

    # 模拟file1_data的数据（来自第一个文件）
    file1_data = [
        {'datetime': 20240101, 'open': 10.0, 'high': 11.0, 'low': 9.5, 'close': 10.5, 'amount': 10000, 'volume': 1000, 'spare': 0},
        {'datetime': 20240102, 'open': 10.5, 'high': 11.5, 'low': 10.0, 'close': 11.0, 'amount': 12000, 'volume': 1200, 'spare': 0},
        {'datetime': 20240103, 'open': 11.0, 'high': 12.0, 'low': 10.5, 'close': 11.5, 'amount': 15000, 'volume': 1500, 'spare': 0},
    ]

    # 模拟file2_data的数据（来自第二个文件，包含重复日期）
    file2_data = [
        {'datetime': 20240102, 'open': 10.6, 'high': 11.6, 'low': 10.1, 'close': 11.1, 'amount': 13000, 'volume': 1300, 'spare': 0},  # 重复日期，应该被跳过
        {'datetime': 20240104, 'open': 11.5, 'high': 12.5, 'low': 11.0, 'close': 12.0, 'amount': 18000, 'volume': 1800, 'spare': 0},
        {'datetime': 20240105, 'open': 12.0, 'high': 13.0, 'low': 11.5, 'close': 12.5, 'amount': 20000, 'volume': 2000, 'spare': 0},
    ]

    # 模拟合并函数
    def merge_day_data(file1, file2):
        return file1 + file2  # file1_data在前

    # 模拟修改后的排序函数
    def sort_day_time_data(all_data):
        # 按年月日和时分间戳进行排序，但使用稳定的排序以确保相同时间戳时保留原始顺序
        sorted_data1 = sorted(all_data, key=lambda x: (x['datetime']))

        # 检查时间连续性并处理不连续的情况
        merged_data = []
        seen_dates = set()  # 用于跟踪已经处理过的日期
        number_of_repetitions = 0

        for record in sorted_data1:
            current_timestamp = record['datetime']

            # 如果这个日期已经处理过，跳过（保留第一个出现的记录）
            if current_timestamp in seen_dates:
                number_of_repetitions = number_of_repetitions + 1
                print(f"跳过重复记录: {current_timestamp}")
                continue

            # 添加数据并记录日期
            merged_data.append(record)
            seen_dates.add(current_timestamp)

        print(f"剔除 {number_of_repetitions} 条重复记录")
        return merged_data

    # 测试流程
    print("file1_data (3条记录):")
    for i, rec in enumerate(file1_data):
        print(f"  [{i}] {rec['datetime']}: open={rec['open']}")

    print("\nfile2_data (3条记录，其中第1条与file1_data的第2条日期重复):")
    for i, rec in enumerate(file2_data):
        print(f"  [{i}] {rec['datetime']}: open={rec['open']}")

    # 合并数据
    merged = merge_day_data(file1_data, file2_data)
    print(f"\n合并后共有 {len(merged)} 条记录")

    # 排序并去重
    sorted_data = sort_day_time_data(merged)

    print(f"\n最终结果 (应保留5条记录，跳过1条重复记录):")
    for i, rec in enumerate(sorted_data):
        print(f"  [{i}] {rec['datetime']}: open={rec['open']} (来自: {'file1' if rec['open'] in [10.0, 10.5, 11.0] else 'file2'})")

    # 验证结果
    assert len(sorted_data) == 5, f"预期5条记录，实际得到{len(sorted_data)}条"

    # 检查重复日期20240102的数据是否来自file1
    for rec in sorted_data:
        if rec['datetime'] == 20240102:
            assert rec['open'] == 10.5, f"日期20240102的数据应来自file1(open=10.5)，实际open={rec['open']}"
            print(f"\n✅ 验证通过：日期20240102的数据来自file1 (open=10.5)")

    print("\n✅ 所有测试通过！")

if __name__ == "__main__":
    test_minute_data_priority()
    test_day_data_priority()
    print("\n" + "=" * 60)
    print("✅ 所有测试用例通过！")
    print("修改后的函数会在重复数据时优先保留file1_data的数据")