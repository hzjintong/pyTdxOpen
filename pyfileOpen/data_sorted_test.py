from operator import itemgetter

students = [
    {'name': 'Alice', 'age': 20, 'score': 85},
    {'name': 'Bob', 'age': 22, 'score': 90},
    {'name': 'Charlie', 'age': 20, 'score': 78},
    {'name': 'David', 'age': 21, 'score': 92},
    {'name': 'Eve', 'age': 20, 'score': 88},
    {'name': 'jonathan', 'age': 19, 'score': 87}
]
# 对字典列表多字段排序
sorted_students = sorted(students, key=itemgetter('age', 'score'))
print("\n使用itemgetter多字段排序:")
for student in sorted_students:
    print(student)

# 对元组列表多字段排序
data = [(1, 'b', 3), (3, 'a', 2), (2, 'c', 1), (1, 'c', 1), (2, 'e', 10)]
sorted_data = sorted(data, key=itemgetter(0, 1))
print("\n元组多字段排序:", sorted_data)