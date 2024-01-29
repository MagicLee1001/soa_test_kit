# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2023/10/24 11:43
# @File    : settings.py

import os
import sys
import yaml
import threading

# project root path
work_dir = os.path.normpath(os.path.dirname(__file__))


class Settings:
    _lock = threading.Lock()

    def __init__(self, config_file):
        self.settings_filepath = config_file
        self.remote_event_data = None
        self.remote_callback = None
        self.is_auto_running = False
        self.load(config_file)

    def __getattr__(self, item):
        value = self.configs[item]
        if type(value) is str and '\\' in value:
            return os.path.join(work_dir, value)
        else:
            return value

    def __setattr__(self, key, value):
        with self._lock:
            if 'configs' in self.__dict__ and key in self.configs:
                self.configs[key] = value
            else:
                # 如果属性不是配置项，正常地设置属性值
                self.__dict__[key] = value

    def load(self, config_file):
        self.settings_filepath = config_file
        with open(config_file, 'r') as f:
            self.configs = yaml.safe_load(f)


env = Settings(os.path.join(work_dir, 'settings.yaml'))

if __name__ == '__main__':
    print(vars(env))
    print(env.sub_topics)
    print(env.idl_filepath)
    print(env.case_dir)
    env.ddt_test_index = 0
    env.ddt_test_index += 1
    print(env.ddt_test_index)
    print(env.remote_event_data)
    print(env.is_auto_running)
