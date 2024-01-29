# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2023/10/19 18:13
# @File    : variable.py


import threading
from loguru import logger

vars_mapping = {}


class Variable:
    # vars_mapping = {}
    _lock = threading.Lock()
    _lock_variable = threading.Lock()

    def __new__(cls, name, value=0):
        with cls._lock:
            global vars_mapping
            if name in vars_mapping:
                return vars_mapping[name]
            else:
                instance = super().__new__(cls)
                instance.name = name
                instance.data_array = [value]
                instance.index = 0
                instance.pre_index = 0
                instance._value = [value]
                instance._pre_value = []
                vars_mapping[name] = instance
                return instance

    def _var(self, name):
        global vars_mapping
        return vars_mapping.get(name)

    @property
    def Value(self):
        return self.data_array[-1]

    @property
    def preValue(self):
        if len(self._pre_value) == 0:
            return None
        return self._pre_value[-1]

    @Value.setter
    def Value(self, new_value):
        with self._lock_variable:
            global vars_mapping
            vars_mapping.get(self.name).data_array.append(new_value)

    def update_pre_value(self):
        self._pre_value.append(self._value[-1])

    def update_value(self):
        if len(self.data_array) <= 1:
            return
        self.index += 1
        try:
            v = self.data_array[self.index]
            self._value.append(v)
        except Exception as e:
            logger.error(f'error: {str(e)}')
            
