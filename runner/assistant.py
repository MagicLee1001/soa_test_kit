# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2024/4/22 15:12
# @File    : assistant.py

import os
import time
import xlwings
import re
from runner.log import logger


class HandleTestCaseFile:
    """
    测试用例源文件预处理
    """

    @classmethod
    def has_digit(cls, text):
        pattern = r'\d'  # 匹配任意一个数字字符
        return bool(re.search(pattern, text))  # 如果找到匹配项，则返回True；否则返回False

    @classmethod
    def get_last_continuous_digits(cls, _string):
        last_digits = ""
        for char in reversed(_string):
            if char.isdigit():
                last_digits = char + last_digits
            else:
                break
        if last_digits.isdigit():
            return int(last_digits)
        else:
            return ''  # 如果不是以连续数字结尾，则返回空字符串

    @classmethod
    def replace_signals(cls, source_str):
        # 定义信号名的匹配规则
        pattern = r'(?:SRV_|MSG_|M2A_|A2M_)[a-zA-Z_]\w*'
        # 使用正则表达式查找所有符合规则的信号名
        signals = re.findall(pattern, source_str)
        for signal in signals:
            # 将信号名按照要求转换
            if not signal.startswith('M2A') and not signal.startswith('A2M'):
                new_signal = ""
                for i in range(len(signal)):
                    if i > 0 and signal[i].isupper() and signal[i - 1].islower():
                        if 'Control_Source' in signal:
                            pass
                        else:
                            new_signal += '_'
                    elif i > 0 and signal[i].isupper() and signal[i - 1].isdigit():
                        new_signal += '_'
                    new_signal += signal[i].lower()

                # 处理这俩特殊信号
                # msg_resssys_temp1_  转换成 msg_resssys_temp_[1]
                # msg_cell_volt1_  转换成 msg_cell_volt_[1]
                if ('msg_resssys_temp' in new_signal or 'msg_cell_volt' in new_signal) and cls.has_digit(new_signal):
                    last_digits = cls.get_last_continuous_digits(new_signal)
                    new_signal = new_signal.rstrip(str(last_digits))
                    new_signal = new_signal + f'_[{last_digits}]'
                else:
                    new_signal += '_'
                # 利用字符串的replace方法进行替换
                source_str = source_str.replace(signal, new_signal)
        return source_str

    @staticmethod
    def gen_test_case(source_path, project):
        """
        源用例文件(vb脚本)批处理，用例sheet生成器
        filepath: 文件/文件夹路径
        project: 项目名称
        """
        app = xlwings.App(visible=False, add_book=False)
        app.display_alerts = False  # 关闭提示信息
        app.screen_updating = False  # 关闭显示更新
        excel_filepaths = []
        try:
            if isinstance(source_path, str):
                is_dir = os.path.isdir(source_path)
                if is_dir:  # 批量修改
                    for root, dirs, files in os.walk(source_path):
                        for file in files:
                            excel_filepaths.append(os.path.join(root, file))
                else:  # 单独修改
                    excel_filepaths.append(source_path)
            elif isinstance(source_path, list):
                excel_filepaths = source_path
            else:
                raise Exception('source_path not a valid type')
            method_start_index = {'x': 'M', 'y': 12}
            project_start_index = {'x': 'S', 'y': 12}
            logger.info('开始执行伴生vb脚本, 生成测试用例工作表')
            cnt = 1
            total_nums = len(excel_filepaths)
            for f in excel_filepaths:
                logger.info(f'当前工作簿: {f}')
                if '.xls' in f:  # 判断是否为 excel文件
                    filename = os.path.basename(f)
                    wb = app.books.open(f)
                    wb.activate()
                    sht = wb.sheets[4]
                    # sht = wb.sheets['ACControl'] # 表名
                    table_info = sht.used_range
                    max_rows = table_info.last_cell.row  # 最大行数
                    for i in range(project_start_index['y'] + 1, max_rows + 1):
                        expect_projects = sht.range(project_start_index['x'] + f'{i}').value
                        if expect_projects:
                            expect_projects = expect_projects.replace(' ', '').lower()
                            expect_projects = expect_projects.split(',')  # 预期项目列表
                            if project.lower() in expect_projects:
                                sht.range(method_start_index['x'] + f'{i}').value = 'Automatic'
                            else:
                                sht.range(method_start_index['x'] + f'{i}').value = 'Manual'
                    marco = wb.app.macro(f'{filename}!caseclear')
                    marco()
                    time.sleep(2)
                    marco = wb.app.macro(f'{filename}!CaseGet')
                    marco()
                    time.sleep(3)
                    wb.save()
                    wb.close()
                    logger.info(f'用例生成完成, 进度 {cnt}/{total_nums}')
                    cnt += 1
        except Exception as e:
            logger.error(f'用例生成失败: {e}')
        else:
            logger.success('vb脚本生成测试用例全部完成 !!!')
        finally:
            app.quit()

    @classmethod
    def lowercase_trans(cls, source_path, save_dir=''):
        testcase_prefix = 'TC'
        app = xlwings.App(visible=False, add_book=False)
        app.display_alerts = False  # 关闭提示信息
        app.screen_updating = False  # 关闭显示更新
        excel_filepaths = []
        result_paths = []
        try:
            if save_dir:
                os.makedirs(save_dir, exist_ok=True)
            if isinstance(source_path, str):
                is_dir = os.path.isdir(source_path)
                if is_dir:  # 批量修改
                    for root, dirs, files in os.walk(source_path):
                        for file in files:
                            excel_filepaths.append(os.path.join(root, file))
                else:  # 单独修改
                    excel_filepaths.append(source_path)
            elif isinstance(source_path, list):
                excel_filepaths = source_path
            else:
                raise Exception('source_path not a valid type')
            total_nums = len(excel_filepaths)
            cnt = 1
            for testcase_filepath in excel_filepaths:
                logger.info(f'修改工作簿: {testcase_filepath}')
                if '.xls' in testcase_filepath:  # 判断是否为 excel文件
                    wb = app.books.open(testcase_filepath)
                    wb.activate()
                    sheet_names = []
                    for i in wb.sheets:
                        if i.name.startswith(testcase_prefix):
                            sheet_names.append(i.name)
                    for sheet_name in sheet_names:
                        sheet = wb.sheets[sheet_name]
                        table_info = sheet.used_range
                        max_rows = table_info.last_cell.row  # 最大行数o
                        for i in range(2, max_rows + 1):
                            cell = f'E{i}'
                            source_signal = sheet.range(cell).value
                            if source_signal:
                                target_signal = cls.replace_signals(source_signal)
                                sheet.range(cell).value = target_signal
                            cell = f'G{i}'
                            source_signal = sheet.range(cell).value
                            if source_signal:
                                target_signal = cls.replace_signals(source_signal)
                                sheet.range(cell).value = target_signal
                    if save_dir:
                        new_file_path = os.path.normpath(os.path.join(save_dir, os.path.basename(testcase_filepath)))
                    else:
                        new_file_path = testcase_filepath
                    result_paths.append(new_file_path)
                    wb.save(new_file_path)  # 保存
                    wb.close()
                logger.info(f'修改信号格式完成, 进度 {cnt}/{total_nums}')
                cnt += 1
        except Exception as e:
            logger.error(f'修改信号格式失败: {e}')
        else:
            logger.success('用例信号格式转换全部完成 !!!')
            return result_paths
        finally:
            app.quit()


if __name__ == '__main__':
    HandleTestCaseFile.gen_test_case(
        source_path=f"D:\likun3\Downloads\修改\XW_SOA_SIL_Topic_SecRSeatControl_二排右座椅控制.xlsm",
        project='x01'
    )
    # HandleTestCaseFile.lowercase_trans(
    #     source_path=f'D:\likun3\Downloads\修改',
    #     save_dir=f'D:\likun3\Downloads\修改\lowercase'
    # )
