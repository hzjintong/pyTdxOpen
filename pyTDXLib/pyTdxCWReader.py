from pytdx.reader import TdxReader

# 这是一个本地读取器示例（如果你本地安装了通达信软件）
# 或者通过 API 获取远程数据
from pytdx.hq import TdxHq_API

api = TdxHq_API()
with api.connect('119.147.212.81', 7709):
    # 参数：市场ID, 股票代码
    finance = api.get_finance_info(0, '000001')
    print("--- 财务信息 ---")
    print(finance)