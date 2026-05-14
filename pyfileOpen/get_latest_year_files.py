import os


def get_latest_year_files( years, cw_path ):
    """
    获取最近几年的财务数据文件

    Args:
        years: 最近多少年
        cw_path: 财务文件所在目录

    Returns:
        排序后的文件路径列表
    """
    # 获取所有文件
    all_files = []
    for filename in os.listdir(cw_path):
        if filename.startswith('gpcw') and filename.endswith('.dat'):
            date_str = filename[4:12]  # gpcwYYYYMMDD.dat
            all_files.append((filename, date_str))

    # 按日期排序
    all_files.sort(key=lambda x: x[1], reverse=True)

    # 获取最近几年的文件（每年取最新的季度报告）
    latest_files = []
    processed_years = set()

    for filename, date_str in all_files:
        year = date_str[:4]
        if year not in processed_years:
            processed_years.add(year)
            latest_files.append((filename, date_str))

        if len(processed_years) >= years:
            break

    # 按日期正序排列
    latest_files.sort(key=lambda x: x[1])

    return [os.path.join(cw_dir, f[0]) for f in latest_files]

if __name__ == '__main__':
    # 财务数据目录
    cw_dir = r'D:\new_hxzq_hc\vipdoc\cw'
    # 查找最近几年的数据
    years_num = 5
    cw_file_list = get_latest_year_files( years_num, cw_dir )
    print(f"最近{years_num}年的财务文件：{cw_file_list}")