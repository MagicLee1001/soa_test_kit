# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Email   : likun19941001@163.com
# @Time    : 2023/10/24 11:06
# @File    : __init__.py

import os
import time
from runner import htmler
from unittest import TestSuite


def run_tests_output_html_report(
        tests,
        report_dir,
        case_name='',
        html_report_title='测试报告',
        description='',
        tester='',
        verbosity=2):
    # 执行测试用例
    suite = TestSuite()
    suite.addTests(tests)

    # 生成html测试报告完整文件路径
    report_path = os.path.join(
        report_dir,
        'TestReport_%s_%s.htm' % (case_name, time.strftime("%Y-%m-%d-%H_%M_%S", time.localtime(time.time())))
    )
    with open(report_path, 'wb') as fp:
        runner = htmler.HTMLTestRunner(
                stream=fp,
                verbosity=verbosity,
                title=html_report_title,
                description=description,
                tester=tester
        )
        result = runner.run(suite)
        return result, report_path
