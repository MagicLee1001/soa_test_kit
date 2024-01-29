# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2023/11/24 10:23
# @File    : remote_job.py

import json
import os
import sys
import socket
import argparse
import time

if getattr(sys, 'frozen', False):
    workspace = os.path.normpath(os.path.dirname(sys.executable))
else:
    workspace = os.path.normpath(os.path.dirname(__file__))


parser = argparse.ArgumentParser(description='远程执行测试用例')
parser.add_argument('-s', '--server', type=str, help='上位机地址')
parser.add_argument('-t', '--task_id', type=str, help='任务ID')
parser.add_argument('-d', '--distribute_id', type=str, help='任务分发ID')
server_addr = parser.parse_args().server
task_id = parser.parse_args().task_id
distribute_id = parser.parse_args().distribute_id

json_data = json.dumps(
    {
        'event_type': 'remote_autotest',
        'event_data': {
            'server': server_addr,
            'task_id': task_id,
            'distribute_id': distribute_id
        }
    }
)

if server_addr and task_id:
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(('127.0.0.1', 54321))
    client_socket.sendall(json_data.encode())
    time.sleep(1)
    client_socket.close()

