# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2024/3/29 14:15
# @File    : worker.py

import os
import time
import json
import traceback
import random
from copy import deepcopy
from runner.log import logger
from PyQt5 import QtCore
from PyQt5.QtCore import pyqtSignal, QDateTime
from PyQt5.Qt import QThread, QObject
from settings import env, work_dir
from runner.variable import Variable
from connector.sdc import SDCConnector
from connector.dds import DDSConnector, DDSConnectorRti
from connector.ssh import SSHConnector, SSHAsyncConnector
from connector.doipclient import DoIPClient
from connector.xcp import XCPConnector
from runner.simulator import DoIPMonitorThread
from runner.tester import CaseTester, TestPrecondition, TestPostCondition, TestHandle
from runner.assistant import HandleTestCaseFile
from test_framework import set_test_handle, qt_main
from flask_app import app as local_flask_app


# 在Qt框架中，几乎所有的GUI组件，都不是线程安全的。
# 这就意味着你不能在除主线程之外的任何线程中操作它们。
# 如果你试图在其他线程中操作GUI组件，可能会导致不可预见的行为，包括闪退、数据错误和死锁等。
# 应该使用信号和槽机制来将内容发送给主线程，并在槽函数中更新GUI


class GetGlobalVarsWorker(QThread):
    """
    线程安全，QT线程，获取vars_mapping并传递给其他ui线程使用
    todo: 后期有界面闪退再用这种方式，目前全局变量上锁认为是安全的
    """
    pass


class FlaskThread(QThread):
    def __init__(self, app):
        super().__init__()
        self.app = app

    def run(self):
        logger.info("Starting Flask server")
        local_flask_app.run('0.0.0.0', port=61007, threaded=True)
        # Ensure that Flask server stops correctly if QThread is stopped
        logger.info("Flask server stopped")


class AutoTestWorker(QThread):
    suite_result_path = pyqtSignal(list)

    """ 自动化测试线程"""
    def __init__(self, app):
        super().__init__()
        self.app = app

    def run(self) -> None:
        try:
            # TestHandle变量重置
            set_test_handle()
            # 设置执行用例
            self.app.set_env_testcase()
            # 测试回调，用于完成后发送信号
            env.tester.set_callback(self)
            self.suite_result_path.emit(TestHandle.result_html_path)
            # 开始自动化测试
            qt_main()
            # 飞书报告通知
            TestHandle.feishu_notice()
            if getattr(env, 'stop_autotest', True):
                TestHandle.run_state = '已停止'
                time.sleep(0.5)
                return
        except Exception as e:
            logger.error(traceback.format_exc())
            TestHandle.run_state = '执行异常: ' + str(e)
        else:
            TestHandle.run_state = '已结束'
            time.sleep(1)
        finally:
            logger.info('测试任务执行全部完成 资源重置')
            env.stop_autotest = False
            # if env.remote_callback:
            #     env.remote_callback.task_callback(env.xcu_info)
            # 远程信息重置
            env.remote_event_data = None
            env.remote_callback = None


class ReloadSettingWorker(QThread):
    """ 配置重加载线程 当前测试对象不能变化"""
    display_case_path_signal = pyqtSignal(object)

    def __init__(self, app):
        super().__init__()
        self.app = app

    def run(self) -> None:
        try:
            # 当前的connector退出
            TestPostCondition(env.tester).run()

            # 处理空配置文件路径
            setting_filepath = self.app.setting_file.text()
            if not setting_filepath:
                setting_filepath = env.settings_filepath
            env.load(setting_filepath)
            # 更新配置中的用例并渲染到UI
            case_filenames = TestHandle.get_filename_from_dir(env.case_dir, 'xlsm')
            case_filepaths = [os.path.join(env.case_dir, case_filename) for case_filename in case_filenames]
            self.display_case_path_signal.emit(case_filepaths)

            # 重写初始化connector 更新各种信号矩阵
            env.ssh_connector = SSHConnector(hostname=env.ssh_hostname, username=env.ssh_username, password=env.ssh_password, port=env.ssh_port)
            env.ssh_async_connector = SSHAsyncConnector(hostname=env.ssh_hostname, username=env.ssh_username, password=env.ssh_password, port=env.ssh_port)
            env.sdc_connector = SDCConnector(env.dbo_filepath, server_ip=env.sil_server_ip, server_port=env.sil_server_port)
            if 'rti_' in env.idl_filepath.lower():
                env.DDSConnectorClass = DDSConnectorRti
                env.platform_version = 2.0
            else:
                env.DDSConnectorClass = DDSConnector
                env.platform_version = 3.0
            env.dds_connector = env.DDSConnectorClass(idl_filepath=env.idl_filepath)
            doipclient_config = env.additional_configs.get('doipclient')
            if doipclient_config:
                env.doipclient = DoIPClient(
                    server_ip=doipclient_config['server_ip'],
                    server_port=doipclient_config['server_port'],
                    client_logical_addr=doipclient_config['client_logical_addr'],
                    server_logical_addr=doipclient_config['server_logical_addr'],
                    uds_timeout=doipclient_config['uds_timeout'],
                    security_level=doipclient_config['security_level'],
                    security_mask=doipclient_config['security_mask']
                )
            else:
                env.doipclient = DoIPClient()
            env.doip_simulator = DoIPMonitorThread()
            a2l_filepath = os.path.normpath(env.additional_configs.get('xcp', {}).get('a2l'))
            if os.path.exists(a2l_filepath):
                env.xcp_connector = XCPConnector(a2l_filepath)
            else:
                logger.warning('没有指定标定a2l文件，请放置到 data\\matrix\\ 目录下并添加配置到 data\\conf\\additional.json')
                env.xcp_connector = None

            env.tester = CaseTester(
                sub_topics=env.sub_topics,
                pub_topics=env.pub_topics,
                sdc_connector=env.sdc_connector,
                dds_connector=env.dds_connector,
                ssh_connector=env.ssh_connector,
                ssh_async_connector=env.ssh_async_connector,
                doip_simulator=env.doip_simulator,
                db_connector=env.db_connector,
                doipclient=env.doipclient,
                xcp_connector=env.xcp_connector
            )
            TestPrecondition(env.tester).run()
            logger.info('重新初始化完成!')
            logger.success('环境配置更新完成')
        except:
            logger.error(traceback.format_exc())


class DeploySilNode(QThread):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.app = parent

    def run(self):
        try:
            env.deploy_sil = True
            env.disable_sdc = True
            env.tester.ssh_connector.put_sil_server()
            # 如果已经启动了 会抛出 RuntimeError("threads can only be started once")异常
            if not env.tester.sdc_connector.started:
                env.tester.sdc_connector.connect_server()
                env.tester.sdc_connector.start()
            logger.success('完成sil仿真节点部署')
        except:
            logger.error(traceback.format_exc())


class UndeploySilNode(QThread):
    def __init__(self, app):
        super().__init__()
        self.app = app

    def run(self):
        try:
            env.deploy_sil = False
            env.disable_sdc = False
            env.tester.ssh_connector.recover_sil_environment(recover_vcs=False, recover_sdc=False)
            logger.success('完成sil仿真节点移除')
        except:
            logger.error(traceback.format_exc())


class ModifyConfigWordWorker(QThread):
    """ 修改配置字线程"""
    def __init__(self, app):
        super().__init__()
        self.app = app

    def run(self) -> None:
        try:
            text = self.app.cw_edit.text()
            if text:
                result = env.tester.ssh_connector.modify_config_word_file(text)
                if result:
                    env.xcu_info['config_word'] = text
                # 这里由于改完后重启,需要主动重新连接一下sil仿真程序
                env.tester.sdc_connector.reconnect_server()
        except:
            logger.error(traceback.format_exc())


class RecoverEnvironment(QThread):
    """ 测试环境还原线程"""
    def __init__(self, app):
        super().__init__()
        self.app = app

    def run(self) -> None:
        try:
            # 发送信号以使按钮置灰（False代表不可用）
            # 执行恢复操作
            env.tester.ssh_connector.recover_sil_environment()
        except:
            logger.error(traceback.format_exc())


class ReleaseWorker(QThread):
    """
    关闭窗口时，释放资源的线程
    """
    def __init__(self, app):
        super().__init__()
        self.app = app

    def run(self) -> None:
        """
        执行测试后的清理工作
        """
        try:
            env.tester.ssh_connector.setup_vcs_ip_config(0)
            TestPostCondition(env.tester).run()
            logger.info('资源释放完成')
        except:
            logger.error(traceback.format_exc())


class SafeLogHandler(QtCore.QObject):
    new_log = pyqtSignal(str)

    def __init__(self):
        super().__init__()

    def write(self, message):
        try:
            self.new_log.emit(message.strip())
        except:
            pass

    def flush(self):
        pass


class GenTestCaseWorker(QThread):
    def __init__(self, app, source_path, project):
        super().__init__()
        self.app = app
        self.source_path = source_path
        self.project = project

    def run(self):
        HandleTestCaseFile.gen_test_case(self.source_path, self.project)


class LowCaseTransWorker(QThread):
    display_paths_signal = pyqtSignal(object)

    def __init__(self, app, source_path, save_dir=''):
        super().__init__()
        self.app = app
        self.source_path = source_path
        self.save_dir = save_dir

    def run(self):
        paths = HandleTestCaseFile.lowercase_trans(self.source_path, save_dir=self.save_dir)
        self.display_paths_signal.emit(paths)  # 发出显示最新用例路径的信号


class DDSFuzzTest(QThread):
    def __init__(self, end_time=None):
        super().__init__()
        self.end_time = end_time
        self.running = True

    def run(self):
        logger.info(f'DDS模糊测试开始, 预计结束时间: {self.end_time.toString("yyyy-MM-dd HH:mm:ss")}')
        try:
            signals = Variable.get_all_signals()
            while self.running:
                for signal_obj in signals:
                    signal_obj.Value = float(random.randint(0, 2 ** 8 - 1))
                    try:
                        env.tester.dds_connector.dds_send(signal_obj)
                    except:
                        pass
                time.sleep(1)
                if self.end_time and QDateTime.currentDateTime() >= self.end_time:
                    break
        except:
            logger.error(f'DDS模糊测试执行异常: {traceback.format_exc()}')
        logger.info('DDS模糊测试结束')

    def stop(self):
        self.running = False

