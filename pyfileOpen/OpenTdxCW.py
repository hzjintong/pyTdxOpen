from struct import *
# import struct
# from datetime import datetime, date, timedelta
# from http.client import responses

# import pandas as pd


def read_tdx_cw_file(file_path):
    """
    读取通达信财务数据文件
    """

    try :
        with open(file_path, 'rb') as cw_file:
            header_size = calcsize("<3h1H3L")
            stock_item_size = calcsize("<6s1c1L")
            data_header = cw_file.read(header_size)
            stock_header = unpack("<3h1H3L", data_header)
            max_count = stock_header[3]
            print(f"stock_header: {stock_header}")
            print(f"max_count: {max_count}")

            for stock_idx in range(0, max_count):
                cw_file.seek(header_size + stock_idx * calcsize("<6s1c1L"))
                si = cw_file.read(stock_item_size)
                stock_item = unpack("<6s1c1L", si)
                code = stock_item[0].decode()
                foa = stock_item[2]
                cw_file.seek(foa)
                info_data = cw_file.read(calcsize('<584f')) #原参数量为264f
                data_size = len(info_data)
                cw_info = unpack('<584f', info_data)  #原参数量为264f
                print(f"stock_item : {stock_item}")
                print(f"stock_code : {code}")
                print(foa)
                print(data_size)
                print("%s, %s" % (code, str(cw_info)))

                response =input("是否继续列印下一条（y/n）？")
                if response == "y":
                    continue
                else:
                    break

    except Exception as e:
        print(f"读取文件 {file_path} 时出错: {e}")
        return []

def main(open_filename):
    read_tdx_cw_file(open_filename)

if __name__ == '__main__':
    open_file = "d:/new_hxzq_hc/vipdoc/cw/gpcw20211231.dat"
    main(open_file)
    open_file = r"d:\new_hxzq_hc\vipdoc\cw\gpcw20220331.dat"
    main(open_file)
    open_file = r"d:\new_hxzq_hc\vipdoc\cw\gpcw20220630.dat"
    main(open_file)
    open_file = r"d:\new_hxzq_hc\vipdoc\cw\gpcw20220930.dat"
    main(open_file)
    open_file = r"d:\new_hxzq_hc\vipdoc\cw\gpcw20221231.dat"
    main(open_file)