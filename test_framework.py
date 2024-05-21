# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Email   : likun3@lixiang.com
# @Time    : 2023/10/24 11:15
# @File    : test_sil_xbp.py

import os
import traceback
import unittest
import ddt
import datetime
import time
from settings import env
from runner.tester import CaseTester, TestHandle, CaseParser, TestPrecondition, TestPostCondition
from runner.log import logger
from runner import run_tests_output_html_report
from connector.dds import DDSConnector, DDSConnectorRti
from connector.sdc import SDCConnector
from connector.ssh import SSHConnector
from runner.simulator import DoIPMonitorThread


def load_ddt_testcase(tc_filenames):
    env.ddt_testcase = []
    for tc_filename in tc_filenames:
        tc_filepath = os.path.join(env.case_dir, tc_filename)
        parser = CaseParser(tc_filepath=tc_filepath)
        all_testcase = parser.get_all_testcase()
        testcases = [
            {
                'case_name': key,
                'case_info': val.get('test_steps'),
                'case_title': val.get('case_name')
            } for key, val in all_testcase.items()
        ]
        TestHandle.all_case_num += len(all_testcase)
        suite_info = {
            'tc_filepath': tc_filepath,
            'suite_name': tc_filename,
            'testcases': testcases
        }
        env.ddt_testcase.append(suite_info)
    env.ddt_test_index = 0


class TestSiLXBP(unittest.TestCase):
    def setUp(self):
        if getattr(env, 'stop_autotest', True):
            self.skipTest("Global flag requests stop of the tests.")

    def test_sil_xbp(self):
        # 执行测试集
        logger.info(f'*********** env.ddt_test_index: {env.ddt_test_index}')
        TestHandle.run_state = '进行中'
        result = True
        suite_info = env.ddt_testcase[env.ddt_test_index]
        test_filename = suite_info.get('suite_name')
        tc_filepath = suite_info.get('tc_filepath')
        testcases = suite_info.get('testcases')
        self.__setattr__(
            '_testMethodName',
            test_filename[:-5]
        )
        # 执行一条测试集的所有测试用例
        logger.info(f'执行测试用例集: {test_filename}')
        for testcase in testcases:
            # 检查全局标志位是否指示停止测试
            if getattr(env, 'stop_autotest', True):
                logger.info('Stopping test due to global flag.')
                break  # 退出循环
            tc_name = testcase.get('case_name')
            test_method_name = self.__getattribute__('_testMethodName') + f'_{tc_name}'
            tc_steps = testcase.get('case_info')
            tc_title = testcase.get('case_title')
            # 远程用例执行状态更新 Running
            if env.remote_callback:
                module_id = env.case_mapping.get(tc_filepath)
                env.remote_callback.update_case_callback(module_id, tc_name)
            try:
                # 执行一条测试用例
                TestHandle.current_running_case = f'{test_filename} - {tc_name}'
                tc_ret = env.tester.run_test_case(tc_name, tc_steps, tc_title=tc_title)
            except:
                logger.error(traceback.format_exc())
                TestHandle.error_num += 1
                result_mark = '🟡'
                if env.remote_callback:
                    module_id = env.case_mapping.get(tc_filepath)
                    env.remote_callback.case_callback(module_id, tc_name, 'Fail')
            else:
                # 每一个suite之间打印跑失败的信息
                if not tc_ret:
                    run_info = env.tester.test_info.get(tc_name)
                    TestHandle.print_run_info(run_info)
                    TestHandle.fail_num += 1
                    result_mark = '🔴'
                    if env.remote_callback:
                        module_id = env.case_mapping.get(tc_filepath)
                        env.remote_callback.case_callback(module_id, tc_name, 'Fail')
                else:
                    TestHandle.pass_num += 1
                    result_mark = '🟢'
                    if env.remote_callback:
                        module_id = env.case_mapping.get(tc_filepath)
                        env.remote_callback.case_callback(module_id, tc_name, 'Pass')
                env.tester.test_info = {}
                result = tc_ret & result
            TestHandle.total_num += 1  # 已经执行总数
            TestHandle.test_detail += f'\n{result_mark} {TestHandle.case_seq}. {test_method_name}'
            TestHandle.case_seq += 1  # 序号
            TestHandle.current_pass_rate = '{:.1%}'.format(TestHandle.pass_num / TestHandle.total_num)
        if not result:
            TestHandle.result_str = '❌ 未通过'
        env.ddt_test_index += 1
        self.assertTrue(result)


def qt_main():
    report_dir = os.path.join(env.result_dir, datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
    if not os.path.exists(report_dir):
        os.mkdir(report_dir)
    TestHandle.report_dir = report_dir
    # method_names = unittest.getTestCaseNames(TestSiLXBP, 'test_sil_xbp')
    tests = [TestSiLXBP('test_sil_xbp') for i in range(len(env.ddt_testcase))]
    result, report_path = run_tests_output_html_report(
        tests,
        report_dir,
        case_name='SOA_ACore_SiL',
        html_report_title='AutoLi SOA ACore SiL Testreport',
        description='',
        tester='',
    )
    TestHandle.report_html_path = report_path
    return result, report_path


def set_test_handle():
    # 飞书报告通知变量
    TestHandle.start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    TestHandle.case_seq = 1
    TestHandle.report_dir = ''
    TestHandle.report_html_path = ''
    TestHandle.template_bg = ''
    TestHandle.cost_time = '0 s'
    TestHandle.total_num = 0
    TestHandle.pass_num = 0
    TestHandle.fail_num = 0
    TestHandle.error_num = 0
    TestHandle.pass_rate = '0%'
    TestHandle.test_detail = ''
    TestHandle.notice_url = env.notice_base_url + env.notice_path
    TestHandle.chat_id = env.notice_chat_id
    TestHandle.card_temp_id = env.notice_temp_id
    TestHandle.vin = env.ssh_connector.get_vin()
    TestHandle.case_name = 'SOA-A核软件在环仿真测试'
    TestHandle.title = 'AutoLi-测试报告'
    TestHandle.result_str = '✔ 通过'
    # QT变量
    TestHandle.run_state = '未执行'
    TestHandle.all_case_num = 0
    TestHandle.current_running_case = ''
    TestHandle.current_pass_rate = '0%'


def set_env_tester():
    # ssh connector要先启动
    env.ssh_connector = SSHConnector(hostname=env.ssh_hostname, username=env.ssh_username, password=env.ssh_password)
    env.sdc_connector = SDCConnector(env.dbo_filepath, server_ip=env.sil_server_ip, server_port=env.sil_server_port)
    env.dds_connector = DDSConnectorRti(idl_filepath=env.idl_filepath) if 'rti_' in env.idl_filepath else DDSConnector(idl_filepath=env.idl_filepath)
    env.doip_simulator = DoIPMonitorThread()
    env.tester = CaseTester(
        sub_topics=env.sub_topics,
        pub_topics=env.pub_topics,
        sdc_connector=env.sdc_connector,
        dds_connector=env.dds_connector,
        ssh_connector=env.ssh_connector,
        doip_simulator=env.doip_simulator
    )


def run():
    set_env_tester()
    set_test_handle()
    TestPrecondition(env.tester).run()
    # ddt 用例集数据 以excel表为单位
    tc_filenames = TestHandle.get_filename_from_dir(env.case_dir, 'xlsm')
    load_ddt_testcase(tc_filenames)
    qt_main()
    TestHandle.feishu_notice()
    TestPostCondition(env.tester).run()


if __name__ == '__main__':
    run()
