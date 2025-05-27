# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2023/11/1 16:50
# @File    : sil_xbp.py

import os
import sys

if getattr(sys, 'frozen', False):
    workspace = os.path.normpath(os.path.dirname(sys.executable))
else:
    workspace = os.path.normpath(os.path.dirname(__file__))
sys.path.append(workspace)
sys.path.append(workspace + '\\venv\\Lib')

import time
import json
import traceback
import glob
import yaml
import subprocess
from threading import Thread
from urllib.parse import unquote
from runner.log import logger
from functools import partial
from PyQt5 import QtWidgets, QtGui, QtCore, sip
from PyQt5.QtCore import Qt, QPoint, QRect, QSize, QModelIndex, pyqtSignal, QCoreApplication, QUrl, pyqtSlot
from PyQt5.QtGui import QStandardItemModel, QFont, QIcon, QBrush, QPixmap, QColor, QTextOption, QDesktopServices
from PyQt5.Qt import QStringListModel, QCompleter, QLineEdit, QListView, QMutex, QThread, QObject, QTimer
from PyQt5.QtNetwork import QTcpServer, QTcpSocket, QHostAddress
from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QSplashScreen, QTabWidget, QVBoxLayout, QPushButton, QWidget, QTableWidget, QSpacerItem,
    QHBoxLayout, QHeaderView, QTableWidgetItem, QLabel, QCheckBox, QScrollArea, QTextEdit, QMessageBox, QFormLayout,
    QFrame, QAction, QFileDialog, QStyle, QStyleOptionViewItem, QStyleOptionButton, QInputDialog, QTabBar, QDialog,
    QComboBox, QListWidget, QListWidgetItem, QProgressBar, QMenu, QPlainTextEdit, QSplitter, QSizePolicy, QActionGroup,
    QRadioButton, QButtonGroup, QMessageBox, QTextBrowser
)
from settings import env, work_dir
from connector.dds import DDSConnector, DDSConnectorRti
from connector.sdc import SDCConnector
from connector.ssh import SSHConnector, SSHAsyncConnector
from connector.database import DBConnector
from connector.doipclient import DoIPClient
from connector.xcp import XCPConnector
from runner.cloud import CloudConnector
from runner.variable import Variable
from runner.tester import CaseTester, TestPrecondition, TestPostCondition, TestHandle, CaseParser
from runner.remote import Run, CallBack
from runner.simulator import DoIPMonitorThread, VehicleModeDiagnostic
from ui.worker import (
    AutoTestWorker, ReloadSettingWorker, RecoverEnvironment, ModifyConfigWordWorker, ReleaseWorker, GenTestCaseWorker,
    LowCaseTransWorker, DeploySilNode, UndeploySilNode, DDSFuzzTest, FlaskThread
)
from ui.widgets import (
    CustomListWidget, CustomTableWidget, CustomTabBar, PopupView, ErrorDialog, CustomerLogArea, ECUSelectionDialog,
    CustomSplashScreen, SilConnectionLabel, DDSFuzzDatePickerDialog, HTMLStatic
)
from ui.startup import PlatformConfigurationDialog

# 这一部分是为了解决pyxcp模块打包后日志的问题
# 在程序入口处添加以下代码
import colorama
colorama.deinit()  # 关闭colorama的ANSI转换
# 在加载A2L配置前显式配置logging
import logging.config
logging.config.dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'DEBUG',
            'formatter': 'simple'
        },
    },
    'formatters': {
        'simple': {
            'format': '%(asctime)s | %(levelname)s | %(name)s: %(message)s'
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console']
    }
})

# 支持高dpi缩放
QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

# 软件版本号
with open(os.path.join(work_dir, '.version'), 'r', encoding='utf-8') as f:
    __version__ = f.read()


class MainWindow(QMainWindow):
    def __init__(self, backend_thread=None):
        super().__init__()
        self.sil_connection_light = {
            0: '🔴 sil 未部署',
            1: '🟢 sil 已连接',
            2: '🟡 sil 连接中断 重连中...'
        }
        self.q_backend_thread = backend_thread
        self.current_doip_env_mode = 0
        case_filenames = TestHandle.get_filename_from_dir(env.case_dir, 'xlsm')
        self.case_filepaths = [os.path.join(env.case_dir, case_filename) for case_filename in case_filenames]
        # 初始化主窗口和菜单栏
        self.init_window()
        self.init_menu()
        # 添加一个工具栏
        self.toolbar = self.addToolBar('Toolbar')
        self.toolbar.setIconSize(QSize(20, 20))
        # 创建动作 QAction
        self.new_tool = QAction(QIcon('ui/icons/Add_black.svg'), '', self)
        self.new_tool.setToolTip('新建')
        self.new_tool.triggered.connect(self.add_tab)
        self.open_tool = QAction(QIcon('ui/icons/Folder_black.svg'), '', self)
        self.open_tool.setToolTip('打开')
        self.open_tool.triggered.connect(self.open_configuration)
        self.save_tool = QAction(QIcon('ui/icons/Save_black.svg'), '', self)
        self.save_tool.setToolTip('保存')
        self.save_tool.triggered.connect(self.save_configuration)
        self.run_tool = QAction(QIcon('ui/icons/PlaySolid_black.svg'), '', self)  # 不显示文本
        self.run_tool.setToolTip('运行')  # 鼠标悬停时显示文本
        self.run_tool.triggered.connect(self.input_table_process)  # 连接到run_btn原有的功能
        self.reload_tool = QAction(QIcon('ui/icons/Sync_black.svg'), '', self)
        self.reload_tool.setToolTip('更新配置')
        self.reload_tool.triggered.connect(self.reload_setting)
        self.remote_tool_color = 'black'
        self.remote_tool = QAction(QIcon(f'ui/icons/Connect_{self.remote_tool_color}.svg'), '', self)
        self.remote_tool.setToolTip('远程执行 打开/关闭')
        self.remote_tool.triggered.connect(self.remote_execute_listen)
        self.recover_tool = QAction(QIcon('ui/icons/EraseTool_black.svg'), '', self)
        self.recover_tool.setToolTip('还原常规环境')
        self.recover_tool.triggered.connect(self.recover_environment)

        # 如果需要工具栏文本一直显示，可以使用setToolButtonStyle方法
        # self.toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        # 设置工具栏样式为图标样式，即仅显示图标，不显示文本
        self.toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        # 将动作添加到工具栏
        self.toolbar.addAction(self.new_tool)
        self.toolbar.addAction(self.open_tool)
        self.toolbar.addAction(self.save_tool)
        self.toolbar.addAction(self.run_tool)
        self.toolbar.addAction(self.reload_tool)
        self.toolbar.addAction(self.remote_tool)
        self.toolbar.addAction(self.recover_tool)

        # 创建一个包含你的备选文本列表的字符串列表模型
        self.signal_list_model = QStringListModel()

        # 手动调试标签页
        self.tabs = QTabWidget()
        self.tables = {}
        self.tab_label_num = 1
        self.current_file_paths = {}
        self.current_right_table = None
        self.left_table_widget = None
        self.right_table_widget = None
        self.tabs.setTabBar(CustomTabBar())
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)  # 自动传递标签页索引

        # 创建日志滚动区域
        self.log_scroll_area = CustomerLogArea()
        self.log_scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 主窗口控件与布局 将 tabs 和 log_scroll_area 添加到 splitter 控件中
        self.main_splitter = QSplitter(Qt.Vertical)  # 使用垂直分割器
        self.main_splitter.addWidget(self.tabs)
        self.main_splitter.addWidget(self.log_scroll_area)

        # 状态信息和脚标
        self.footer_widget = QWidget()
        self.footer_layout = QHBoxLayout()
        self.footer_widget.setLayout(self.footer_layout)
        self.sil_connection_label = SilConnectionLabel(self, f'{self.sil_connection_light[env.sil_node_status]}')
        self.sil_connection_label.setAlignment(Qt.AlignCenter)
        self.footer_layout.addWidget(self.sil_connection_label)
        self.footer_layout.addStretch(1)  # 插入一个弹性空间
        self.status_label = QLabel('')
        self.status_label.setAlignment(Qt.AlignLeft)
        self.footer_layout.addWidget(self.status_label)
        self.footer_layout.addStretch(1)  # 插入一个弹性空间
        self.foot_label = QLabel(f"整车电动-车辆控制-李琨 | {__version__}")
        self.foot_label.setAlignment(Qt.AlignRight)
        self.footer_layout.addWidget(self.foot_label)
        # 创建一个新的垂直布局
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.main_splitter, 1)  # splitter 占据布局中的大部分空间
        self.layout.addWidget(self.footer_widget, 0)  # foot_label 位于底部，没有额外的空间
        # 创建一个存储布局的中心窗口控件，并将其设置为 MainWindow 的中心控件
        self.window = QWidget()
        self.window.setLayout(self.layout)
        self.setCentralWidget(self.window)

        # 添加主页
        self.add_home_tab()
        # 连接 currentChanged 信号和 switch_current_tab 方法
        self.tabs.currentChanged.connect(self.switch_current_tab)
        # 初始化手动窗口输出值更新定时器
        self.timer_right_value = QTimer(self)
        self.timer_right_value.timeout.connect(self.update_right_values)
        self.timer_right_value.setInterval(200)
        # 初始化Home执行文本信息更新定时器
        self.timer_home = QTimer(self)
        self.timer_home.timeout.connect(self.set_auto_run_text)
        self.timer_home.setInterval(500)
        # 初始化显示sil仿真连接情况
        self.display_sil_connection = QTimer(self)
        self.display_sil_connection.timeout.connect(
            lambda: self.sil_connection_label.setText(f'{self.sil_connection_light[env.sil_node_status]}')
        )
        self.display_sil_connection.start(1000)
        # 自动化测试线程 禁用和解禁一些按钮
        self.auto_test_worker = AutoTestWorker(self)
        self.auto_test_worker.started.connect(self.on_auto_test_start)
        self.auto_test_worker.finished.connect(self.on_auto_test_finish)
        self.auto_test_worker.suite_result_path.connect(self.display_result_html_path)
        # 加载配置线程
        self.reload_setting_worker = ReloadSettingWorker(self)
        self.reload_setting_worker.display_case_path_signal.connect(self.display_case_paths)
        self.reload_setting_worker.started.connect(lambda: self.status_label.setText("🟡 正在更新并初始化配置，请稍后..."))
        self.reload_setting_worker.finished.connect(self.on_handle_task_finished)
        # 修改配置字线程
        self.modify_cw_worker = ModifyConfigWordWorker(self)
        self.modify_cw_worker.finished.connect(self.set_sw_info_text)
        # 恢复环境线程
        self.recover_env_task = RecoverEnvironment(self)
        self.recover_env_task.started.connect(lambda: self.recover_tool.setEnabled(False))
        self.recover_env_task.started.connect(lambda: self.status_label.setText("🟡 正在还原当前测试环境为正常环境，请稍后..."))
        self.recover_env_task.finished.connect(lambda: self.recover_tool.setEnabled(True))
        self.recover_env_task.finished.connect(self.on_handle_task_finished)
        # 资源释放线程
        self.release_work = ReleaseWorker(self)
        self.release_work.finished.connect(self.on_cleanup_finished)
        # 部署sil-node线程
        self.deploy_sil_node_task = DeploySilNode(self)
        self.deploy_sil_node_task.started.connect(lambda: self.recover_tool.setEnabled(False))
        self.deploy_sil_node_task.started.connect(lambda: self.status_label.setText("🟡 正在部署sil仿真节点，请稍后..."))
        self.deploy_sil_node_task.finished.connect(lambda: self.recover_tool.setEnabled(True))
        self.deploy_sil_node_task.finished.connect(self.on_handle_task_finished)
        # 移除sil-node线程
        self.undeploy_sil_node_task = UndeploySilNode(self)
        self.undeploy_sil_node_task.started.connect(lambda: self.recover_tool.setEnabled(False))
        self.undeploy_sil_node_task.started.connect(lambda: self.status_label.setText("🟡 正在移除sil仿真节点，请稍后..."))
        self.undeploy_sil_node_task.finished.connect(lambda: self.recover_tool.setEnabled(True))
        self.undeploy_sil_node_task.finished.connect(self.on_handle_task_finished)
        # dds模糊测试线程
        self.dds_fuzz_thread = None
        # 创建一个手动调试页
        logger.info('创建手动调试页')
        self.add_tab()
        self.switch_current_tab()
        logger.info('初始化时默认打开远程执行开关')
        # 初始化时默认打开远程执行开关
        self.remote_execute_listen()
        # 启动Flask服务器
        self.flask_thread = FlaskThread(self)
        self.flask_thread.start()

        # 初始化时更新界面数据
        self.set_auto_run_text()

    def init_window(self):
        self.resize(env.width, env.height)
        # self.setMinimumWidth(600)
        self.setWindowTitle('SOA A核测试工具')
        self.setWindowIcon(QIcon('ui/icons/icon.ico'))
        desktop = QApplication.desktop().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

    def init_menu(self):
        self.menu_bar = self.menuBar()
        file_menu = self.menu_bar.addMenu('文件')
        add_new_table = QAction('新建', self)
        add_new_table.triggered.connect(self.add_tab)
        open_table = QAction('打开', self)
        open_table.triggered.connect(self.open_configuration)
        save_action = QAction('保存', self)
        save_action.setShortcut('Ctrl+S')
        save_action.triggered.connect(self.save_configuration)  # 连接到保存配置的函数
        save_as_action = QAction('另存为', self)
        save_as_action.triggered.connect(self.save_configuration_as)  # 连接到保存配置的函数
        file_menu.addAction(add_new_table)
        file_menu.addAction(open_table)
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)

        tool_menu = self.menu_bar.addMenu('工具')
        # 添加仿真环境启动菜单选项
        doip_env_menu = tool_menu.addMenu('DoIP仿真环境')
        doip_env_group = QActionGroup(self)
        doip_env_group.setExclusive(True)  # 互斥 保证只能选一个
        doip_env_close = QAction('关闭', self)
        doip_env_close.setCheckable(True)
        doip_env_close.triggered.connect(lambda: self.doip_env_setup(0))
        doip_env_group.addAction(doip_env_close)
        doip_env_menu.addAction(doip_env_close)
        doip_env_open = QAction('开启', self)
        doip_env_open.setCheckable(True)
        doip_env_open.triggered.connect(lambda: self.doip_env_setup(1))
        doip_env_group.addAction(doip_env_open)
        doip_env_menu.addAction(doip_env_open)
        doip_env_close.setChecked(True)
        self.current_doip_env_mode = 0  # 默认仿真环境关闭

        # 添加车模式仿真ECU配置菜单选项
        vehicle_mode_ecu_menu = tool_menu.addAction('车辆模式ECU选择')
        vehicle_mode_ecu_menu.triggered.connect(self.show_vehicle_mode_ecu_selection)

        # 添加dds模糊测试任务开关
        dds_fuzz_menu = tool_menu.addMenu('DDS模糊测试')
        self.dds_fuzz_start_action = QAction('启动', self)
        self.dds_fuzz_start_action.triggered.connect(self.show_dds_fuzz_datetime_dialog)
        self.dds_fuzz_stop_action = QAction('停止', self)
        self.dds_fuzz_stop_action.setEnabled(False)
        self.dds_fuzz_stop_action.triggered.connect(self.stop_dds_fuzz)
        dds_fuzz_menu.addAction(self.dds_fuzz_start_action)
        dds_fuzz_menu.addAction(self.dds_fuzz_stop_action)

    def show_dds_fuzz_datetime_dialog(self):
        self.datetime_picker_dialog = DDSFuzzDatePickerDialog(self)
        self.datetime_picker_dialog.datetime_selected.connect(self.start_dds_fuzz)
        self.datetime_picker_dialog.exec_()

    def start_dds_fuzz(self, end_time):
        self.dds_fuzz_start_action.setEnabled(False)
        self.dds_fuzz_stop_action.setEnabled(True)
        self.dds_fuzz_thread = DDSFuzzTest(end_time)
        self.dds_fuzz_thread.started.connect(
            lambda: self.status_label.setText(
                f"🟡 正在执行dds模糊测试 截止时间: {end_time.toString('yyyy-MM-dd HH:mm:ss')} ..."
            )
        )
        self.dds_fuzz_thread.finished.connect(self.dds_fuzz_finished)
        self.dds_fuzz_thread.finished.connect(self.on_handle_task_finished)
        self.dds_fuzz_thread.start()

    def stop_dds_fuzz(self):
        if self.dds_fuzz_thread and self.dds_fuzz_thread.isRunning():
            self.dds_fuzz_thread.stop()

    def dds_fuzz_finished(self):
        self.dds_fuzz_thread = None
        self.dds_fuzz_start_action.setEnabled(True)
        self.dds_fuzz_stop_action.setEnabled(False)

    def recover_environment(self):
        self.recover_tool.setEnabled(False)
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setText("您确定要恢复测试前的环境吗?")
        msg_box.setWindowTitle("确认操作")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        reply = msg_box.exec_()
        if reply == QMessageBox.Yes:
            self.recover_env_task.start()
        else:
            self.recover_tool.setEnabled(True)

    def remote_execute_listen(self):
        """
        监听tcp消息，目前用于远程执行
        """
        try:
            if self.remote_tool_color == 'black':
                self.tcp_server = QTcpServer(self)
                logger.info('TCP Server open.')
                if not self.tcp_server.listen(QHostAddress.LocalHost, 36666):
                    logger.error(f'Failed to listen: {self.errorString()}')
                    self.tcp_server.close()
                else:
                    logger.success('Listening successfully.')
                    self.tcp_server.newConnection.connect(self.new_socket_slot)
                self.remote_tool_color = 'green'
            else:
                logger.info('TCP Server closed.')
                self.tcp_server.close()
                self.remote_tool_color = 'black'
            self.remote_tool.setIcon(QIcon(f'ui/icons/Connect_{self.remote_tool_color}.svg'))
        except:
            logger.error(traceback.format_exc())

    def new_socket_slot(self):
        sock = self.tcp_server.nextPendingConnection()
        peer_address = sock.peerAddress().toString()
        peer_port = sock.peerPort()
        logger.info('Connected with address {}, port {}'.format(peer_address, str(peer_port)))
        # lambda 表达式捕获 sock 变量时可能会导致意外的行为，尤其是当 sock 变量在循环或异步调用中改变时
        # partial 函数返回的是一个新的callable对象，这个对象在调用时会将原函数配合原函数所需的参数一并调用。
        sock.readyRead.connect(partial(self.read_tcp_data_slot, sock))
        sock.disconnected.connect(partial(self.disconnected_tcp_slot, sock))

    def read_tcp_data_slot(self, sock):
        """
        远程执行触发槽函数
        """
        try:
            while sock.bytesAvailable():
                datagram = sock.read(sock.bytesAvailable())
                message = datagram.decode().strip()
                logger.info(f'tcp server recv: {message}')
                parse_data = json.loads(message)
                event_type = parse_data.get('event_type', None)
                if event_type == 'remote_autotest':
                    event_data = parse_data.get('event_data')
                    env.remote_event_data = event_data  # 远程执行参数信息
                    if event_data.get('case_path') and not self.auto_test_worker.isRunning():
                        # 切换至自动化页面
                        if self.tabs.currentIndex() != 0:
                            self.tabs.setCurrentIndex(0)
                        # 执行自动化测试
                        self.auto_test_worker.start()
        except:
            logger.error(traceback.format_exc())

    def disconnected_tcp_slot(self, sock):
        try:
            peer_address = sock.peerAddress().toString()
            peer_port = sock.peerPort()
            logger.info('Disconnected with address {}, port {}'.format(peer_address, str(peer_port)))
            sock.close()
        except Exception as e:
            logger.error(e)

    def enable_buttons(self, enable=True):
        """
        自动化测试过程中禁用一些按钮
        """
        self.reload_tool.setEnabled(enable)
        self.select_setting_btn.setEnabled(enable)
        self.select_case_btn.setEnabled(enable)
        self.remote_tool.setEnabled(enable)

    def show_gen_testcase_dialog(self):
        # 弹出输入对话框
        project_name, ok = QInputDialog.getText(self, '用例生成', '请输入项目名称(不区分大小写):')
        # 判断用户是否点击了确认
        if ok:
            # 处理用户的输入，此处只是打印到控制台
            logger.info(f'用例项目名称: {project_name}')
            self.gen_testcase_worker = GenTestCaseWorker(self, self.case_filepaths, project_name)
            self.gen_testcase_worker.started.connect(lambda: self.status_label.setText("🟡 正在将当前用例重新生成，请稍后..."))
            self.gen_testcase_worker.finished.connect(self.on_handle_task_finished)
            self.gen_testcase_worker.start()

    def show_trans_testcase_dialog(self):
        # 弹出目录选择对话框
        directory = QFileDialog.getExistingDirectory(self, "选择保存路径", "")
        if directory:
            self.trans_testcase_worker = LowCaseTransWorker(self, self.case_filepaths, save_dir=directory)
            self.trans_testcase_worker.started.connect(lambda: self.status_label.setText("🟡 正在将当前用例进行信号格式转换，请稍后..."))
            self.trans_testcase_worker.finished.connect(self.on_handle_task_finished)
            self.trans_testcase_worker.display_paths_signal.connect(self.display_case_paths)
            self.trans_testcase_worker.start()

    def on_handle_task_finished(self):
        # 移除提示信息
        self.status_label.setText('')
        # 显示任务完成的信息框
        # QMessageBox.information(self, "完成", "任务执行完成！")

    def show_vehicle_mode_ecu_selection(self):
        # 在点击时显示对话框
        dialog = ECUSelectionDialog(self, self.select_vehicle_mode_simulation)
        # dialog.exec_()  # 显示为模态对话框 会阻塞主窗口操作
        dialog.show()  # 显示非模态对话框 不影响主窗口操作

    def select_vehicle_mode_simulation(self, ecu_name, option_state):
        if option_state:
            state = 0
            option_desc = '开启'
        else:
            state = 1
            option_desc = '关闭'
        logger.info(f'设置车辆模式ECU仿真:{ecu_name} {option_desc}')
        VehicleModeDiagnostic.set_state(ecu_name, state)

    def doip_env_setup(self, status: int):
        """
        status:
            0: DoIP仿真环境关闭
            1: DoIP仿真环境打开
        action:
            选项
        """
        if self.current_doip_env_mode == status:
            return
        self.current_doip_env_mode = status
        env.tester.ssh_connector.setup_vcs_ip_config(status)

    def switch_current_tab(self):
        # 当前标签页切换时调用的函数 tab全都关闭以后索引是0(home页)
        current_tab_index = self.tabs.currentIndex()
        if not self.tables or current_tab_index < 1 or current_tab_index >= self.tabs.count():
            self.current_right_table = None
            if self.timer_right_value.isActive():
                self.timer_right_value.stop()
        else:
            # TODO 这一步是个大Bug 这个时候可能 self.tables中的索引还没销毁完 当前已有临时处理方法 后续解决
            _, self.current_right_table = self.tables[current_tab_index]
            if not self.timer_right_value.isActive():
                self.timer_right_value.start()

    def save_configuration_as(self):
        try:
            # 获取当前选项卡的标签名称
            current_tab_index = self.tabs.currentIndex()
            current_tab_text = self.tabs.tabText(current_tab_index)
            filepath, _ = QFileDialog.getSaveFileName(
                self, "Save Configuration", current_tab_text,
                "AutoLi SiL Files (*.li);;All Files (*)"
            )
            if filepath:
                self.current_file_paths[current_tab_index] = filepath
                left_table, right_table = self.tables[current_tab_index]
                file_content = {'input': [], 'output': []}

                for row in range(left_table.rowCount()):
                    signal = left_table.cellWidget(row, 0).text() if left_table.cellWidget(row, 0) else ""
                    value = left_table.item(row, 1).text() if left_table.item(row, 1) else ""
                    file_content['input'].append({'signal': signal, 'value': value})
                    # f.write(f'1;;{signal};;{value}\n')
                for row in range(right_table.rowCount()):
                    signal = right_table.cellWidget(row, 0).text() if right_table.cellWidget(row, 0) else ""
                    value = right_table.item(row, 1).text() if right_table.item(row, 1) else ""
                    file_content['output'].append({'signal': signal, 'value': value})
                        # f.write(f'2;;{signal};;{value}\n')
                # 转成yaml格式
                yaml_str = yaml.dump(file_content, allow_unicode=True)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(yaml_str)
                # 另存完后改名
                saved_tab_name = os.path.splitext(os.path.basename(filepath))[0]
                self.tabs.setTabText(current_tab_index, saved_tab_name)
        except:
            logger.error(traceback.format_exc())

    def save_configuration(self):
        try:
            current_tab_index = self.tabs.currentIndex()
            if current_tab_index > 0:  # 保存手动调试配置
                current_file_path = self.current_file_paths[current_tab_index]
                if current_file_path == '':  # 如果当前文件路径为空就另存
                    self.save_configuration_as()
                else:
                    left_table, right_table = self.tables[current_tab_index]
                    file_content = {'input': [], 'output': []}
                    for row in range(left_table.rowCount()):
                        signal = left_table.cellWidget(row, 0).text() if left_table.cellWidget(row, 0) else ""
                        value = left_table.item(row, 1).text() if left_table.item(row, 1) else ""
                        file_content['input'].append({'signal': signal, 'value': value})
                    for row in range(right_table.rowCount()):
                        signal = right_table.cellWidget(row, 0).text() if right_table.cellWidget(row, 0) else ""
                        value = right_table.item(row, 1).text() if right_table.item(row, 1) else ""
                        file_content['output'].append({'signal': signal, 'value': value})
                    # 转成yaml格式
                    yaml_str = yaml.dump(file_content, allow_unicode=True)
                    with open(current_file_path, 'w', encoding='utf-8') as f:
                        f.write(yaml_str)
        except:
            logger.error(traceback.format_exc())

    def open_configuration(self):
        try:
            # 加载配置的函数
            filepath, _ = QFileDialog.getOpenFileName(
                self, "Open Configuration",
                "", "AutoLi SiL Files (*.li);;All Files (*)"
            )
            if filepath:
                tab_name = os.path.splitext(os.path.basename(filepath))[0]
                self.add_tab(tab_name=tab_name)
                current_tab_index = self.tabs.currentIndex()
                # 更新当前标签页的文件路径
                self.current_file_paths[current_tab_index] = filepath
                left_table, right_table = self.tables[current_tab_index]
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    left_lines = data.get('input')
                    right_lines = data.get('output')
                    num_left_rows = len(left_lines) if left_lines else 0
                    num_right_rows = len(right_lines) if right_lines else 0

                    # lines = f.readlines()
                    # # 分别加载输入和输出的表格
                    # num_left_rows = 0
                    # num_right_rows = 0
                    # left_lines = []
                    # right_lines = []
                    # for row, line in enumerate(lines):
                    #     table_type, signal, value = line.strip().split(';;')
                    #     if table_type == '1':
                    #         num_left_rows += 1
                    #         left_lines.append((signal, value))
                    #     else:
                    #         num_right_rows += 1
                    #         right_lines.append((signal, value))

                    # 首先确定行数，如果需要的话，添加额外的行
                    num_left_rows_needed = num_left_rows - left_table.rowCount()
                    for _ in range(num_left_rows_needed):
                        self.insert_left_row(left_table)
                        QApplication.processEvents()  # 强制处理未完成的事件

                    num_right_rows_needed = num_right_rows - right_table.rowCount()
                    for _ in range(num_right_rows_needed):
                        self.insert_right_row(right_table)
                        QApplication.processEvents()  # 强制处理未完成的事件

                    # 然后加载表格数据
                    for row, line in enumerate(left_lines):
                        signal, value = line['signal'], line['value']
                        # left_table.cellWidget(row, 0).setCheckState(int(checkbox_state))
                        left_table.cellWidget(row, 0).setText(signal)
                        if not left_table.item(row, 1):  # 防止这行没有单元格项目
                            left_table.setItem(row, 1, QTableWidgetItem())
                        left_table.item(row, 1).setText(value)
                    for row, line in enumerate(right_lines):
                        signal, value = line['signal'], line['value']
                        right_table.cellWidget(row, 0).setText(signal)
        except:
            logger.error(traceback.format_exc())

    def keyPressEvent(self, event):
        # 按下Ctrl+S 保存配置
        if event.key() == Qt.Key_S and int(event.modifiers()) == Qt.ControlModifier:
            self.save_configuration()
        super().keyPressEvent(event)

    def update_signal_list_model(self):
        """
        使用vars_mapping的新键更新 QStringListModel
        """
        self.signal_list_model.setStringList(list(Variable.get_var_keys()))

    def input_table_process(self):
        """
        运行按钮触发的槽函数，执行手动或自动化测试
        新版 默认找到值变化的信号发送
        """
        current_table_index = self.tabs.currentIndex()
        # 手动调试窗口
        if current_table_index >= 1:
            # 从字典中获取当前选项卡的左、右 table_widget
            left_table_widget, right_table_widget = self.tables[current_table_index]
            # 取消table焦点 防止处于编辑中的数据不生效
            left_table_widget.clearFocus()
            left_table_widget.setFocus()
            for row in range(left_table_widget.rowCount()):
                signal_name = left_table_widget.cellWidget(row, 0).text() if left_table_widget.cellWidget(row, 0) else ""
                # 假设“值”列的数据是直接以文字形式储存在单元格里的
                value = left_table_widget.item(row, 1).text()
                if signal_name and value != '':
                    try:
                        signal = Variable(signal_name)
                        signal_value = CaseTester.convert_signal_value(value)
                        if signal_value is None:
                            raise Exception(f'{signal.name}={signal_value} value convert error')
                        # if signal.data_array[-1] != signal_value:  # 当前值有修改则发送, 2024.02.20 沟通需求确认均发送
                        signal.Value = signal_value
                        env.tester.send_single_msg(signal, async_mode=True)
                    except Exception as e:
                        logger.error(e)
                        logger.error(traceback.format_exc())
        else:
            # 自动化测试执行窗口
            if not self.auto_test_worker.isRunning():
                # 没有进行测试，开始测试
                self.auto_test_worker.start()
            else:
                # 已经有测试在运行，需要告诉它停止
                logger.info('自动化测试终止')
                TestHandle.run_state = '停止中'
                env.stop_autotest = True
                self.run_tool.setEnabled(False)

    def input_table_combine(self):
        """
        回车按下时，聚合发送：同一topic下的信号set_value完以后在write过去
        """
        current_table_index = self.tabs.currentIndex()
        # 手动调试窗口
        if current_table_index >= 1:
            # 从字典中获取当前选项卡的左、右 table_widget
            left_table_widget, right_table_widget = self.tables[current_table_index]
            # 取消table焦点 防止处于编辑中的数据不生效
            left_table_widget.clearFocus()
            left_table_widget.setFocus()
            # 依次查找一组dds消息，按顺序发送，先到先得
            dds_multi_signals = {}
            for row in range(left_table_widget.rowCount()):
                signal_name = left_table_widget.cellWidget(row, 0).text() if left_table_widget.cellWidget(row, 0) else ""
                # 假设“值”列的数据是直接以文字形式储存在单元格里的
                value = left_table_widget.item(row, 1).text()
                if signal_name and value != '':
                    try:
                        signal = Variable(signal_name)
                        signal_value = CaseTester.convert_signal_value(value)
                        if signal_value is None:
                            raise Exception(f'{signal.name}={signal_value} value convert error')
                        signal.Value = signal_value

                        if not any(signal.name.startswith(prefix) for prefix in CaseTester.non_dds_prefix):  # 添加DDS信号组
                            topic_name = env.tester.dds_connector.signal_map[signal_name]
                            if topic_name and topic_name not in dds_multi_signals:
                                dds_multi_signals[topic_name] = []
                                dds_multi_signals[topic_name].append(signal)
                            else:
                                dds_multi_signals[topic_name].append(signal)
                        else:  # 不是dds的直接发送
                            env.tester.send_single_msg(signal, async_mode=True)
                    except Exception as e:
                        logger.error(traceback.format_exc())
                        logger.error(e)
            # 最后依次发送dds信号组
            for tpn, s in dds_multi_signals.items():
                if tpn and s:
                    env.tester.dds_connector.dds_multi_send(
                        topic_name=tpn,
                        signals=s
                    )

    def insert_left_row(self, table_widget):
        row_position = table_widget.rowCount()
        table_widget.insertRow(row_position)
        # 为新行的 "信号" 列添加 QLineEdit 编辑器和 QCompleter
        completer = QCompleter()
        completer.setModel(self.signal_list_model)  # 这里假设你在类中存储了模型
        completer.setFilterMode(Qt.MatchContains)  # 支持模糊搜索，没有的话默认是起始位置搜索
        completer.setCaseSensitivity(Qt.CaseInsensitive)  # 不区分大小写
        line_edit = QLineEdit()
        # 下拉补齐补全器展示所有内容
        popup_view = PopupView()
        completer.setPopup(popup_view)
        line_edit.setCompleter(completer)
        table_widget.setCellWidget(row_position, 0, line_edit)  # 信号列
        table_widget.setItem(row_position, 1, QTableWidgetItem())  # 这里添加一个空的QTableWidgetItem

    def insert_right_row(self, table_widget):
        # 插入右侧表格的新行的函数
        row_position = table_widget.rowCount()
        table_widget.insertRow(row_position)
        completer = QCompleter()
        completer.setModel(self.signal_list_model)
        completer.setFilterMode(Qt.MatchContains)  # 支持模糊搜索，没有的话默认是起始位置搜索
        completer.setCaseSensitivity(Qt.CaseInsensitive)  # 不区分大小写
        line_edit = QLineEdit()
        # 下拉补齐补全器展示所有内容
        popup_view = PopupView()
        completer.setPopup(popup_view)
        line_edit.setCompleter(completer)
        table_widget.setCellWidget(row_position, 0, line_edit)
        # 为新行的 "值" 列禁止编辑
        item = QTableWidgetItem()
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        table_widget.setItem(row_position, 1, item)

    def delete_row(self, table_widget):
        # 删除按钮的函数
        index_list = []
        for model_index in table_widget.selectionModel().selectedRows():
            index = QtCore.QPersistentModelIndex(model_index)
            index_list.append(index)
        for index in index_list:
            table_widget.removeRow(index.row())

    def update_right_values(self):
        """
        由于 self.current_right_table 被 close_table和switch_current_tab两个异步方法处理后对象实际已经不存在了
        """
        if self.current_right_table is None or sip.isdeleted(self.current_right_table):
            return
        try:
            for i in range(self.current_right_table.rowCount()):
                signal_name = self.current_right_table.cellWidget(i, 0).text() if self.current_right_table.cellWidget(i, 0) else ""
                if signal_name:
                    signal_value = Variable(signal_name).Value
                    self.current_right_table.takeItem(i, 1)
                    self.current_right_table.setItem(i, 1, QTableWidgetItem(str(signal_value)))
        except Exception as e:
            logger.error(e)
            self.switch_current_tab()

    def create_left_table(self):
        """
        新版逻辑 设置勾选框 只发送勾选的信号
        """
        # 创建一个 QLabel 作为输入的标签，并将标签和复选框添加到一个水平布局中
        label = QLabel('输入')
        label.setAlignment(Qt.AlignCenter)
        self.left_table_widget = table_widget = CustomTableWidget(self, 3, 2)
        # 设置表头为自定义的 CheckBoxHeader
        # table_widget.setHorizontalHeader(CheckBoxHeader(table_widget))
        # 设置表头标签
        table_widget.setHorizontalHeaderLabels(['信号', '值'])
        # 设置列的大小策略
        header = table_widget.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)

        for i in range(table_widget.rowCount()):
            # 信号这一列支持搜索补全功能
            completer = QCompleter()
            completer.setModel(self.signal_list_model)  # 设置为刚才创建的字符串列表模型
            completer.setFilterMode(Qt.MatchContains)  # 支持模糊搜索，没有的话默认是起始位置搜索
            completer.setCaseSensitivity(Qt.CaseInsensitive)  # 不区分大小写
            line_edit = QLineEdit()
            # 下拉补齐补全器展示所有内容
            popup_view = PopupView()
            completer.setPopup(popup_view)
            # 设置完成器
            line_edit.setCompleter(completer)
            # 用它替换默认的编辑器
            table_widget.setCellWidget(i, 0, line_edit)
            table_widget.setItem(i, 1, QTableWidgetItem())  # 这里添加一个空的QTableWidgetItem

        add_row_btn = QPushButton("添加行", self)
        add_row_btn.clicked.connect(lambda: self.insert_left_row(table_widget))
        delete_row_btn = QPushButton("删除行", self)
        delete_row_btn.clicked.connect(lambda: self.delete_row(table_widget))
        # 创建一个 QVBoxLayout，并添加 QLabel 和 QTableWidget
        layout = QVBoxLayout()
        layout.addWidget(label)
        layout.addWidget(table_widget)
        layout.addWidget(add_row_btn)
        layout.addWidget(delete_row_btn)
        # 创建一个 QWidget，设置其布局为前面创建的 QVBoxLayout
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def create_right_table(self):
        label = QLabel('输出')
        label.setAlignment(Qt.AlignCenter)  # 设置对齐方式为居中
        self.right_table_widget = table_widget = QTableWidget(3, 2)  # 形如3行3列的QTableWidget
        table_widget.resizeColumnsToContents()
        # 设置表头
        table_widget.setHorizontalHeaderLabels(['信号', '值'])
        # 设置列的大小策略
        header = table_widget.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        for i in range(table_widget.rowCount()):
            # 信号这一列支持搜索补全功能
            completer = QCompleter()
            completer.setModel(self.signal_list_model)  # 设置为刚才创建的字符串列表模型
            completer.setFilterMode(Qt.MatchContains)  # 支持模糊搜索，没有的话默认是起始位置搜索
            completer.setCaseSensitivity(Qt.CaseInsensitive)  # 不区分大小写
            line_edit = QLineEdit()
            # 下拉补齐补全器展示所有内容
            popup_view = PopupView()
            completer.setPopup(popup_view)
            line_edit.setCompleter(completer)  # 设置完成器
            table_widget.setCellWidget(i, 0, line_edit)  # 用它替换默认的编辑器

            # 为“值”列的每个单元格禁用编辑
            item = QTableWidgetItem("")
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)  # 禁用 ItemIsEditable 属性
            table_widget.setItem(i, 1, item)  # 若假设“值”列是第二列，即索引为 1 的列
        # 添加一个按钮，用于添加新的行
        add_row_btn = QPushButton("添加行", self)
        add_row_btn.clicked.connect(lambda: self.insert_right_row(table_widget))
        # 删除行
        delete_row_btn = QPushButton("删除行", self)
        delete_row_btn.clicked.connect(lambda: self.delete_row(table_widget))
        layout = QVBoxLayout()
        layout.addWidget(label)
        layout.addWidget(table_widget)
        layout.addWidget(add_row_btn)
        layout.addWidget(delete_row_btn)
        # 创建一个 QWidget，设置其布局为前面创建的 QVBoxLayout
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def create_tab_content(self):
        layout = QHBoxLayout()
        layout.addWidget(self.create_left_table())  # 添加table到tab
        layout.addWidget(self.create_right_table())  # 添加table到tab
        content = QWidget()
        content.setLayout(layout)
        return content

    def add_home_tab(self):
        self.home_page = self.create_home_page()
        init_tab_index = self.tabs.addTab(self.home_page, "AutoTest")
        self.tables[init_tab_index] = (None, None)
        self.current_file_paths[init_tab_index] = ''
        self.tabs.setCurrentIndex(init_tab_index)
        # 隐藏关闭按钮
        self.tabs.tabBar().setTabButton(init_tab_index, QTabBar.RightSide, None)

    def create_home_page(self):
        home_page = QWidget(self)
        main_layout = QVBoxLayout(home_page)
        # 创建左右两部分的水平布局
        hlayout = QHBoxLayout()
        main_layout.addLayout(hlayout)
        # 左侧部分
        left_layout = QVBoxLayout()
        hlayout.addLayout(left_layout)

        # 左侧第一行
        l_setting_layout = QHBoxLayout()
        # 左侧第一行左边
        self.select_setting_btn = QPushButton('选择配置')
        self.select_setting_btn.clicked.connect(self.select_setting)
        l_setting_layout.addWidget(self.select_setting_btn)
        self.setting_file = QLineEdit()
        self.setting_file.setPlaceholderText(env.settings_filepath)
        l_setting_layout.addWidget(self.setting_file, 3)
        # 添加伸缩项分隔左右部分
        l_setting_layout.addStretch(1)
        # 右侧新增部分
        r_press_layout = QHBoxLayout()
        tag_label = QLabel("压测次数:")
        self.tag_input = QLineEdit()
        self.tag_input.setText('1')
        self.tag_input.textChanged.connect(self.handle_press_changed)  # 绑定文本改变信号
        r_press_layout.addWidget(tag_label)
        r_press_layout.addWidget(self.tag_input)
        l_setting_layout.addLayout(r_press_layout, stretch=1)
        left_layout.addLayout(l_setting_layout)

        # 左侧第二行
        l_case_layout = QVBoxLayout()
        l_case_btn_group_layout = QHBoxLayout()
        self.select_case_btn = QPushButton('加载用例')
        self.select_case_btn.clicked.connect(self.select_case)
        self.gen_case_btn = QPushButton('生成用例')
        self.gen_case_btn.clicked.connect(self.show_gen_testcase_dialog)
        self.trans_case_btn = QPushButton('转换用例(小写)')
        self.trans_case_btn.clicked.connect(self.show_trans_testcase_dialog)
        l_case_btn_group_layout.addWidget(self.select_case_btn)
        l_case_btn_group_layout.addWidget(self.gen_case_btn)
        l_case_btn_group_layout.addWidget(self.trans_case_btn)
        l_case_layout.addLayout(l_case_btn_group_layout)
        self.case_list_widget = CustomListWidget(self)
        self.case_list_widget.addItems(self.case_filepaths)
        l_case_layout.addWidget(self.case_list_widget)
        left_layout.addLayout(l_case_layout)
        # 左侧第三行
        l_sw_info_layout = QVBoxLayout()
        self.sw_info_text = QTextEdit()
        self.sw_info_text.setFont(QFont("Segoe UI", 10))  # 设置字体和字号
        self.sw_info_text.setReadOnly(True)
        # 显示当前软件信息
        l_sw_info_layout.addWidget(self.sw_info_text)
        left_layout.addLayout(l_sw_info_layout)
        # 右侧部分
        right_layout = QVBoxLayout()
        hlayout.addLayout(right_layout)
        # 右侧第一行
        cw_edit_layout = QHBoxLayout()
        cw_edit_btn = QPushButton('修改配置字')
        cw_edit_btn.clicked.connect(self.modify_config_word)
        self.cw_edit = QLineEdit()
        self.cw_edit.setPlaceholderText('<- 输入配置字并点击左侧按钮进行修改')
        cw_edit_layout.addWidget(cw_edit_btn)
        cw_edit_layout.addWidget(self.cw_edit)
        right_layout.addLayout(cw_edit_layout)
        # 右侧第二行
        process_layout = QHBoxLayout()
        process_label = QLabel('执行进度')
        process_layout.addWidget(process_label)
        self.process_bar = QProgressBar()
        self.process_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid grey;
                border-radius: 3px;
                text-align: center;
            }
            """)
        process_layout.addWidget(self.process_bar)
        right_layout.addLayout(process_layout)
        # 右侧第三行
        self.auto_run_text = QTextBrowser()
        self.auto_run_text.setFont(QFont("Consolas", 12))  # 设置字体和字号
        self.auto_run_text.setOpenExternalLinks(True)
        self.auto_run_text.setOpenLinks(False)
        self.auto_run_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)  # 确保 QTextBrowser 可以扩展
        right_layout.addWidget(self.auto_run_text, stretch=1)  # Add QWidget with stretch to allow expansion
        self.auto_run_text.anchorClicked.connect(self.open_link)   # 连接点击事件到队列函数

        # 右侧第四行
        self.result_path_text = QTextBrowser()
        self.result_path_text.setFont(QFont("Consolas", 12))  # 设置字体和字号
        self.result_path_text.setOpenExternalLinks(True)
        self.result_path_text.setOpenLinks(False)
        self.result_path_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)  # 确保 QTextBrowser 可以扩展
        self.result_path_text.anchorClicked.connect(self.open_link)  # 连接点击事件到队列函数
        right_layout.addWidget(self.result_path_text, stretch=1)  # Add QWidget with stretch to allow expansion

        # 设置布局的边距为0，使得布局之间紧密排布
        for layout in (main_layout, hlayout, left_layout, right_layout, l_setting_layout,
                       l_case_layout, l_sw_info_layout, process_layout):
            layout.setContentsMargins(0, 0, 0, 0)
        return home_page

    def open_link(self, url):
        logger.info(f'打开文件链接: {url}')
        # 解码 URL 中的特殊字符
        url_str = unquote(url.toString())

        # 打开链接到默认浏览器
        if url_str.startswith('file:///'):
            QDesktopServices.openUrl(QUrl(url_str))
        else:
            logger.warning(f'无效的URL: {url_str}')

    def modify_config_word(self):
        self.modify_cw_worker.start()

    def select_setting(self):
        # PyQt5中使用QFileDialog.getOpenFileName()方法选择一个文件
        # 参数依次是 窗口名字，起始路径，文件格式过滤器
        filepath, _ = QFileDialog.getOpenFileName(self, "选择配置文件", "", "Setting File (*.yaml);;All Files (*)")
        if filepath:
            env.settings_filepath = filepath
            self.setting_file.setText(filepath)

    def select_case(self):
        """
        加载用例按钮的槽函数
        """
        try:
            dialog = QFileDialog(self)
            dialog.setFileMode(QFileDialog.ExistingFiles)  # 可以选择多个文件
            dialog.setOption(QFileDialog.ShowDirsOnly, False)  # 可以选择文件夹
            # dialog.setOption(QFileDialog.DontUseNativeDialog, True)  # 使用Qt的标准文件选择器，而非操作系统的文件选择器
            dialog.setNameFilter("Excel files (*.xls *.xlsx *.xlsm)")  # 只显示和选择Excel文件
            if dialog.exec_():
                self.case_filepaths = dialog.selectedFiles()  # 获取选择的文件和文件夹名称的列表
                env.case_dir = os.path.normpath(os.path.dirname(self.case_filepaths[0]))
                self.display_case_paths()
        except:
            logger.error(traceback.format_exc())

    def display_case_paths(self, case_filepaths=None):
        if case_filepaths:
            if not isinstance(case_filepaths, list):
                error_message = f'用例路径类型错误: {case_filepaths}, type: {type(case_filepaths)}'
                ErrorDialog(error_message).exec_()
            self.case_filepaths = case_filepaths
        self.case_list_widget.clear()
        self.case_list_widget.addItems(self.case_filepaths)

    def reload_setting(self):
        # 获取现有配置文件路径
        self.reload_setting_worker.start()

    def on_auto_test_start(self):
        logger.info('开始自动化测试, 测试信息更新, 按钮置灰')
        if not self.timer_home.isActive():
            self.timer_home.start()
        # 禁用按钮
        self.enable_buttons(enable=False)
        # 更改按钮标识
        self.run_tool.setIcon(QIcon(f'ui/icons/Pause_black.svg'))
        self.run_tool.setToolTip('停止')

    def handle_press_changed(self, text):
        try:
            if not text:
                env.press_times = 1
            else:
                env.press_times = int(text)
        except:
            logger.error(f'请修改压测次数为正确的类型')
        else:
            logger.success(f'当前压测次数为: {env.press_times}')

    def on_auto_test_finish(self):
        try:
            logger.info(f'停止自动化测试, 测试信息停止更新, 按钮还原')
            if self.timer_home.isActive():
                self.timer_home.stop()
            # 停止完成后打开运行按钮
            self.run_tool.setEnabled(True)
            self.enable_buttons(enable=True)
            self.run_tool.setIcon(QIcon('ui/icons/PlaySolid_black.svg'))
            self.run_tool.setToolTip('运行')  # 鼠标悬停时显示文本
        except:
            logger.error(traceback.format_exc())

    def display_result_html_path(self, suite_result_paths):
        try:
            html_template = f"""
            <html>
            <head>
                <meta charset="UTF-8">
                {HTMLStatic.table_style} 
            </head>
            <body>
                <div class="container">
                    <table>
            """
            for status, result_path in suite_result_paths:
                filepath = result_path.replace('\\', '/')
                html_template += f"""<tr><td>{status}</td><td><a href="file:///{filepath}">{os.path.basename(result_path)}</a></td></tr>"""
            html_template += "</table></div></body></html>"
            self.result_path_text.setHtml(html_template)
        except:
            logger.error(traceback.format_exc())

    def set_env_testcase(self):
        try:
            # 远程执行触发参数
            if env.remote_event_data:
                case_path = env.remote_event_data['case_path']
                if case_path.startswith('http'):  # 从svn拉下来
                    env.remote_run = Run(
                        server=env.remote_event_data['server'],
                        task_id=env.remote_event_data['task_id'],
                        distribute_id=env.remote_event_data['distribute_id']
                    )
                    self.case_filepaths, result_case_path = env.remote_run.parse_case_by_svn_path(case_path)
                else:  # 直接获取本地路径
                    self.case_filepaths = glob.glob(os.path.normpath(os.path.join(case_path.replace('"', ''), '*.xlsm')))
                self.display_case_paths()  # 显示用例列表
                # env.remote_callback = CallBack()
            env.ddt_testcase = []
            for tc_filepath in self.case_filepaths:
                tc_filename = os.path.basename(tc_filepath)
                parser = CaseParser(tc_filepath=tc_filepath)
                all_testcase = parser.get_all_testcase()
                # 当前用例总数
                TestHandle.all_case_num += len(all_testcase)
                testcases = [
                    {
                        'case_name': key,
                        'case_info': val.get('test_steps'),
                        'case_title': val.get('case_name')
                    } for key, val in all_testcase.items()
                ]
                suite_info = {
                    'tc_filepath': tc_filepath,
                    'suite_name': os.path.splitext(tc_filename)[0],
                    'testcases': testcases
                }
                env.ddt_testcase.append(suite_info)
            env.ddt_test_index = 0
        except:
            logger.error(traceback.format_exc())

    def set_auto_run_text(self):
        """所有的GUI操作更新都要放在主线程中"""
        try:
            filepath_link = TestHandle.report_html_path.replace('\\', '/')
            html_template = f"""
            <html>
            <head>
                <meta charset="UTF-8">
                {HTMLStatic.table_style}        
            </head>
            <body>
                <div class="container">
                    <table>
                        <tr>
                            <td>执行时间</td>
                            <td>{TestHandle.start_time}</td>
                        </tr>
                        <tr>
                            <td>测试状态</td>
                            <td>{TestHandle.run_state}</td>
                        </tr>
                        <tr>
                            <td>用例总数</td>
                            <td>{TestHandle.all_case_num}</td>
                        </tr>
                        <tr>
                            <td>已经执行</td>
                            <td>{TestHandle.total_num}</td>
                        </tr>
                        <tr>
                            <td>通过数量</td>
                            <td>{TestHandle.pass_num}</td>
                        </tr>
                        <tr>
                            <td>失败数量</td>
                            <td>{TestHandle.fail_num}</td>
                        </tr>                        
                        <tr>
                            <td>通过率</td>
                            <td>{TestHandle.current_pass_rate}</td>
                        </tr>
                        <tr>
                            <td>当前用例</td>
                            <td>{TestHandle.current_running_case}</td>
                        </tr>
                        <tr>
                            <td>报告路径</td>
                            <td><a href="file:///{filepath_link}">{os.path.basename(TestHandle.report_html_path)}</a></td>
                        </tr>
            """
            html_template += "</table></div></body></html>"

            self.auto_run_text.setHtml(html_template)
            if TestHandle.all_case_num:
                self.process_bar.setValue(int(round(TestHandle.total_num / TestHandle.all_case_num, 2) * 100))
            else:
                self.process_bar.setValue(0)
        except Exception:
            logger.error(traceback.format_exc())

    def set_sw_info_text(self):
        """
        显示当前被测设备软件信息
        """
        try:
            html_template = f"""
            <html>
            <head>
                <meta charset="UTF-8">
                {HTMLStatic.table_style}        
            </head>
            <body>
                <div class="container">
                    <table>
            """
            for key, val in env.xcu_info.items():
                html_template += f'<tr><td>{key}</td><td>{val}</td></tr>'
            html_template += '</table></div></body></html>'
            self.sw_info_text.setHtml(html_template)
        except Exception:
            logger.error(traceback.format_exc())

    def add_tab(self, tab_name=''):
        if not tab_name:
            label_name = f"Tab {self.tab_label_num}"
            self.tab_label_num += 1
        else:
            label_name = tab_name
        tab_content = self.create_tab_content()
        new_tab_index = self.tabs.addTab(tab_content, label_name)
        self.tables[new_tab_index] = (self.left_table_widget, self.right_table_widget)
        self.current_file_paths[new_tab_index] = ''
        self.tabs.setCurrentIndex(new_tab_index)

    def close_tab(self, index):
        if index != 0:
            del self.tables[index]
            self.tables = {
                new_index: value for new_index, value in enumerate(self.tables.values())
            }
            del self.current_file_paths[index]
            self.current_file_paths = {
                new_index: value for new_index, value in enumerate(self.current_file_paths.values())
            }
            tab = self.tabs.widget(index)
            tab.deleteLater()  # 事件循环空闲时删除tab对象
            self.tabs.removeTab(index)  # 从UI中移除对应的标签

    def closeEvent(self, event):
        """
        点击关闭窗口按钮时触发的事件
        选 QMessageBox.Yes程序默认调用 event.accept()关闭窗口
        """
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setText('您确认要退出吗？ 如需要请记得还原测试环境')
        msg_box.setWindowTitle("确认")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        reply = msg_box.exec_()  # 显示对话框并等待用户的响应
        if reply == QMessageBox.Yes:
            try:
                # 关闭一些QTimer任务
                if self.timer_right_value.isActive():
                    self.timer_right_value.stop()
                if self.timer_home.isActive():
                    self.timer_home.stop()
                # 后台资源释放
                self.release_work.start()
                # 忽略默认的关闭事件，等资源释放线程完成
                event.ignore()
            except:
                logger.error(traceback.format_exc())
        else:
            event.ignore()
        # super().closeEvent(event)  # 不能继承父类关闭方法，否则选择否也会关闭窗口

    def on_cleanup_finished(self):
        if self.q_backend_thread:
            self.q_backend_thread.quit()
            self.q_backend_thread.wait()
        logger.info('退出主窗口')
        QApplication.quit()


# noinspection PyUnresolvedReferences
class SetupWorker(QObject):
    finished = pyqtSignal(object)  # 创建一个信号
    progress = pyqtSignal(str)

    def run(self):
        try:
            # ssh connector要先启动
            self.progress.emit('Initialize SSHConnector...')
            try:
                env.ssh_connector = SSHConnector(hostname=env.ssh_hostname, username=env.ssh_username, password=env.ssh_password, port=env.ssh_port)
            except:
                self.progress.emit('SSHConnector 初始化失败')
                logger.error(traceback.format_exc())
                # 不影响用户正常使用其他soa功能如dds
                env.ssh_connector = None
            try:
                env.ssh_async_connector = SSHAsyncConnector(hostname=env.ssh_hostname, username=env.ssh_username, password=env.ssh_password, port=env.ssh_port)
            except:
                self.progress.emit('SSHAsyncConnector 初始化失败')
                logger.error(traceback.format_exc())
                env.ssh_async_connector = None
            self.progress.emit('Initialize SDCConnector...')
            env.sdc_connector = SDCConnector(env.dbo_filepath, server_ip=env.sil_server_ip, server_port=env.sil_server_port)
            self.progress.emit('Initialize DDSConnector...')
            # env.dds_connector = DDSConnectorRti(idl_filepath=env.idl_filepath)
            logger.info(env.idl_filepath)
            logger.info(env.sub_topics)
            logger.info(env.pub_topics)
            env.dds_connector = env.DDSConnectorClass(idl_filepath=env.idl_filepath) \
                if env.DDSConnectorClass else DDSConnectorRti(idl_filepath=env.idl_filepath)
            self.progress.emit('Initialize DBConnector...')
            env.db_connector = DBConnector()
            self.progress.emit('Initialize DoIPClient...')
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
            self.progress.emit('Initialize CloudConnector...')
            env.cloud_connector = CloudConnector()
            self.progress.emit('Initialize DoIPSimulator...')
            env.doip_simulator = DoIPMonitorThread()
            self.progress.emit('Initialize CaseTester...')
            a2l_filepath = os.path.normpath(env.additional_configs.get('xcp', {}).get('a2l'))
            if os.path.exists(a2l_filepath):
                env.xcp_connector = XCPConnector(a2l_filepath)
            else:
                logger.warning('没有指定标定a2l文件，请检查并添加配置到 data\\conf\\additional.json')
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
                cloud_connector=env.cloud_connector,
                doipclient=env.doipclient,
                xcp_connector=env.xcp_connector
            )
            self.progress.emit('Initialize TestPrecondition ...')
            TestPrecondition(env.tester, callback=self.progress).run()
            logger.info('程序初始化完成!')
            self.progress.emit('初始化完成! 欢迎使用')
            time.sleep(1)
            self.finished.emit(True)  # 发射信号
        except Exception:
            error_info = traceback.format_exc()
            error_message = f'程序初始化失败: {error_info}'
            self.finished.emit(error_message)


def handle_exception(exc_type, exc_value, exc_traceback):
    """Handle all uncaught exceptions and print them to the console."""
    if issubclass(exc_type, KeyboardInterrupt):
        logger.error('KeyboardInterrupt event')
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.error(traceback.format_exc())


def parse_commandline():
    app = QCoreApplication.instance()
    args = app.arguments()[1:]  # 0是程序名称本身，所以从1开始取
    print('parse_commandline: ', args)


class SafeApplication(QApplication):
    def notify(self, receiver, event):
        try:
            return QApplication.notify(self, receiver, event)
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error(f'GUI应用发生异常: {e}')
            return False


# noinspection PyUnresolvedReferences
def main():
    # sys.excepthook = handle_exception

    def update_splash(message):
        splash.message = message  # 将要显示的message传给splash
        splash.update()  # 更新splash显示

    def show_error_message(error_message):
        # 自定义的弹出错误提示，并结束程序
        error_dialog = ErrorDialog(error_message)
        error_dialog.exec_()

    def on_worker_finished(result):
        try:
            # 创建一个槽函数，用于在Worker完成后，接收tester并创建显示App窗口
            if isinstance(result, str):
                # 弹出错误提示，并结束程序
                show_error_message(result)
                try:
                    # 后台线程清理掉
                    env.dds_connector.dds_proxy.clear()
                except:
                    pass
                # QThread线程关闭，不然主窗口退出后会告警
                new_thread.quit()  # 退出线程
                new_thread.wait()  # 等待线程退出
                sys.exit(-1)
            elif result is True:
                # main_window = MainWindow(backend_thread=new_thread)
                main_window.show()
                # parse_commandline()
                splash.finish(main_window)
            # QThread线程关闭，不然主窗口退出后会告警
            new_thread.quit()  # 退出线程
            new_thread.wait()  # 等待线程退出
        except:
            logger.error(traceback.format_exc())

    # 初始化App和 MainWindow
    app = SafeApplication(sys.argv)
    main_window = MainWindow()

    # 运行平台选择对话框
    dialog = PlatformConfigurationDialog()
    if dialog.exec_() != QDialog.Accepted:
        sys.exit(0)

    # 显示Splash Screen
    splash = CustomSplashScreen(QPixmap('ui/icons/splash.png'))
    splash.show()
    app.processEvents()  # 处理事件循环中的事件，保持splash显示响应

    # 创建并开始新线程
    new_thread = QThread()
    tester_worker = SetupWorker()
    tester_worker.moveToThread(new_thread)
    new_thread.started.connect(tester_worker.run)
    tester_worker.progress.connect(update_splash)
    tester_worker.finished.connect(on_worker_finished)   # 连接Worker完成的信号和槽函数
    tester_worker.finished.connect(main_window.update_signal_list_model)  # 更新主窗口的补全器
    tester_worker.finished.connect(main_window.set_sw_info_text)  # 更新被测对象软件信息
    tester_worker.finished.connect(lambda: main_window.setting_file.setPlaceholderText(env.settings_filepath))  # 默认显示当前配置路径
    new_thread.start()
    sys.exit(app.exec_())


def main2():
    app = QApplication(sys.argv)
    windows = MainWindow()
    windows.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(e)
        logger.error(traceback.format_exc())
    except KeyboardInterrupt:
        logger.error('按键终止，程序退出')
