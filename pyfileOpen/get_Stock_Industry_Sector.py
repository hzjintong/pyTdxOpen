import pandas as pd
# import numpy as np
# import chardet

def load_stock_industry_sector_data(file_path):
    """
    读取并预处理股票板块信息
    格式：行业板块代码，行业板块名称，板块中的股票代码，股票名称
    """

    # 文件编码为 gbk，gb18030为最大扩展的GBK
    df_split = pd.read_csv(
        file_path,
        encoding='gb18030',
        header=None,
        dtype={'Industry_code': str, 'Industry_name': str, 'code':str, 'stock_name':str}
        )
    df_split.columns = ['Industry_code', 'Industry_name', 'code', 'stock_name']
    # 去除可能的空格，确保代码格式一致
    df_split['code'] = df_split['code'].astype(str).str.strip()
    # 将代码格式化为6位数字（不足前面补0）
    df_split['code'] = df_split['code'].apply(lambda x: x.zfill(6))
    df_split['stock_name'] = df_split['stock_name'].astype(str).str.strip()
    print("读取到的列名：", df_split.columns.tolist())

    return df_split

if __name__ == '__main__':
    df = load_stock_industry_sector_data(file_path=r'D:\二级行业板块.txt')
    print(df)
