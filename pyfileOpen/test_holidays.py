from datetime import date, timedelta
from holidays import country_holidays  # 假设您使用的是holidays库

# 1. 定义起始和结束日期（使用date对象通常更方便，datetime也可以）
start_date = date(2024, 1, 1)  # 2024年1月1日
end_date = date(2024, 1, 31)  # 2024年1月31日

# 2. 定义一天的timedelta
one_day = timedelta(days=1)

# 3. 初始化holidays库（以中国为例）
# 注意：holidays库函数通常接受date对象
ch_holidays = country_holidays('CN', years=2024)

# 4. 迭代日期并进行判断
current_date = start_date
date_range = []

while current_date <= end_date:
    date_range.append(current_date)

    # 逐日判断是否为节假日
    if current_date in ch_holidays:
        print(f"日期: {current_date} 是节假日: {ch_holidays.get(current_date)}")
    # 否则，可能是工作日或周末
    # ... 您可以在这里添加更多逻辑，例如判断 current_date.weekday()

    # 推进到下一天
    current_date += one_day

# 5. 结果示例（date_range中包含了所有逐日日期对象）
# print("\n获取到的日期对象列表:", date_range)