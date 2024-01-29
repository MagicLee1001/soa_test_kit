# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2023/11/21 14:37
# @File    : remote.py

import datetime
import os
import shutil
import socket
import threading
import traceback
import urllib.parse
import requests
import svn.utility
from loguru import logger
from settings import env

# 云端执行
TEST_MANAGER_RUN = False
CURRENT_MODULE_ID = ''
SERVER_ADDRESS = ''
TASK_ID = ''
DISTRIBUTE_ID = ''
# Id 名字的映射
MODULE_ID_MAPPING = {}
# 用例和模块的映射
CASE_MAPPING = {}


def pc_name():
    """
    获取计算机名称
    """
    name = socket.gethostname()
    return name


class Run(object):
    def __init__(self, server, task_id, distribute_id):
        self.time_folder_path = ''
        if str(server).startswith('http:') is False:
            self.http_server = 'http://' + server
        else:
            self.http_server = server
        global SERVER_ADDRESS
        SERVER_ADDRESS = self.http_server
        self.task_id = task_id
        global TASK_ID
        TASK_ID = self.task_id
        self.distribute_id = distribute_id
        global DISTRIBUTE_ID
        DISTRIBUTE_ID = self.distribute_id
        global TEST_MANAGER_RUN
        TEST_MANAGER_RUN = True

    def create_group(self, group_name, order):
        """
        按分组生成文件夹
        """
        if group_name is None and order is None:
            group_order_path = self.time_folder_path
        else:
            # 执行测试计划
            # 排序按照模块创建文件夹
            if order is None:
                group_order = group_name
            else:
                order = "%02d" % order
                group_order = str(order) + "_" + group_name
            #
            group_order_path = self.time_folder_path + '\\' + group_order
            if os.path.exists(group_order_path) is False:
                os.mkdir(group_order_path)
                # os.mkdir(self.time_folder_path + "\\result\\"+group_order)
        return group_order_path

    def export_svn_group(self, group_url, group_order_path, run_time):
        try:
            if group_url is None or group_url == '':
                return False
            urls = str(group_url).split(',')
            for svn_url in urls:
                try:
                    if svn_url == '' or svn_url == "''":
                        continue
                    svn_url = urllib.parse.unquote(svn_url, encoding='utf-8')
                    svn_url = parse_svn_url(svn_url)
                    client = svn.utility.get_client(svn_url, username=env.svn_username, password=env.svn_password)
                    client.export(to_path=group_order_path, force=True)
                    logger.info('svn group export: ' + svn_url + '\n' + group_order_path)
                    if run_time != 1:
                        generate_load_test_case(run_time, group_order_path)
                except Exception as e:
                    logger.error(traceback.format_exc())
            return True
        except Exception as e:
            logger.error(traceback.format_exc())
            return False

    def parse_case(self):
        """
        解析任务下发的用例
        """

        response = requests.get(self.http_server + '/caseRun/task', params={'taskId': self.task_id,
                                                                            'distributeId': self.distribute_id})
        res_data = response.json()
        if res_data['code'] == -1:
            logger.error(res_data)
            return
        cases = []
        case_path = os.path.abspath('execute_case')
        if os.path.exists(case_path) is False:
            os.mkdir(case_path)
        time_folder = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        self.time_folder_path = case_path + '\\' + str(time_folder)
        os.mkdir(self.time_folder_path)
        result_case_path = self.time_folder_path + "\\result"
        # os.mkdir(result_case_path)
        for root in res_data['data']:
            group_id = root.get('groupId')
            group_name = root.get('groupName')
            MODULE_ID_MAPPING[group_id] = group_name
            run_time = root.get('runTime')
            if run_time is None:
                run_time = 1
            order = root.get('order')
            group_svn_url = root.get('groupSvnUrl')
            # 按分组生成运行文件夹
            group_order_path = self.create_group(group_name, order)
            case_files = []
            self.export_svn_group(group_svn_url, group_order_path, run_time)
            get_suffix_file(group_order_path, 'xlsm', case_files)
            for case_file in case_files:
                CASE_MAPPING[case_file] = group_id
                cases.append(case_file)
        # call_back = CallBack()
        # call_back.task_case_path(time_folder)
        return cases, result_case_path


def get_suffix_file(path, suffix, all_files):
    """
    获取指定文件夹下指定后缀的文件
    """
    for f in os.listdir(path):  # listdir返回文件中所有目录
        file_path = path + "\\" + f
        if not os.path.isfile(f) and f.endswith(suffix):
            all_files.append(file_path)
        if os.path.isdir(file_path):
            get_suffix_file(file_path, suffix, all_files)


def svn_export(group_url, svn_url, path, run_time):
    """
    SVN 用例导出
    """
    try:
        # 导出SVN 用例到指定目录
        logger.info('>> 从SVN导出用例 >>')
        if group_url is None or group_url == '':
            svn_url = urllib.parse.unquote(svn_url, encoding='utf-8')
            url = parse_svn_url(svn_url)
            svn_client = svn.utility.get_client(url, username=env.svn_username, password=env.svn_password)
            svn_client.export(to_path=path)

            if int(run_time) != 1:
                file_name = svn_url.split(r'/')[-1]
                src_file_path = os.path.join(path, file_name)

                for time in range(1, int(run_time)):
                    logger.info('生成压测用例: ' + file_name)
                    n = "%02d" % time
                    dst_file_path = os.path.join(path,
                                                 file_name.split('.')[0] + "_" + n + "." + file_name.split('.')[1])
                    shutil.copy(src_file_path, dst_file_path)
        # else:

    except Exception as e:
        logger.error(e)


def generate_load_test_case(run_time, folder):
    """
    生成压测用例
    """
    excel_files = []
    # 获取当前文件夹中的所有文件名
    if os.path.isdir(folder):
        excel_files = os.listdir(folder)
    else:
        excel_files.append(folder)
    # 遍历文件列表，对每一个文件进行复制操作
    for file in excel_files:
        # 组装源文件路径和目标文件路径
        src_file_path = os.path.join(folder, file)
        for time in range(1, int(run_time)):
            logger.info('生成压测用例: ' + file)
            n = "%02d" % time
            dst_file_path = os.path.join(folder, file.split('.')[0] + "_" + n + "." + file.split('.')[1])
            # 判断是否是文件，如果是则进行复制操作
            if os.path.isfile(src_file_path):
                shutil.copy(src_file_path, dst_file_path)


def parse_svn_url(url):
    """
    对SVN路径中的特殊字符做处理
    """
    parse_url = str(url).replace('&', '%26')
    if '@' in url:
        parse_url = parse_url + '@'
    return parse_url


class CallBack:
    def __init__(self):
        # self.http_server = SERVER_ADDRESS
        self.task_id = TASK_ID
        self.distribute_id = DISTRIBUTE_ID

    def task_case_path(self, time_folder):
        """
        更新任务的用例执行结果路径
        """
        case_path = "file://" + pc_name() + "/execute_case/" + time_folder
        logger.info(case_path)
        try:
            requests.get(SERVER_ADDRESS + '/caseRun/startRun',
                         params={'taskId': self.task_id, 'casePath': case_path, 'distributeId': self.distribute_id})
        except Exception as e:
            logger.error(e)
            requests.get(env.remote_server + '/caseRun/startRun',
                         params={'taskId': self.task_id, 'casePath': case_path, 'distributeId': self.distribute_id})

    def module_finsh(self, module_name):
        """
       执行完成一个文件夹推送消息通知
       """
        module_id = CURRENT_MODULE_ID
        if module_id == '':
            return
        try:
            requests.get(SERVER_ADDRESS + '/caseRun/moduleFinish',
                         params={'taskId': self.task_id, 'moduleId': module_id})
        except Exception as e:
            logger.error(e)
            requests.get(env.remote_server + '/caseRun/moduleFinish',
                         params={'taskId': self.task_id, 'moduleId': module_id})

    def task_callback(self, xcu_info):
        """
        上传整个任务结果,有一条用例失败,则整个任务失败
        """

        ois_path = ''
        try:

            requests.post(SERVER_ADDRESS + '/caseRun/systemVersion',
                          json={'taskId': self.task_id, 'distributeId': self.distribute_id, 'xcu_info': xcu_info})
            res = requests.get(SERVER_ADDRESS + '/caseRun/taskResultCallback',
                               params={'taskId': self.task_id, 'baseLine': xcu_info['xcu_baseline'],
                                       'coreVersion': xcu_info['acore_app'], 'logPath': ois_path,
                                       'distributeId': self.distribute_id})
            logger.info(u'task callback request test_manager result: ' + str(res))
        except Exception as e:
            logger.error(e)

    def case_callback(self, module_id, case_name, result):

        """
        使用线程上传用例结果
        """
        th = threading.Thread(target=self._task, args=(module_id, case_name, result,))
        th.start()

    def _task(self, module_id, case_name, result):

        try:
            res = requests.get(SERVER_ADDRESS + '/caseRun/caseResultCallback',
                               params={'taskId': self.task_id, 'moduleId': module_id, 'caseName': case_name,
                                       'result': result})
            res_data = res.json()
            logger.info(res_data)
        except Exception as e:
            logger.error('上传用例结果失败' + str(e))
            requests.get(env.remote_server + '/caseRun/caseResultCallback',
                         params={'taskId': self.task_id, 'moduleId': module_id, 'caseName': case_name,
                                 'result': result})

    def update_case_callback(self, module_id, case_name, status='Running'):
        """
        更新用例执行结果
        """
        module_name = MODULE_ID_MAPPING.get(module_id)
        try:
            requests.get(SERVER_ADDRESS + '/caseRun/updateCase',
                         params={'taskId': self.task_id, 'caseName': case_name, 'moduleId': module_id,
                                 'status': status, 'moduleName': module_name})
        except Exception as e:
            logger.error('更新用例状态失败' + str(e))
            requests.get(env.remote_server + '/caseRun/updateCase',
                         params={'taskId': self.task_id, 'caseName': case_name, 'status': status,
                                 'moduleId': module_id, 'moduleName': module_name})

    def update_case_log_path(self, case_id, log_path):
        """
        更新用例的日志
        """
        try:
            requests.get(SERVER_ADDRESS + '/caseRun/caseLogResult',
                         params={'taskId': self.task_id, 'caseId': case_id, 'logPath': log_path})
        except Exception as e:
            logger.error('更新日志失败' + str(e))
            requests.get(env.remote_server + '/caseRun/caseLogResult',
                         params={'taskId': self.task_id, 'caseId': case_id, 'logPath': log_path})


if __name__ == '__main__':
    # resp = requests.get('https://xxx/caseRun/systemVersion',
    #              json={'taskId': 'a', 'distributeId': '1', 'xcu_info': {"a": 1}})
    # resp = requests.get('https://xxx/caseRun/task',
    #              params={'taskId': '44b2be6e82d211eeb33d96a234d0dd88 ', 'distributeId': '2091'})
    # print(resp.json())

    run = Run(server='xxx',
              task_id='44b2be6e82d211eeb33d96a234d0dd88',
              distribute_id='2091')
    cases, result_case_path = run.parse_case()
    print(cases)
