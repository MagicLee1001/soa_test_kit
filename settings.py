# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2023/10/24 11:43
# @File    : settings.py

import os
import sys
import yaml
import threading

# project root path
# work_dir = os.path.normpath(os.path.dirname(__file__))

if getattr(sys, 'frozen', False):
    work_dir = os.path.normpath(os.path.dirname(sys.executable))
else:
    work_dir = os.path.normpath(os.path.dirname(__file__))


class Settings:
    _lock = threading.Lock()

    def __init__(self, config_file):
        self.settings_filepath = config_file
        self.remote_event_data = None
        self.remote_callback = None
        self.platform_version = 2.0
        self.has_topic_prefix = False  # eea2.0+vbs的topic需要带前缀
        self.stop_autotest = False
        self.disable_sdc = True  # 启动时自动禁用sdc
        self.module_id_mapping = {}  # 远程执行变量
        self.case_mapping = {}  # 用例和模块的映射
        self.load(config_file)

    def __getattr__(self, item):
        with self._lock:
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
