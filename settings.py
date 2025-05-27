# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Email   : likun3@lixiang.com
# @Time    : 2023/10/24 11:43
# @File    : settings.py

import json
import os
import sys
import yaml
import threading
from loguru import logger

# project root path
# work_dir = os.path.normpath(os.path.dirname(__file__))

if getattr(sys, 'frozen', False):
    work_dir = os.path.normpath(os.path.dirname(sys.executable))
else:
    work_dir = os.path.normpath(os.path.dirname(__file__))


class Settings:
    _lock = threading.Lock()

    def __init__(self, config_file):
        self.configs = {}  # yaml配置文件中的变量存到这里
        self.additional_configs = {}  # json配置文件中的变量存到这里
        self.settings_filepath = config_file
        self.vin = ''
        # self.sub_topics = []
        # self.pub_topics = []
        self.remote_event_data = None
        self.remote_callback = None
        self.platform_version = 2.0
        self.platform_name = 'XAP'

        # 自动化测试
        self.press_times = None  # 压测次数
        self.stop_autotest = False

        # 配置文件中修改的属性
        self.disable_sdc = True  # 启动时自动禁用sdc
        self.deploy_sil = True  # 启动时部署sil
        self.has_topic_prefix = False  # eea2.0+vbs的topic需要带前缀
        self.sub_all_topics = False
        self.pub_all_topics = False
        self.deploy_fault_server = False

        self.module_id_mapping = {}  # 远程执行变量
        self.case_mapping = {}  # 用例和模块的映射
        self.sil_node_status = 0  # 0: 未部署  1: 已连接  2: 连接断开
        self.load(config_file)

    def __getattr__(self, item):
        with self._lock:
            value = self.configs.get(item)
            if isinstance(value, str) and '\\' in value:
                return os.path.join(work_dir, value)
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

        # 添加额外变量
        additional_filepath = os.path.join(work_dir, 'data\\conf\\additional.json')
        if os.path.exists(additional_filepath):
            try:
                with open(additional_filepath, 'r', encoding='utf=8') as f:
                    json_data = json.load(f)
                    self.additional_configs = json_data
            except Exception as e:
                logger.error(f'添加额外配置文件异常: {e}')


env = Settings(os.path.join(work_dir, 'settings.yaml'))

if __name__ == '__main__':
    pass
    # print(vars(env))
    # print(env.additional_configs.get('doipclient'))
    print(hasattr(env, '123'))  # 因为 __getattr__ 中没有抛出AttributeError 所以这里是空
    # print(env.__dict__)
