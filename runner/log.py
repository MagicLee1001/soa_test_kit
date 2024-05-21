# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Email   : likun19941001@163.com
# @Time    : 2024/3/29 13:36
# @File    : log.py

from loguru import logger
import os
from datetime import datetime
from settings import work_dir

# 日志文件保存路径
log_directory = os.path.join(work_dir, 'data', 'log')
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# 配置日志
logger.add(
    os.path.join(log_directory, 'log_{time}.log'),  # 动态命名日志文件
    rotation='10 MB',  # 当文件大小达到10M时轮换
    compression='zip',  # 压缩为zip格式
    retention='7 days',  # 保存最近7天的日志
    level='INFO'  # 记录INFO级别以上的日志
)

logger = logger
