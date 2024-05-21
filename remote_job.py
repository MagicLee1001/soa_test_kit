# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Email   : likun3@lixiang.com
# @Time    : 2023/11/24 10:23
# @File    : remote_job.py

"""
远程测试服务，分两种执行场景
1. soa_test_kit qt界面启动，远程功能开关开启，作为tcp客户端与qt远程执行server通信，传递测试消息
2. 直接作为命令行工具执行，无需qt界面启动
"""


import json
import os
import sys
if getattr(sys, 'frozen', False):
    workspace = os.path.normpath(os.path.dirname(sys.executable))
else:
    workspace = os.path.normpath(os.path.dirname(__file__))

import socket
import argparse
import time
import traceback
from runner.log import logger


def check_port(ip, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)  # 设置超时时间
    result = sock.connect_ex((ip, port))
    sock.close()
    if result == 0:
        logger.info(f"Port {port} is open. QT界面已启动并打开远程执行开关")
        return True
    else:
        logger.info(f"Port {port} is not open. QT界面未打开远程执行开关")
        return False


def run_job():
    server_ip = '127.0.0.1'
    server_port = 54321

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
        if check_port(server_ip, server_port):
            # qt界面执行
            try:
                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_socket.connect((server_ip, server_port))
                client_socket.sendall(json_data.encode())
                time.sleep(2)
                client_socket.close()
            except Exception as e:
                logger.error(e)
        else:
            # 终端窗口执行
            from settings import env
            from test_framework import run, TestHandle
            from runner.remote import Run, CallBack

            try:
                env.remote_run = Run(
                    server=server_addr,
                    task_id=task_id,
                    distribute_id=distribute_id
                )
                case_filepaths, result_case_path = env.remote_run.parse_case()
                env.remote_callback = CallBack()
                env.case_dir = os.path.normpath(os.path.dirname(case_filepaths[0]))
                logger.info(f'测试用例目录: {env.case_dir}')
                # 测试执行
                run()
            except:
                logger.error(traceback.format_exc())
            finally:
                try:
                    logger.info('<<< 测试任务执行全部完成 资源重置>>>\n')
                    env.remote_callback.task_callback(env.xcu_info)
                    logger.info(f'\n'
                                f'测试时长: {TestHandle.cost_time}\n'
                                f'测试总数: {TestHandle.total_num}\n'
                                f'通过数量: {TestHandle.pass_num}\n'
                                f'通过率: {TestHandle.pass_rate}\n'
                                f'测试结果路径: {TestHandle.report_html_path}')
                except:
                    pass
                time.sleep(3)
                input('<<< 执行完成，请关闭此窗口 >>>')


if __name__ == '__main__':
    run_job()
    # check_port('127.0.0.1', 54321)
