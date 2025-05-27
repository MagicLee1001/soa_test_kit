# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2024/7/16 13:59
# @File    : pytester.py

import os
import sys
import time
import subprocess
import threading
import shutil
from settings import work_dir
from runner.log import logger
from runner.tester import TestHandle


class PyTester:
    def __init__(self):
        self.allure_path = os.path.join(work_dir, 'runner\\allure-2.29.0\\bin\\allure.bat')
        self.framework_path = os.path.join(work_dir, 'test_framework.py')
        self.allure_results_path = os.path.join(work_dir, 'data\\result\\allure-results')
        self.allure_history_path = os.path.join(self.allure_results_path, 'history')
        os.makedirs(self.allure_results_path, exist_ok=True)
        self.allure_report_base_path = os.path.join(work_dir, 'data\\result\\allure-report')
        os.makedirs(self.allure_report_base_path, exist_ok=True)
        self.__current_time = time.strftime("%Y%m%d-%H%M%S")
        self.allure_report_path = os.path.join(self.allure_report_base_path, f'report-{self.__current_time}')

    @classmethod
    def run_command(cls, command):
        def stream_reader(stream, output_func):
            for line in iter(stream.readline, ''):
                output_func(line)
            stream.close()

        logger.info(command)
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   bufsize=1, encoding='utf-8')
        stdout_thread = threading.Thread(target=stream_reader, args=(process.stdout, sys.stdout.write))
        stderr_thread = threading.Thread(target=stream_reader, args=(process.stderr, sys.stderr.write))

        stdout_thread.start()
        stderr_thread.start()

        stdout_thread.join()
        stderr_thread.join()

        return_code = process.poll()
        if return_code != 0:
            logger.info(f"Command `{command}` failed with exit code {return_code}")
        else:
            logger.info(f"Command `{command}` executed successfully")

        # 确保子进程被正确终止
        process.terminate()
        process.wait()

    def copy_history_from_previous_report(self):
        report_dirs = sorted([d for d in os.listdir(self.allure_report_base_path) if os.path.isdir(os.path.join(self.allure_report_base_path, d))])
        if not report_dirs:
            logger.info("No previous report directories found.")
            return
        latest_report_path = os.path.join(self.allure_report_base_path, report_dirs[-1], 'history')
        if os.path.exists(latest_report_path):
            if not os.path.exists(self.allure_history_path):
                os.makedirs(self.allure_history_path, exist_ok=True)
            for file_name in os.listdir(latest_report_path):
                full_file_name = os.path.join(latest_report_path, file_name)
                if os.path.isfile(full_file_name):
                    destination = os.path.join(self.allure_history_path, file_name)
                    shutil.copy2(full_file_name, destination)

    def clean_allure_results(self):
        # 如果 allure-results 目录不存在则直接创建
        if not os.path.exists(self.allure_results_path):
            os.makedirs(self.allure_results_path)
        else:
            # 遍历 allure-results 目录中的文件和文件夹
            for item in os.listdir(self.allure_results_path):
                item_path = os.path.join(self.allure_results_path, item)
                # 如果 item 是文件直接删除
                if os.path.isfile(item_path) and item != 'history':
                    os.remove(item_path)
                # 如果 item 是文件夹且不是 history，则递归删除
                elif os.path.isdir(item_path) and item != 'history':
                    shutil.rmtree(item_path)

    def set_language(self):
        config_path = os.path.join(self.allure_results_path, 'allure.properties')
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write('allure.jeeves.language=zh')

    def custom_attachment_height(self):
        styles_css_path = os.path.join(self.allure_report_path, 'styles.css')
        with open(styles_css_path, 'r', encoding='utf-8') as f:
            content = f.read()
        content = content.replace('.attachment__iframe{width:100%}', '.attachment__iframe{width:100%;min-height:460px}')
        with open(styles_css_path, 'w', encoding='utf-8') as f:
            f.write(content)


def main():
    tester = PyTester()

    # 清理旧的测试结果
    tester.clean_allure_results()

    # 复制历史数据以保持趋势图
    tester.copy_history_from_previous_report()

    # 运行pytest新的测试结果
    # -v：表示“详细模式”。使用这个参数后，pytest 会输出更详细的测试进度和结果信息，包括每个测试用例的名称和结果。
    # 默认情况下，pytest 只会报告的简要信息，而使用 -v 参数能让你获取更多的细粒度信息。
    # -s：表示“禁止捕获标准输出”。在默认情况下，pytest 会捕获并隐藏测试用例中的所有输出（包括标准输出和标准错误输出）。
    # 使用 -s 参数后，这些输出将会直接显示在控制台中。这个选项在调试测试用例时特别有用，因为你可以看到所有的调试信息和打印输出。
    pytest_command = f"pytest {tester.framework_path} --alluredir={tester.allure_results_path} -v -s"
    tester.run_command(pytest_command)

    # 设置报告默认为中文 现在没啥反应
    # set_language()

    # 生成allure报告，保留历史结果
    # 运行后进行了用例更改，那么下次运行可能还是会查看到之前记录，可添加 --clean-alluredir 选项清除之前记录
    allure_generate_command = f"{tester.allure_path} generate {tester.allure_results_path} -o {tester.allure_report_path} --clean"
    tester.run_command(allure_generate_command)

    TestHandle.report_dir = tester.allure_report_path

    # 设置报告html附件样式 （定制高度）
    tester.custom_attachment_height()

    # 打开allure报告
    allure_open_command = f"{tester.allure_path} open {tester.allure_report_path}"
    subprocess.Popen(allure_open_command, creationflags=subprocess.CREATE_NEW_CONSOLE)
    # run_command(allure_open_command)


if __name__ == '__main__':
    main()

