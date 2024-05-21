# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Email   : likun19941001@163.com
# @Time    : 2023/10/19 18:13
# @File    : variable.py


import threading
from collections import deque


class Variable:
    _vars_mapping = {}  # 这个变量不建议直接操作，全部通过类方法进行访问，否则线程不安全
    _lock = threading.Lock()  # 锁 _vars_mapping
    _lock_variable = threading.Lock()  # 锁 Variable

    def __new__(cls, name, value=0):
        with cls._lock:
            if name in cls._vars_mapping:
                return cls._vars_mapping[name]
            instance = super().__new__(cls)
            instance.name = name
            instance.data_array = deque([value], maxlen=3)
            instance.index = 0
            cls._vars_mapping[name] = instance
            return instance

    def _var(self, name):
        with Variable._lock:
            return Variable._vars_mapping.get(name)

    @classmethod
    def check_existence(cls, name):
        with cls._lock:
            return name in cls._vars_mapping

    @classmethod
    def get_var_keys(cls):
        with cls._lock:
            return cls._vars_mapping.keys()

    @classmethod
    def get_all_signals(cls):
        with cls._lock:
            # 注意使用时最好用snapshot防止多线程在字典迭代过程中对字典修改 list(dict.values())
            return list(cls._vars_mapping.values())

    @property
    def Value(self):
        with self._lock_variable:
            return self.data_array[-1]

    @Value.setter
    def Value(self, new_value):
        with self._lock_variable:
            self.data_array.append(new_value)


if __name__ == '__main__':
    pass
    Variable('SOA')
    print(Variable('SOA').Value)
    Variable('SOA').Value = 1
    print(Variable('SOA').Value)
    print(Variable.check_existence('SOA'))
    print(Variable.check_existence('SOA2'))
    print(Variable.get_var_keys())
