# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2023/10/23 11:18
# @File    : tester.py

import os
import sys
import re
import time
import json
import requests
import math
from loguru import logger
from prettytable import PrettyTable
from runner.variable import vars_mapping, Variable
from openpyxl import load_workbook


class TestStep:
    def __init__(
            self,
            pre_condition,
            actions,
            wait_condition,
            pass_condition,
            hold_condition,
            row_number,
            heading
    ):
        self.pre_condition = pre_condition
        self.actions = actions
        self.heading = heading
        self.wait_condition = wait_condition
        self.pass_condition = pass_condition
        self.hold_condition = hold_condition
        self.row_number = row_number
        self.heading = heading
        self.evaluation_condition = []  # 实际运行的结果
        self.step_ret = True


class TestInfo:
    def __init__(self, tc_name, tc_steps, tc_ret, tc_title=''):
        self.tc_name = tc_name
        self.tc_title = tc_title
        self.tc_steps = tc_steps
        self.tc_ret = tc_ret


class TestHandle:
    case_seq = 1
    chat_id = ''
    card_temp_id = ''
    notice_url = ''
    vin = ''
    title = ''
    case_name = ''
    report_dir = ''
    report_html_path = ''
    template_bg = ''
    start_time = ''
    cost_time = '0 s'
    result_str = ''
    total_num = 0
    pass_num = 0
    fail_num = 0
    error_num = 0
    pass_rate = '0%'
    test_detail = ''

    # 给QT界面用
    all_case_num = 0
    run_state = '未执行'
    current_running_case = ''
    current_pass_rate = '0%'

    @staticmethod
    def change_dos_to_unix(filepath):
        """ 文件制符变成unix"""
        with open(filepath, "rb+") as file_handle:
            all_text = file_handle.read()
            all_change_text = all_text.replace(b"\r\n", b"\n")
            file_handle.seek(0, 0)
            file_handle.truncate()
            file_handle.write(all_change_text)

    @staticmethod
    def get_filename_from_dir(dir_path, include):
        """
        获取给定文件夹下的文件名(带后缀)列表
        Args:
            dir_path: 文件夹路径
            include: 包含词汇
        Returns:
            文件名列表
        """
        files = os.listdir(dir_path)
        filenames = []
        if files:
            for filename in files:
                if include in filename:
                    filenames.append(filename)
            return filenames
        else:
            return False

    @staticmethod
    def print_run_info(run_info):
        def process_list(lst, connector_str='', step_length=2):
            if lst:
                result = []
                for i in range(0, len(lst), step_length):
                    group = lst[i: i + step_length]
                    result.append(connector_str.join(group))
                return '\n'.join(result)
            return ''

        def reformat_string(_str, step_length=20):
            if _str and isinstance(_str, str):
                # 先省略
                format_str = _str if len(_str) <= 40 else _str[:38] + '..'
                # 再换行切割
                return '\n'.join([format_str[i:i + step_length] for i in range(0, len(format_str), step_length)])
            return ''

        print(f'***{run_info.tc_name}: {run_info.tc_title}***')
        table = PrettyTable()
        table.field_names = ['行号', '结果', '描述', '行动', '预期', '实际']
        for tc_step in run_info.tc_steps:
            table.add_row([
                tc_step.row_number,
                tc_step.step_ret,
                reformat_string(tc_step.heading),
                process_list(tc_step.actions),
                process_list(tc_step.pass_condition, step_length=1),
                process_list(tc_step.evaluation_condition, step_length=1, connector_str=';')
            ])
        # 这里可以以后再做成更好看的，现在已经挺好看的了
        # table_html_str = table.get_html_string()
        # logger.info(table_html_str)
        table_str = table.get_string()
        print(table_str)
        print('\n')

    @classmethod
    def feishu_notice(cls, *args, **kwargs):
        if cls.total_num != 0:
            cls.pass_rate = '{:.1%}'.format(cls.pass_num / cls.total_num)
        else:
            cls.pass_rate = '0%'
        cls.template_bg = 'green' if cls.pass_num == cls.total_num else 'red'
        cost_seconds = int(time.time() - time.mktime(time.strptime(cls.start_time, "%Y-%m-%d %H:%M:%S")))
        m, s = divmod(cost_seconds, 60)
        h, m = divmod(m, 60)
        cls.cost_time = f'{h}小时{m}分{s}秒'
        # html_url = 'https:'  # TODO 做个local文件服务器

        template_variable = {
            # 'template_bg':cls.template_bg,  # 这里不知道模板变量为什么不生效
            'title': cls.title,
            'case_name': cls.case_name,
            'report_dir': cls.report_dir,
            # 'html_url': cls.html_url,  # 后面做本地文件服务器
            'vin': cls.vin,
            'start_time': cls.start_time,
            'cost_time': cls.cost_time,
            'result': cls.result_str,
            'total_num': str(cls.total_num),
            'pass_num': str(cls.pass_num),
            'fail_num': str(cls.fail_num),
            'error_num': str(cls.error_num),
            'pass_rate': cls.pass_rate,
            'test_detail': cls.test_detail,
        }
        payload = json.dumps({
            "receive_id": cls.chat_id,
            "msg_type": "interactive",
            "content": json.dumps(
                {
                    'type': 'template',
                    'data': {
                        'template_id': cls.card_temp_id,
                        'template_variable': template_variable,
                    }
                }
            )
        })
        headers = {
            'Content-Type': 'application/json'
        }
        params = {
            'receive_id_type': 'chat_id'
        }
        response = requests.request("POST", cls.notice_url, params=params, headers=headers, data=payload, timeout=5)
        logger.info(response.text)


class CaseParser:
    def __init__(self, tc_filepath):
        self.tc_filepath = tc_filepath
        self.wb = load_workbook(filename=tc_filepath)

    def parse_run_sheet(self, tc_sheet_name):
        """
        解析要执行的sheet
        :param tc_sheet_name:
        :return:
        """
        tc_sheet_name = str(tc_sheet_name).replace(' ', '').strip()
        sheet_numbers = []
        sheet_ranges = tc_sheet_name.split(";")

        for sheet_range in sheet_ranges:
            # 如果range中包含"-"符号，则解析出开始和结束的数字
            if "-" in sheet_range:
                start, end = map(int, sheet_range.split("-"))
                # 将开始和结束的数字之间的所有数字加入sheet_numbers
                for num in range(start, end + 1):
                    sheet_numbers.append(num)
            # 如果range为空，则跳过
            elif sheet_range == "":
                continue
            else:
                sheet_numbers.append(int(sheet_range))
        # 将数字转换为sheet名称，例如"3"转换为"Sheet3"
        sheet_names = ["TC" + str(num) for num in sheet_numbers]
        return sheet_names

    def get_all_testcase(self):
        """
        用例返回字典对象
            tc_sheet_name:
                'case_name':'',
                'test_steps':[]
        """
        option_sheet = self.wb['Options']
        if option_sheet is None:
            logger.error('not found Options sheet')
            return
        tc_case = option_sheet['D9'].value
        if tc_case is None or tc_case == '':
            logger.error('not found testcase tc')

        all_tc = {}
        tc_case_sheets = self.parse_run_sheet(tc_case)
        for tc_name in tc_case_sheets:
            tc_info = {
                'case_name': '',
                'test_steps': []
            }
            try:
                sheet = self.wb[tc_name]
            except Exception as e:
                logger.error(f'{e} {self.tc_filepath}: {tc_name} sheet not exists')
                continue
            test_steps = []
            for row_number, row in enumerate(sheet.iter_rows(), start=2):
                if row[1].value == 'Test case' and not tc_info['case_name']:
                    tc_info['case_name'] = str(row[2].value).strip()
                if row[1].value == 'Test step':
                    actions = str(row[4].value).split('\n')
                    pass_condition = str(row[6].value).split('\n')
                    test_step = TestStep(
                        pre_condition=row[3].value,
                        actions=actions,
                        hold_condition=row[7].value,
                        wait_condition=row[5].value,
                        pass_condition=pass_condition,
                        row_number=row_number,
                        heading=row[2].value
                    )
                    test_steps.append(test_step)
            tc_info['test_steps'] = test_steps

            all_tc[tc_name] = tc_info
        return all_tc


class TestPrecondition:
    def __init__(self, tester):
        self.tester = tester

    def start_sdc_connector(self):
        logger.info('>>> sdc接收器 启动tcp接收线程 ...')
        self.tester.sdc_connector.start()
        time.sleep(3)

    def start_dds_connector(self):
        """
        dds connector订阅与发布池启动
        Bug to fix: 先发布后启动，部分Topic如 ACSetStatus中的信号无法正常接受
        这一块以后再分析原因
        """
        logger.info('>>> dds订阅器 启动订阅线程池 ...')
        for sub_tp_name in self.tester.sub_topics:
            self.tester.dds_connector.create_subscriber(sub_tp_name)
        time.sleep(3)

        logger.info('>>> dds发布器 启动发布线程池 ...')
        for pub_tp_name in self.tester.pub_topics:
            self.tester.dds_connector.create_publisher(pub_tp_name)
        time.sleep(3)

    def start_ssh_connector(self):
        logger.info('>>> ssh连接器 vcsDB信号初始化 ...')
        self.tester.ssh_connector.get_vsc_db_signals()
        time.sleep(1)

    def run(self):
        self.start_sdc_connector()
        self.start_dds_connector()
        self.start_ssh_connector()


class TestPostCondition:
    def __init__(self, tester):
        self.tester = tester

    def sdc_connector_leave(self):
        self.tester.sdc_connector.keep_recv = False

    def dds_connector_leave(self):
        self.tester.dds_connector.release_connector()

    def ssh_connector_leave(self):
        self.tester.ssh_connector.close()

    def run(self):
        self.sdc_connector_leave()
        # self.dds_connector_leave()
        self.ssh_connector_leave()


class TestReload:
    def __init__(self, tester):
        self.tester = tester
        self.tpr = TestPrecondition(tester)

    def run(self):
        self.tpr.start_dds_connector()


class CaseTester:
    def __init__(self, sub_topics, pub_topics, sdc_connector, dds_connector, ssh_connector):
        self.sub_topics = sub_topics
        self.pub_topics = pub_topics
        self.sdc_connector = sdc_connector
        self.dds_connector = dds_connector
        self.ssh_connector = ssh_connector
        self.test_info = {}

    @staticmethod
    def convert_to_float(value):
        """
        数据类型转换
        :param value:
        :return:
        """
        if value.startswith("0b") or value.startswith("0B"):
            try:
                decimal_value = int(value[2:], 2)
                return decimal_value
            except ValueError:
                logger.error('转换二进制失败')

        if value.startswith("0x") or value.startswith("0X"):
            try:
                decimal_value = int(value[2:], 16)
                return decimal_value
            except ValueError:
                logger.error('转换十六进制失败')

        try:
            decimal_value = float(value)
            return decimal_value
        except ValueError:
            logger.error('转换十进制失败')
        return None

    def send_single_msg(self, signal):
        if signal.name.startswith('SRV_') or signal.name.startswith('MSG_'):  # 发DDS信号给被测对象
            self.dds_connector.dds_send(signal)
        elif signal.name.startswith('M2A_'):  # 发M2A TCP信号给被测对象
            self.sdc_connector.tcp_send(signal)
        elif signal.name.startswith('sql3_switch'):  # 操作vcs数据库
            self.ssh_connector.get_vsc_db_signals()
        elif signal.name.startswith('sql3_write_'):  # 操作vcs数据库
            set_signal_name = signal.name.lstrip('sql3_write_')
            self.ssh_connector.set_vsc_db_signal(
                signal_name=set_signal_name,
                signal_value=signal.Value
            )
        elif signal.name in ['Sw_HandWakeup']:  # 用例默认信号 起填充作用 无实际意义
            vars_mapping.get('SIL_Client_CnnctSt').Value = 1
        elif signal.name.startswith('A2M_'):  # 用例中要更改现有的全局变量 不作发送
            logger.info(f'修改全局A2M_信号 {signal.name} = {signal.Value}')
            vars_mapping.get(signal.name).Value = signal.Value
        else:
            raise Exception(f'SignalFormatError: {signal.name}')

    def run_test_case(self, tc_name, test_steps, tc_title=''):
        tc_ret = True
        test_info = TestInfo(tc_name, test_steps, tc_ret, tc_title=tc_title)
        logger.info(f'执行测试用例 {tc_name}')
        for _i, step in enumerate(test_steps):
            if step.pre_condition is not None and step.pre_condition != '':
                logger.info(f'Precondition {step.pre_condition}')

            step_evaluation = []

            # action 输入
            action_pass = True
            for action in step.actions:
                if action is not None and action != '' and action != 'None':
                    action = str(action).replace(' ', '').replace(';', '')
                    if '==' in str(action):
                        action = str(action).replace('==', '=')
                    # 判断是不是一组dds消息
                    if '&&' in action:
                        multi_msg = str(action).strip().split('&&')
                        signals = []
                        topic_name = ''
                        for msg in multi_msg:
                            _m = msg.split('=')
                            # 判断是不是dds消息格式
                            if not _m[0].startswith('MSG_') and not _m[0].startswith('SRV_'):
                                fail_reason = f'SignalFormatError: {_m[0]}'
                                if fail_reason not in step_evaluation:
                                    step_evaluation.append(fail_reason)
                                logger.error(f'DDS SignalFormatError: {_m[0]}')
                                action_pass = False
                                break
                            signal = vars_mapping.get(_m[0])
                            if signal is None:
                                fail_reason = f'SignalNotFound: {_m[0]}'
                                if fail_reason not in step_evaluation:
                                    step_evaluation.append(fail_reason)
                                logger.error(f'Actions not found signal {_m[0]}')
                                action_pass = False
                                break
                            else:
                                try:
                                    tpn = self.dds_connector.signal_map[signal.name]
                                    if topic_name:
                                        if topic_name != tpn:
                                            raise Exception(f'SignalsTopicNotSame')
                                    else:
                                        topic_name = tpn
                                    signal_value = CaseTester.convert_to_float(_m[1])
                                    if signal_value is None:
                                        logger.error(f'Signal {signal.name} value {signal_value}convert error')
                                        raise Exception(f'Signal {signal.name} value {signal_value}convert error')
                                    signal.Value = signal_value
                                    signals.append(signal)

                                except Exception as e:
                                    if str(e) not in step_evaluation:  # 防止原因重复
                                        step_evaluation.append(str(e))
                                    logger.error("Actions error: " + str(e))
                                    action_pass = False
                                    break
                        # 发送一组dds消息
                        if topic_name and signals:
                            self.dds_connector.dds_multi_send(
                                topic_name=topic_name,
                                signals=signals
                            )

                    else:
                        msg = str(action).strip().split('=')
                        signal = vars_mapping.get(msg[0])
                        if signal is None:
                            fail_reason = f'SignalNotFound: {msg[0]}'
                            if fail_reason not in step_evaluation:
                                step_evaluation.append(fail_reason)
                            logger.error(f'Actions SignalNotFound {msg[0]}')
                            action_pass = False
                            break
                        else:
                            try:
                                signal_value = CaseTester.convert_to_float(msg[1])
                                if signal_value is None:
                                    logger.error(f'{signal.name}={signal_value} value convert error')
                                    raise Exception(f'{signal.name}={signal_value} value convert error')
                                signal.Value = signal_value
                                self.send_single_msg(signal)
                            except Exception as e:
                                if str(e) not in step_evaluation:  # 防止原因重复
                                    step_evaluation.append(str(e))
                                logger.error("Actions error: " + str(e))
                                action_pass = False
                                break

            if not action_pass:
                tc_ret = False
                if step_evaluation:
                    test_steps[_i].evaluation_condition = step_evaluation
                test_steps[_i].step_ret = False
                continue  # action异常直接进行下一个测试步骤

            # wait condition 等待
            wait = step.wait_condition
            if wait is not None and wait != '':
                try:
                    wait = str(wait).replace(' ', '')
                    time.sleep(float(wait))
                except Exception as e:
                    logger.error(f'{e}. Wait condition format error: {wait}')

            # pass condition 校验
            step_ret = None
            for pass_con in step.pass_condition:
                if pass_con is not None and pass_con != '' and pass_con != 'None':
                    pass_con = str(pass_con).replace(' ', '').replace('&&', '')
                    # con = str(pass_con).strip().split('==')
                    try:
                        pattern = r"(\w+)\s*(==|!=|>=|<=|>|<)\s*(.*?)$"
                        match = re.match(pattern, pass_con)
                        if match is None:
                            raise Exception(f'PassConditionFormatError ')
                        variable_name = match.group(1)
                        pass_value = match.group(3)
                        variable = vars_mapping.get(variable_name)
                        if variable is None:
                            logger.error(f'Not found variable: {variable_name} ')
                            raise Exception(f'SignalNotFound: {variable_name} ')
                        real_value = variable.Value
                        step_evaluation.append(f'{variable_name}=={real_value}')

                        # "MSG_BatACChrgEngy==nan" 这种eval会报错
                        # 这里强调一下 任何值与 NaN相比都会返回False，包括 NaN == NaN
                        # 判断类型是否为 nan，用 math.isnan()
                        if 'nan' in pass_con:
                            pass_con = pass_con.replace('nan', '"nan"')
                            if math.isnan(real_value):  # NaN == NaN返回False 这里都转换为字符进行比较
                                real_value = str(real_value)
                        result = eval(pass_con, {variable_name: real_value})
                        logger.info(f'>>> {variable_name}: 实际值：{variable.Value}, 预期值：{pass_value}, 结果：{result}')
                        if step_ret is None:
                            step_ret = result
                        else:
                            step_ret = result & step_ret
                        test_steps[_i].step_ret = step_ret

                    except Exception as e:
                        evaluation_condition = str(e)
                        logger.error("Condition error: {}".format(evaluation_condition))
                        if evaluation_condition not in step_evaluation:
                            step_evaluation.append(evaluation_condition)
                        step_ret = False
                        test_steps[_i].step_ret = step_ret

                    # 一条测试步骤不过则整个用例不过
                    if not step_ret:
                        tc_ret = False

            if step_evaluation:
                test_steps[_i].evaluation_condition = step_evaluation
        test_info.tc_steps = test_steps
        test_info.tc_ret = tc_ret
        self.test_info[tc_name] = test_info
        return tc_ret


if __name__ == '__main__':
    from settings import *
    from connector.dds import DDSConnector
    from connector.sdc import SDCConnector
    from connector.ssh import SSHConnector

    ssh_connector = SSHConnector(hostname=env.ssh_hostname, username=env.ssh_username, password=env.ssh_password)
    sdc_connector = SDCConnector(dbo_filepath=env.dbo_filepath)
    dds_connector = DDSConnector(idl_filepath=env.idl_filepath)

    # 这个是跑一个excel下的一个TC
    # parser = CaseParser(
    #     # tc_filepath=r"D:\likun3\Downloads\XBP_SIL_ThermalSystemDisplay.xlsm"
    #     # tc_filepath=r"D:\likun3\Downloads\XBP_SIL_ACSetStatus_Debug.xlsm"
    #     tc_filepath=r"D:\likun3\Downloads\XBP_SIL_ACSetStatus.xlsm")

    # all_testcase = parser.get_all_testcase()
    # tc1 = all_testcase.get('TC1')
    # for test_step in tc1.get('test_steps'):
    #     print(test_step.row_number, test_step.heading, test_step.actions, test_step.pass_condition)
    #     print('>'*20)

    # 这个是跑一个excel下的所有TC
    # parser = CaseParser(
    #     tc_filepath=r"D:\likun3\Downloads\XBP_SIL_ACSetStatus.xlsm"
    # )
    # tester = CaseTester(
    #     sub_topics=['ACSetStatus'],
    #     pub_topics=['ACSetStatus'],
    #     sdc_connector=sdc_connector,
    #     dds_connector=dds_connector,
    #     ssh_connector=ssh_connector
    # )
    # TestPrecondition(tester)
    # all_testcase = parser.get_all_testcase()
    # for tc_sheet_name, tc_info in all_testcase.items():
    #     tc_name = tc_info.get('case_name')
    #     test_steps = tc_info.get('test_steps')
    #     tester.run_test_case(tc_sheet_name, test_steps, tc_title=tc_name)
    #     test_info = tester.test_info.get(tc_sheet_name)
    #     time.sleep(2)
    #     for tc_step in test_info.tc_steps:
    #         print(
    #             tc_step.row_number,
    #             tc_step.heading,
    #             tc_step.actions,
    #             tc_step.pass_condition,
    #             tc_step.evaluation_condition,
    #             tc_step.step_ret
    #         )
    # TestPostCondition(tester)

