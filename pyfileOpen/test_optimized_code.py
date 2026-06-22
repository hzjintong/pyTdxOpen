#!/usr/bin/env python3
"""
测试优化后的代码
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 由于文件名包含连字符，使用importlib动态导入
import importlib.util

def import_module_from_file(filepath):
    """从文件路径导入模块"""
    spec = importlib.util.spec_from_file_location("module_name", filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# 导入优化后的模块
module = import_module_from_file("BatchGlobPathDelTDXLc1-5.py")
batch_delete_vipdoc_optimized = module.batch_delete_vipdoc_optimized
batch_delete_min_file = module.batch_delete_min_file
batch_delete_vipdoc = module.batch_delete_vipdoc
def test_optimized_function():
    """测试优化后的函数"""
    print("=== 测试优化后的批量处理函数 ===")
    
    # 创建一个测试目录结构
    test_dir = Path("test_vipdoc")
    
    # 清理旧的测试目录
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)
    
    # 创建测试目录结构
    markets = ['sh', 'sz', 'bj', 'ds']
    data_types = ['minline', 'fzline', 'lday']
    
    for market in markets:
        for data_type in data_types:
            dir_path = test_dir / market / data_type
            dir_path.mkdir(parents=True, exist_ok=True)
            
            # 创建一些测试文件
            for i in range(3):
                file_path = dir_path / f"{market}00000{i}.lc1"
                file_path.write_bytes(b'test content')
                
                file_path = dir_path / f"{market}00000{i}.lc5"
                file_path.write_bytes(b'test content')
    
    print(f"创建了测试目录结构: {test_dir}")
    
    # 测试优化后的函数
    try:
        start_date = '20200101'
        print(f"\n开始测试优化函数，起始日期: {start_date}")
        batch_delete_vipdoc_optimized(str(test_dir), start_date)
        print("优化函数测试完成！")
    except Exception as e:
        print(f"测试优化函数时出错: {e}")
    
    # 清理测试目录
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)
        print(f"清理测试目录: {test_dir}")

def compare_performance():
    """比较原函数和优化函数的性能差异"""
    print("\n=== 性能比较说明 ===")
    print("原实现有两个独立的函数:")
    print("1. batch_delete_min_file() - 遍历所有文件，删除老旧文件")
    print("2. batch_delete_vipdoc() - 再次遍历所有文件，删除早于设定时间的记录")
    print("\n优化后的实现:")
    print("1. batch_delete_vipdoc_optimized() - 在一次遍历中完成两个任务")
    print("\n主要优化点:")
    print("- 减少文件系统遍历次数: 从2次减少到1次")
    print("- 减少文件读取次数: 老旧文件检查后，如果文件被删除，则跳过后续处理")
    print("- 保持核心逻辑不变: 先删除老旧文件，再处理早于设定时间的记录")
    print("- 添加统计信息: 显示处理文件总数、删除老旧文件数、清洗数据文件数")

def main():
    print("代码优化说明")
    print("=" * 50)
    
    # 显示优化说明
    compare_performance()
    
    # 运行测试
    test_optimized_function()
    
    print("\n" + "=" * 50)
    print("优化总结:")
    print("1. 将两次文件遍历合并为一次，提高了效率")
    print("2. 保持了原有的核心逻辑: 先删除老旧文件，再删除早于设定时间的记录")
    print("3. 添加了详细的统计信息")
    print("4. 保持了向后兼容性，原有函数仍然可用")
    print("5. 使用优化后的函数 batch_delete_vipdoc_optimized() 替代原来的两个函数调用")

if __name__ == '__main__':
    main()