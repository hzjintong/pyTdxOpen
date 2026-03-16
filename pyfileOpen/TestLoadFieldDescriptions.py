import re
# from PIL.ImtImagePlugin import field

class TestLoadFieldDescriptions:
    def __init__(self,field_file="专业财务数据字段说明.txt"):
        self.field_names = {}
        self.field_descriptions = {}
        self.load_field_descriptions(field_file)

    def load_field_descriptions(self, field_file):
        """加载字段说明"""
        try:
            with open(field_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            current_section = None
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # 识别章节标题
                if line.startswith('-------------') and '----------------' in line:
                    section_match = re.match(r'-*(\D+)-*', line)
                    if section_match:
                        current_section = section_match.group(1).strip()
                        continue

                # 识别字段行：数字--字段名 或 数字.--字段名
                field_match = re.match(r'(\d+)\.?--(.+)', line)
                if field_match:
                    field_id = int(field_match.group(1))
                    field_name = field_match.group(2).strip()
                    self.field_names[field_id] = field_name
                    if current_section:
                        self.field_descriptions[field_id] = f"{current_section} - {field_name}"
                    else:
                        self.field_descriptions[field_id] = field_name

        except Exception as e:
            print(f"加载字段说明文件时出错: {e}")
            # 如果没有字段说明文件，使用默认的字段索引
            for i in range(1, 585):
                self.field_names[i] = f"字段{i}"
                self.field_descriptions[i] = f"字段{i}"

if __name__ == '__main__':
    list_field = TestLoadFieldDescriptions()
    for field_id1 in list_field.field_names:
        print(list_field.field_names.get(field_id1))
        print(list_field.field_descriptions.get(field_id1))
