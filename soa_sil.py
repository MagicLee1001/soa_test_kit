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
from loguru import logger
from PyQt5 import QtWidgets, QtGui, QtCore, sip
from PyQt5.QtCore import Qt, QPoint, QRect, QSize, QModelIndex, pyqtSignal, QCoreApplication
from PyQt5.QtGui import QStandardItemModel, QTextCursor, QFont, QIcon, QBrush, QPixmap, QColor
from PyQt5.Qt import QStringListModel, QCompleter, QLineEdit, QListView, QMutex, QThread, QObject, QTimer
from PyQt5.QtNetwork import QTcpServer, QTcpSocket, QHostAddress
from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QSplashScreen, QTabWidget, QVBoxLayout, QPushButton, QWidget, QTableWidget, \
    QHBoxLayout, QHeaderView, QTableWidgetItem, QLabel, QCheckBox, QScrollArea, QTextEdit, QMessageBox,\
    QFrame, QAction, QFileDialog, QStyle, QStyleOptionViewItem, QStyleOptionButton, QInputDialog, QTabBar, \
    QComboBox, QListWidget,QListWidgetItem, QProgressBar, QMenu, QPlainTextEdit, QSplitter, QSizePolicy
)
from settings import env
from connector.dds import DDSConnector
from connector.sdc import SDCConnector
from connector.ssh import SSHConnector
from runner.variable import vars_mapping
from runner.tester import CaseTester, TestPrecondition, TestPostCondition, TestHandle, CaseParser
from runner.remote import Run, CallBack
from test_sil_xbp import set_test_handle, qt_main


class AutoTestWorker(QThread):
    finish_signal = pyqtSignal(str)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.is_running = False  # 防止自动化测试任务同时多次下发

    def disable_buttons(self):
        """
        GUI更新操作非线程安全, 以后放在主线程中做
        """
        self.app.reload_tool.setEnabled(False)
        self.app.run_tool.setEnabled(False)
        self.app.select_setting_btn.setEnabled(False)
        self.app.select_case_btn.setEnabled(False)
        self.app.remote_tool.setEnabled(False)

    def run(self) -> None:
        if env.is_auto_running:
            logger.warning('auto test task is running')
            return
        try:
            env.is_auto_running = True
            # 执行过程中禁用按钮
            self.disable_buttons()
            # TestHandle变量重置
            set_test_handle()
            # 设置执行用例
            self.app.set_env_testcase()
            # 开始自动化测试
            qt_main()
            # 飞书报告通知
            TestHandle.feishu_notice()
        except Exception as e:
            logger.error(traceback.format_exc())
            TestHandle.run_state = '执行异常: ' + str(e)
            self.finish_signal.emit('TestCase run task exception')
        else:
            TestHandle.run_state = '已结束'
            time.sleep(1)
            self.finish_signal.emit('TestCase run task finished')
        finally:
            logger.info('测试任务执行全部完成 资源重置')
            env.is_auto_running = False
            if env.remote_callback:
                env.remote_callback.task_callback(env.xcu_info)
            # 远程信息重置
            env.remote_event_data = None
            env.remote_callback = None


class ReloadSettingWorker(QThread):
    def __init__(self, app):
        super().__init__()
        self.app = app

    def run(self) -> None:
        try:
            # 处理空配置文件路径
            setting_filepath = self.app.setting_file.text()
            if not setting_filepath:
                setting_filepath = env.settings_filepath
            env.load(setting_filepath)
            # 更新配置中的用例并渲染
            # case_filenames = TestHandle.get_filename_from_dir(env.case_dir, 'xlsm')
            # self.app.case_filepaths = [os.path.join(env.case_dir, case_filename) for case_filename in case_filenames]
            # self.app.case_list_widget.addItems(self.case_filepaths)
            # 重写初始化connector 更新各种信号矩阵
            env.sdc_connector = SDCConnector(env.dbo_filepath, server_ip=env.sil_server_ip, server_port=env.sil_server_port)
            env.dds_connector = DDSConnector(idl_filepath=env.idl_filepath)
            self.app.tester = env.tester = CaseTester(
                sub_topics=env.sub_topics,
                pub_topics=env.pub_topics,
                sdc_connector=env.sdc_connector,
                dds_connector=env.dds_connector,
                ssh_connector=env.ssh_connector
            )
            tpr = TestPrecondition(env.tester)
            # 更新ssh信号矩阵
            tpr.start_ssh_connector()
            # 更新dds writer与reader池
            tpr.start_dds_connector()
        except:
            logger.error(traceback.format_exc())


class ModifyConfigWordWorker(QThread):
    def __init__(self, app):
        super().__init__()
        self.app = app

    def run(self) -> None:
        try:
            text = self.app.cw_edit.text()
            if text:
                result = self.app.tester.ssh_connector.modify_config_word_file(text)
                if result:
                    env.xcu_info['config_word'] = text
                # 这里由于改完后重启,需要主动重新连接一下sil仿真程序
                # 重连时的close会导致接收线程抛出异常再重连一次
                self.app.tester.sdc_connector.reconnect_server()
        except:
            logger.error(traceback.format_exc())


class RecoverEnvironment(QThread):
    def __init__(self, app):
        super().__init__()
        self.app = app

    def run(self) -> None:
        try:
            # 恢复过程中按钮置灰
            self.app.recover_tool.setEnabled(False)
            self.app.tester.ssh_connector.recover_sil_environment()
        except:
            logger.error(traceback.format_exc())
        finally:
            self.app.recover_tool.setEnabled(True)


class CustomListWidget(QListWidget):
    def __init__(self, app, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app = app
        self.setSortingEnabled(False)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())  # 获取被右键点击的项
        if item is not None:  # 如果有项被右键点击
            menu = QMenu(self)
            delete_action = menu.addAction("Delete")
            action = menu.exec_(self.mapToGlobal(event.pos()))  # 显示菜单
            if action == delete_action:  # 如果用户选择"Delete"操作，删除被点击的项
                row_index = self.row(item)
                self.takeItem(row_index)
                self.app.case_filepaths.pop(row_index)


class CustomTableWidget(QTableWidget):
    def __init__(self, app, *args, **kwargs):
        super(CustomTableWidget, self).__init__(*args, **kwargs)
        self.app = app

    def mousePressEvent(self, event):
        # table鼠标点击事件
        index = self.indexAt(event.pos())
        if index.column() == 0:  # 如果点击的是第一列（即复选框所在列）
            checkbox = self.cellWidget(index.row(), 0)
            if checkbox.checkState() == Qt.Checked:  # 如果原本是选中状态，则设置为未选中
                checkbox.setCheckState(Qt.Unchecked)
            else:  # 如果原本是未选中状态，则设置为选中
                checkbox.setCheckState(Qt.Checked)
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        # 判断是否按下了删除键
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.app.delete_row(self)
        # 按下回车键 直接运行
        elif event.key() in (Qt.Key_Enter, Qt.Key_Return):
            self.app.input_table_process()
        super().keyPressEvent(event)

    def handle_checkbox_clicked(self, state):
        self.app.all_checkbox_clicked(state)


class CheckBoxHeader(QHeaderView):
    def __init__(self, parent=None):
        super(CheckBoxHeader, self).__init__(Qt.Horizontal, parent)
        self.parent = parent
        self.isChecked = False

    def disconnect_slot(self):
        try:
            self.mousePressEvent.disconnect()
        except TypeError:  # 如果没有连接的槽函数
            pass

    def mousePressEvent(self, event):
        """鼠标点击勾选进行全选/全选取消"""
        index = self.logicalIndexAt(event.pos())
        if index == 0:  # 第一列（“勾选”列）
            if self.isChecked:
                self.isChecked = False
                self.parent.handle_checkbox_clicked(Qt.Unchecked)
            else:
                self.isChecked = True
                self.parent.handle_checkbox_clicked(Qt.Checked)
        super().mousePressEvent(event)


class CustomTabBar(QTabBar):
    """表格控件的导航栏标签自定义修改"""
    def __init__(self, parent=None):
        super().__init__(parent)

    def mouseDoubleClickEvent(self, event):
        """双击修改Tab标签名"""
        index = self.tabAt(event.pos())
        if index >= 0:
            current_tab_name = self.tabText(index)
            new_tab_name, accept = QInputDialog.getText(self, 'Rename Tab', f'New name for {current_tab_name}:')
            if accept and new_tab_name:  # 如果用户点击了 OK 并且输入了新的名称
                self.setTabText(index, new_tab_name)

    def tabButton(self, index, position):
        if position == QTabBar.RightSide and index == 0:  # 假设 home 页面在第一个
            return None
        return super().tabButton(index, position)


class PopupView(QListView):
    """补全器滚动条"""
    def sizeHintForColumn(self, column):
        return self.sizeHintForIndex(self.model().index(0, column)).width()


class SafeLogHandler(QtCore.QObject):
    """在Qt框架中，几乎所有的GUI组件，包括QPlainTextEdit，都不是线程安全的。
    这就意味着你不能在除主线程之外的任何线程中操作它们。
    如果你试图在其他线程中操作GUI组件，可能会导致不可预见的行为，包括闪退、数据错误和死锁等。
    不应该直接在该线程中操作QPlainTextEdit，应该使用信号和槽机制来将内容发送给主线程，并在槽函数中更新QPlainTextEdit
    """
    new_log = pyqtSignal(str)

    def __init__(self):
        super().__init__()

    def write(self, message):
        self.new_log.emit(message.strip())

    def flush(self):
        pass


class CustomLogText(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setFont(QFont("Consolas", 10))  # 设置字体和字号
        self.setStyleSheet("QTextEdit {background-color: #f0f0f0;}")  # 设置背景色

    def contextMenuEvent(self, event):
        # 调用 QTextEdit 创建默认的右键菜单
        menu = self.createStandardContextMenu()
        # 在默认菜单项后面添加一个清除当前日志的菜单项
        clear_action = QAction('Clear All', self)
        clear_action.triggered.connect(self.clear)
        menu.addAction(clear_action)
        menu.exec_(event.globalPos())


class CustomerLogArea(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setMinimumHeight(200)  # 设置最小高度
        log_layout = QVBoxLayout()
        self.log_widget = CustomLogText()
        # 创建handler，并添加到logger
        self.log_handler = SafeLogHandler()
        self.log_handler.new_log.connect(self._append_new_log)
        logger.add(self.log_handler)
        # 将日志文本框添加到垂直布局中
        log_title = QLabel("运行日志")
        log_title.setAlignment(Qt.AlignLeft)
        log_layout.addWidget(log_title)
        log_layout.addWidget(self.log_widget)
        # 创建存垂直布局的小部，并将其设置为滚动区域的小部件
        widget = QWidget()
        widget.setLayout(log_layout)
        self.setWidget(widget)

    def _append_new_log(self, text):
        self.log_widget.appendPlainText(text)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


class App(QMainWindow):
    def __init__(self, tester):
        super().__init__()
        self.tester = tester
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
        self.signal_name_list = vars_mapping.keys()
        self.signal_list_model.setStringList(self.signal_name_list)

        # 主窗口控件与布局
        self.main_splitter = QSplitter(Qt.Vertical)  # 使用垂直分割器
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
        self.tabs.tabCloseRequested.connect(self.close_tab)
        # 创建一个 QFrame 作为分割线，并添加到布局中
        # self.hline = QFrame()
        # self.hline.setFrameShape(QFrame.HLine)
        # self.hline.setFrameShadow(QFrame.Sunken)
        # 创建日志滚动区域
        self.log_scroll_area = CustomerLogArea()
        self.log_scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # 将 tabs 和 log_scroll_area 添加到 splitter 控件中
        self.main_splitter.addWidget(self.tabs)
        self.main_splitter.addWidget(self.log_scroll_area)
        # 软件右下角标签
        self.foot_label = QLabel("By likun3@lixiang.com 版本:24.1.18")
        self.foot_label.setAlignment(Qt.AlignRight)
        # 创建一个新的垂直布局
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.main_splitter, 1)  # splitter 占据布局中的大部分空间
        self.layout.addWidget(self.foot_label, 0)  # foot_label 位于底部，没有额外的空间
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
        self.timer_right_value.start(200)
        self.timer_right_value.timeout.connect(self.update_right_values)
        # 初始化Home执行文本信息更新定时器
        self.timer_home = QTimer(self)
        self.timer_home.timeout.connect(self.set_auto_run_text)
        self.timer_home.setInterval(500)
        # 自动化测试线程 禁用和解禁一些按钮
        self.auto_test_worker = AutoTestWorker(self)
        self.auto_test_worker.started.connect(lambda: self.timer_home.start())
        self.auto_test_worker.finish_signal.connect(self.on_auto_test_finish)
        # 加载配置线程
        self.reload_setting_worker = ReloadSettingWorker(self)
        # 修改配置字线程
        self.modify_cw_worker = ModifyConfigWordWorker(self)
        self.modify_cw_worker.finished.connect(self.set_sw_info_text)
        # 恢复环境线程
        self.recover_env_task = RecoverEnvironment(self)
        self.recover_env_task.finished.connect(lambda: self.recover_tool.setEnabled(True))
        # 创建一个手动调试页
        self.add_tab()
        self.switch_current_tab()

    # def __init__(self, tester):
    #     super().__init__()
    #     self.tester = tester
    #     self.init_window()
    #     self.init_menu()
    #     # 添加一个工具栏
    #     self.toolbar = self.addToolBar('Toolbar')
    #     self.toolbar.setIconSize(QSize(20, 20))
    #     # 创建动作 QAction
    #     self.new_tool = QAction(QIcon('ui/icons/Add_black.svg'), '', self)
    #     self.new_tool.setToolTip('新建')
    #     self.new_tool.triggered.connect(self.add_tab)
    #     self.open_tool = QAction(QIcon('ui/icons/Folder_black.svg'), '', self)
    #     self.open_tool.setToolTip('打开')
    #     self.open_tool.triggered.connect(self.open_configuration)
    #     self.save_tool = QAction(QIcon('ui/icons/Save_black.svg'), '', self)
    #     self.save_tool.setToolTip('保存')
    #     self.save_tool.triggered.connect(self.save_configuration)
    #     self.run_tool = QAction(QIcon('ui/icons/PlaySolid_black.svg'), '', self)  # 不显示文本
    #     self.run_tool.setToolTip('运行')  # 鼠标悬停时显示文本
    #     self.run_tool.triggered.connect(self.input_table_process)  # 连接到run_btn原有的功能
    #     self.reload_tool = QAction(QIcon('ui/icons/Sync_black.svg'), '', self)
    #     self.reload_tool.setToolTip('更新配置')
    #     self.reload_tool.triggered.connect(self.reload_setting)
    #     self.remote_tool_color = 'black'
    #     self.remote_tool = QAction(QIcon(f'ui/icons/Connect_{self.remote_tool_color}.svg'), '', self)
    #     self.remote_tool.setToolTip('远程执行 打开/关闭')
    #     self.remote_tool.triggered.connect(self.remote_execute_listen)
    #
    #     # 如果需要工具栏文本一直显示，可以使用setToolButtonStyle方法
    #     # self.toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
    #     # 设置工具栏样式为图标样式，即仅显示图标，不显示文本
    #     self.toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
    #     # 将动作添加到工具栏
    #     self.toolbar.addAction(self.new_tool)
    #     self.toolbar.addAction(self.open_tool)
    #     self.toolbar.addAction(self.save_tool)
    #     self.toolbar.addAction(self.run_tool)
    #     self.toolbar.addAction(self.reload_tool)
    #     self.toolbar.addAction(self.remote_tool)
    #
    #     # 主窗口控件与布局
    #     self.window = QWidget()
    #     self.layout = QVBoxLayout()
    #     # 创建一个包含你的备选文本列表的字符串列表模型
    #     self.signal_list_model = QStringListModel()
    #     self.signal_name_list = vars_mapping.keys()
    #     self.signal_list_model.setStringList(self.signal_name_list)
    #     # 手动调试标签页
    #     self.tabs = QTabWidget()
    #     self.tables = {}
    #     self.tab_label_num = 1
    #     self.current_file_paths = {}
    #     self.current_right_table = None
    #     self.left_table_widget = None
    #     self.right_table_widget = None
    #     self.tabs.setTabBar(CustomTabBar())
    #     self.tabs.setTabsClosable(True)
    #     self.tabs.tabCloseRequested.connect(self.close_tab)
    #     # 创建一个 QFrame 作为分割线，并添加到布局中
    #     self.hline = QFrame()
    #     self.hline.setFrameShape(QFrame.HLine)
    #     self.hline.setFrameShadow(QFrame.Sunken)
    #     # 创建日志滚动区域
    #     self.log_scroll_area = CustomerLogArea()
    #     # 软件右下角标签
    #     self.foot_label = QLabel("By likun3@lixiang.com 版本:24.1.18")
    #     self.foot_label.setAlignment(Qt.AlignRight)
    #     self.layout.addWidget(self.tabs)
    #     self.layout.addWidget(self.hline)
    #     self.layout.addWidget(self.log_scroll_area, 1)  # 添加伸缩因子
    #     self.layout.addWidget(self.foot_label, 0)
    #     self.window.setLayout(self.layout)
    #     self.setCentralWidget(self.window)
    #     self.add_home_tab()
    #     # 连接 currentChanged 信号和 switch_current_tab 方法
    #     self.tabs.currentChanged.connect(self.switch_current_tab)
    #     # 初始化手动窗口输出值更新定时器
    #     self.timer_right_value = QTimer(self)
    #     self.timer_right_value.start(200)
    #     self.timer_right_value.timeout.connect(self.update_right_values)
    #     # 初始化Home执行文本信息更新定时器
    #     self.timer_home = QTimer(self)
    #     self.timer_home.timeout.connect(self.set_auto_run_text)
    #     self.timer_home.setInterval(500)
    #     # 自动化测试线程 禁用和解禁一些按钮
    #     self.auto_test_worker = AutoTestWorker(self)
    #     self.auto_test_worker.started.connect(lambda: self.timer_home.start())
    #     self.auto_test_worker.finish_signal.connect(self.on_auto_test_finish)
    #     # 加载配置线程
    #     self.reload_setting_worker = ReloadSettingWorker(self)
    #     # 创建一个手动调试页
    #     self.add_tab()
    #     self.switch_current_tab()
    
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
        if self.remote_tool_color == 'black':
            self.tcp_server = QTcpServer(self)
            logger.info('TCP Server open.')
            if not self.tcp_server.listen(QHostAddress.LocalHost, 54321):
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

    def new_socket_slot(self):
        sock = self.tcp_server.nextPendingConnection()
        peer_address = sock.peerAddress().toString()
        peer_port = sock.peerPort()
        logger.info('Connected with address {}, port {}'.format(peer_address, str(peer_port)))
        sock.readyRead.connect(lambda: self.read_tcp_data_slot(sock))
        sock.disconnected.connect(lambda: self.disconnected_tcp_slot(sock))

    def read_tcp_data_slot(self, sock):
        """
        远程执行触发槽函数
        """
        try:
            while sock.bytesAvailable():
                datagram = sock.read(sock.bytesAvailable())
                message = datagram.decode().strip()
                logger.info(f'TCP Server recv: {message}')
                parse_data = json.loads(message)
                event_type = parse_data.get('event_type', None)
                if event_type == 'remote_autotest':
                    event_data = parse_data.get('event_data')
                    env.remote_event_data = event_data  # 远程执行参数信息
                    if event_data.get('task_id'):
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

    def init_window(self):
        self.resize(env.width, env.height)
        # self.setMinimumWidth(600)
        self.setWindowTitle('SOA XBP 测试工具')
        self.setWindowIcon(QIcon('ui/icons/icon.ico'))
        desktop = QApplication.desktop().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w//2 - self.width()//2, h//2 - self.height()//2)

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

    def switch_current_tab(self):
        # 当前标签页切换时调用的函数 tab全都关闭以后索引是0(home页)
        current_tab_index = self.tabs.currentIndex()
        if not self.tables or current_tab_index < 1 or current_tab_index >= self.tabs.count():
            self.current_right_table = None
            return
        # TODO 这一步是个大Bug 这个时候可能 self.tables中的索引还没销毁完 当前已有临时处理方法 后续解决
        _, self.current_right_table = self.tables[current_tab_index]

    def save_configuration_as(self):
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
            with open(filepath, 'w') as f:
                for row in range(left_table.rowCount()):
                    # checkbox = left_table.cellWidget(row, 0)
                    signal = left_table.cellWidget(row, 0).text() if left_table.cellWidget(row, 0) else ""
                    value = left_table.item(row, 1).text() if left_table.item(row, 1) else ""
                    f.write(f'1,{signal},{value}\n')
                for row in range(right_table.rowCount()):
                    signal = right_table.cellWidget(row, 0).text() if right_table.cellWidget(row, 0) else ""
                    value = right_table.item(row, 1).text() if right_table.item(row, 1) else ""
                    f.write(f'2,{signal},{value}\n')
            # 另存完后改名
            saved_tab_name = os.path.splitext(os.path.basename(filepath))[0]
            self.tabs.setTabText(current_tab_index, saved_tab_name)

    def save_configuration(self):
        current_tab_index = self.tabs.currentIndex()
        if current_tab_index > 0: # 保存手动调试配置
            current_file_path = self.current_file_paths[current_tab_index]
            if current_file_path == '':  # 如果当前文件路径为空就另存
                self.save_configuration_as()
            else:
                left_table, right_table = self.tables[current_tab_index]
                with open(current_file_path, 'w') as f:
                    for row in range(left_table.rowCount()):
                        # checkbox = left_table.cellWidget(row, 0)
                        signal = left_table.cellWidget(row, 0).text() if left_table.cellWidget(row, 0) else ""  # cellWidget(row, 1)
                        value = left_table.item(row, 1).text() if left_table.item(row, 1) else ""  # item(row, 1)
                        # f.write(f'1,{checkbox.checkState()},{signal},{value}\n')
                        f.write(f'1,{signal},{value}\n')
                    for row in range(right_table.rowCount()):
                        signal = right_table.cellWidget(row, 0).text() if right_table.cellWidget(row, 0) else ""
                        value = right_table.item(row, 1).text() if right_table.item(row, 1) else ""
                        # f.write(f'2,,{signal},{value}\n')
                        f.write(f'2,{signal},{value}\n')

    def open_configuration(self):
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
            with open(filepath, 'r') as f:
                lines = f.readlines()
                # 分别加载输入和输出的表格
                num_left_rows = 0
                num_right_rows = 0
                left_lines = []
                right_lines = []
                for row, line in enumerate(lines):
                    table_type, signal, value = line.strip().split(',')
                    if table_type == '1':
                        num_left_rows += 1
                        left_lines.append((signal, value))
                    else:
                        num_right_rows += 1
                        right_lines.append((signal, value))

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
                    signal, value = line
                    # left_table.cellWidget(row, 0).setCheckState(int(checkbox_state))
                    left_table.cellWidget(row, 0).setText(signal)
                    if not left_table.item(row, 1):  # 防止这行没有单元格项目
                        left_table.setItem(row, 1, QTableWidgetItem())
                    left_table.item(row, 1).setText(value)
                for row, line in enumerate(right_lines):
                    signal, value = line
                    right_table.cellWidget(row, 0).setText(signal)

    def keyPressEvent(self, event):
        # 按下Ctrl+S 保存配置
        if event.key() == Qt.Key_S and int(event.modifiers()) == Qt.ControlModifier:
            self.save_configuration()
        # 按下回车键 模拟点击run_btn运行
        # elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
        #     self.input_table_process()
        super().keyPressEvent(event)

    # def input_table_process(self):
    #     """
    #     旧版 勾选后发送，新版不用勾选
    #     """
    #     current_table_index = self.tabs.currentIndex()
    #     # 手动调试窗口
    #     if current_table_index >= 1:
    #         # 从字典中获取当前选项卡的左、右 table_widget
    #         left_table_widget, right_table_widget = self.tables[current_table_index]
    #         # 取消table焦点 防止处于编辑中的数据不生效
    #         left_table_widget.clearFocus()
    #         left_table_widget.setFocus()
    #         checked_data = self.get_checked_data(left_table_widget)
    #         try:
    #             for msg in checked_data:
    #                 signal = vars_mapping.get(msg[0])
    #                 signal_value = CaseTester.convert_to_float(msg[1])
    #                 if signal_value is None:
    #                     logger.error(f'{signal.name}={signal_value} value convert error')
    #                     raise Exception(f'{signal.name}={signal_value} value convert error')
    #                 signal.Value = signal_value
    #                 self.tester.send_single_msg(signal)
    #         except Exception as e:
    #             logger.error("运行异常: " + str(e))
    #     else:
    #         # 自动执行窗口
    #         self.auto_test_worker.start()

    def input_table_process(self):
        """
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
                value = left_table_widget.item(row, 1).text() if left_table_widget.item(row, 1) else None
                if signal_name and value is not None:
                    try:
                        signal = vars_mapping.get(signal_name)
                        signal_value = CaseTester.convert_to_float(value)
                        if signal_value is None:
                            raise Exception(f'{signal.name}={signal_value} value convert error')
                        if signal.data_array[-1] != signal_value:  # 当前值有修改则发送
                            signal.Value = signal_value
                            self.tester.send_single_msg(signal)
                    except Exception as e:
                        logger.error(e)
        else:
            # 自动化测试执行窗口
            self.auto_test_worker.start()

    # def insert_left_row(self, table_widget):
    #     """
    #     旧版 带勾选框
    #     """
    #     rowPosition = table_widget.rowCount()
    #     table_widget.insertRow(rowPosition)
    #     # 也为新行的 “勾选” 列添加复选框
    #     checkbox = QCheckBox()
    #     table_widget.setCellWidget(rowPosition, 0, checkbox)
    #     # 为新行的 "信号" 列添加 QLineEdit 编辑器和 QCompleter
    #     completer = QCompleter()
    #     completer.setModel(self.signal_list_model)  # 这里假设你在类中存储了模型
    #     line_edit = QLineEdit()
    #     # 下拉补齐补全器展示所有内容
    #     popup_view = PopupView()
    #     completer.setPopup(popup_view)
    #     line_edit.setCompleter(completer)
    #     table_widget.setCellWidget(rowPosition, 1, line_edit)  # 假设"信号"列是第二列，即索引为1的列
    #     table_widget.setItem(rowPosition, 2, QTableWidgetItem())  # 这里添加一个空的QTableWidgetItem

    def insert_left_row(self, table_widget):
        rowPosition = table_widget.rowCount()
        table_widget.insertRow(rowPosition)
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
        table_widget.setCellWidget(rowPosition, 0, line_edit)  # 信号列
        table_widget.setItem(rowPosition, 1, QTableWidgetItem())  # 这里添加一个空的QTableWidgetItem

    def insert_right_row(self, table_widget):
        # 插入右侧表格的新行的函数
        rowPosition = table_widget.rowCount()
        table_widget.insertRow(rowPosition)
        completer = QCompleter()
        completer.setModel(self.signal_list_model)
        completer.setFilterMode(Qt.MatchContains)  # 支持模糊搜索，没有的话默认是起始位置搜索
        completer.setCaseSensitivity(Qt.CaseInsensitive)  # 不区分大小写
        line_edit = QLineEdit()
        # 下拉补齐补全器展示所有内容
        popup_view = PopupView()
        completer.setPopup(popup_view)
        line_edit.setCompleter(completer)
        table_widget.setCellWidget(rowPosition, 0, line_edit)
        # 为新行的 "值" 列禁止编辑
        item = QTableWidgetItem()
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        table_widget.setItem(rowPosition, 1, item)

    def delete_row(self, table_widget):
        # 删除按钮的函数
        index_list = []
        for model_index in table_widget.selectionModel().selectedRows():
            index = QtCore.QPersistentModelIndex(model_index)
            index_list.append(index)
        for index in index_list:
            table_widget.removeRow(index.row())

    # def get_checked_data(self, table_widget):
    #     """
    #     旧版需要搭配勾选左table使用，新版不用勾选了
    #     """
    #     checked_data = []
    #     for row in range(table_widget.rowCount()):
    #         checkbox = table_widget.cellWidget(row, 0)
    #         if checkbox.checkState() == Qt.Checked:
    #             # 假设“信号”列的数据是通过 QLineEdit 编辑的
    #             signal = table_widget.cellWidget(row, 1).text() if table_widget.cellWidget(row, 1) else ""
    #             # 假设“值”列的数据是直接以文字形式储存在单元格里的
    #             value = table_widget.item(row, 2).text() if table_widget.item(row, 2) else None
    #             if signal and value != None:
    #                 checked_data.append((signal, value))
    #     return checked_data

    def get_checked_data(self, table_widget):
        """
        旧版需要搭配勾选左table使用，新版不用勾选了
        """
        checked_data = []
        for row in range(table_widget.rowCount()):
            signal = table_widget.cellWidget(row, 1).text() if table_widget.cellWidget(row, 1) else ""
            # 假设“值”列的数据是直接以文字形式储存在单元格里的
            value = table_widget.item(row, 2).text() if table_widget.item(row, 2) else None
            if signal and value is not None:
                checked_data.append((signal, value))
        return checked_data

    def update_right_values(self):
        """
        由于 self.current_right_table 被 close_table和switch_current_tab两个异步方法处理后对象实际已经不存在了
        """
        if self.current_right_table is None or sip.isdeleted(self.current_right_table):
            # 然后接着切一下当前的tab,重置最新的右表
            # self.switch_current_tab()
            return
        try:
            for i in range(self.current_right_table.rowCount()):
                signal_name = self.current_right_table.cellWidget(i, 0).text() \
                    if self.current_right_table.cellWidget(i, 0) else ""
                if signal_name:
                    signal_value = vars_mapping.get(signal_name).Value
                    self.current_right_table.takeItem(i, 1)
                    self.current_right_table.setItem(i, 1, QTableWidgetItem(str(signal_value)))
        except:
            self.switch_current_tab()

    def all_checkbox_clicked(self, state):
        # 获取当前选项卡的table widget
        left_table, right_table = self.tables[self.tabs.currentIndex()]
        # 获取表头，并设置复选框的状态
        header = left_table.horizontalHeader()
        if isinstance(header, CheckBoxHeader):
            header.isChecked = (state == Qt.Checked)
        # 对表格的每一行进行操作
        for row in range(left_table.rowCount()):
            checkbox = left_table.cellWidget(row, 0)
            checkbox.setCheckState(state)

    # def create_left_table(self):
    #     """
    #     旧版逻辑 设置勾选框 只发送勾选的信号
    #     """
    #     # 创建一个 QLabel 作为输入的标签，并将标签和复选框添加到一个水平布局中
    #     label = QLabel('输入')
    #     label.setAlignment(Qt.AlignCenter)
    #     self.left_table_widget = table_widget = CustomTableWidget(self, 3, 3)
    #     # 设置表头为自定义的 CheckBoxHeader
    #     table_widget.setHorizontalHeader(CheckBoxHeader(table_widget))
    #     # 设置表头标签
    #     table_widget.setHorizontalHeaderLabels(['勾选', '信号', '值'])
    #     # 设置列的大小策略
    #     header = table_widget.horizontalHeader()
    #     header.setSectionResizeMode(QHeaderView.Stretch)
    #     header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
    #     header.setSectionResizeMode(1, QHeaderView.Stretch)
    #     header.setSectionResizeMode(2, QHeaderView.Stretch)
    #
    #     for i in range(table_widget.rowCount()):
    #         # 创建一个复选框对象
    #         checkbox = QCheckBox()
    #         # 把这个复选框设置为第一列的元素
    #         table_widget.setCellWidget(i, 0, checkbox)
    #         # 信号这一列支持搜索补全功能
    #         completer = QCompleter()
    #         completer.setModel(self.signal_list_model)  # 设置为刚才创建的字符串列表模型
    #         completer.setFilterMode(Qt.MatchContains)  # 支持模糊搜索，没有的话默认是起始位置搜索
    #         completer.setCaseSensitivity(Qt.CaseInsensitive)  # 不区分大小写
    #         line_edit = QLineEdit()
    #         # 下拉补齐补全器展示所有内容
    #         popup_view = PopupView()
    #         completer.setPopup(popup_view)
    #         # 设置完成器
    #         line_edit.setCompleter(completer)
    #         # 用它替换默认的编辑器
    #         table_widget.setCellWidget(i, 1, line_edit)
    #         table_widget.setItem(i, 2, QTableWidgetItem())  # 这里添加一个空的QTableWidgetItem
    #
    #     add_row_btn = QPushButton("添加行", self)
    #     add_row_btn.clicked.connect(lambda: self.insert_left_row(table_widget))
    #     delete_row_btn = QPushButton("删除行", self)
    #     delete_row_btn.clicked.connect(lambda: self.delete_row(table_widget))
    #     # 创建一个 QVBoxLayout，并添加 QLabel 和 QTableWidget
    #     layout = QVBoxLayout()
    #     layout.addWidget(label)
    #     layout.addWidget(table_widget)
    #     layout.addWidget(add_row_btn)
    #     layout.addWidget(delete_row_btn)
    #     # 创建一个 QWidget，设置其布局为前面创建的 QVBoxLayout
    #     widget = QWidget()
    #     widget.setLayout(layout)
    #     return widget

    def create_left_table(self):
        """
        新版逻辑 设置勾选框 只发送勾选的信号
        """
        # 创建一个 QLabel 作为输入的标签，并将标签和复选框添加到一个水平布局中
        label = QLabel('输入')
        label.setAlignment(Qt.AlignCenter)
        self.left_table_widget = table_widget = CustomTableWidget(self, 3, 2)
        # 设置表头为自定义的 CheckBoxHeader
        table_widget.setHorizontalHeader(CheckBoxHeader(table_widget))
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
        self.select_setting_btn = QPushButton('选择配置')
        self.select_setting_btn.clicked.connect(self.select_setting)
        l_setting_layout.addWidget(self.select_setting_btn)
        self.setting_file = QLineEdit()
        self.setting_file.setPlaceholderText(env.settings_filepath)
        l_setting_layout.addWidget(self.setting_file)
        left_layout.addLayout(l_setting_layout)
        # 左侧第二行
        l_case_layout = QVBoxLayout()
        self.select_case_btn = QPushButton('加载用例')
        self.select_case_btn.clicked.connect(self.select_case)
        l_case_layout.addWidget(self.select_case_btn)
        self.case_list_widget = CustomListWidget(self)
        case_filenames = TestHandle.get_filename_from_dir(env.case_dir, 'xlsm')
        self.case_filepaths = [os.path.join(env.case_dir, case_filename) for case_filename in case_filenames]
        self.case_list_widget.addItems(self.case_filepaths)
        l_case_layout.addWidget(self.case_list_widget)
        left_layout.addLayout(l_case_layout)
        # 左侧第三行
        l_sw_info_layout = QVBoxLayout()
        self.sw_info_text = QTextEdit()
        self.sw_info_text.setFont(QFont("Segoe UI", 10))  # 设置字体和字号
        self.sw_info_text.setReadOnly(True)
        # 显示当前软件信息
        self.set_sw_info_text()
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
        # 右侧第二行
        self.auto_run_text = QTextEdit()
        self.auto_run_text.setFont(QFont("Consolas", 12))  # 设置字体和字号
        self.auto_run_text.setReadOnly(True)
        right_layout.addWidget(self.auto_run_text)
        # 设置布局的边距为0，使得布局之间紧密排布
        for layout in (main_layout, hlayout, left_layout, right_layout, l_setting_layout,
                       l_case_layout, l_sw_info_layout, process_layout):
            layout.setContentsMargins(0, 0, 0, 0)
        return home_page

    # def handle_tcp_message(self, message):
    #     try:
    #         logger.info(f'TCP Server recv: {message}')
    #         parse_data = json.loads(message)
    #         event_type = parse_data.get('event_type', None)
    #         if event_type == 'remote_autotest':
    #             event_data = parse_data.get('event_data')
    #     except Exception:
    #         logger.error(traceback.format_exc())

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
        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.ExistingFiles)  # 可以选择多个文件
        dialog.setOption(QFileDialog.ShowDirsOnly, False)  # 可以选择文件夹
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)  # 使用Qt的标准文件选择器，而非操作系统的文件选择器
        dialog.setNameFilter("Excel files (*.xls *.xlsx *.xlsm)")  # 只显示和选择Excel文件
        if dialog.exec_():
            self.case_filepaths = dialog.selectedFiles()  # 获取选择的文件和文件夹名称的列表
            self.case_list_widget.clear()
            self.case_list_widget.addItems(self.case_filepaths)

    def reload_setting(self):
        # 获取现有配置文件路径
        self.reload_setting_worker.start()

    def on_auto_test_finish(self, msg):
        try:
            logger.info(f'自动化执行信息停止更新 按钮置灰还原： {msg}')
            if self.timer_home.isActive():
                self.timer_home.stop()
            self.reload_tool.setEnabled(True)
            self.run_tool.setEnabled(True)
            self.select_setting_btn.setEnabled(True)
            self.select_case_btn.setEnabled(True)
            self.remote_tool.setEnabled(True)
        except:
            logger.error(traceback.format_exc())

    def set_env_testcase(self):
        # 远程执行触发参数
        if env.remote_event_data:
            env.remote_run = Run(
                server=env.remote_event_data['server'],
                task_id=env.remote_event_data['task_id'],
                distribute_id=env.remote_event_data['distribute_id']
            )
            self.case_filepaths, result_case_path = env.remote_run.parse_case()
            env.remote_callback = CallBack()
            self.case_list_widget.clear()
            self.case_list_widget.addItems(self.case_filepaths)
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
                'suite_name': tc_filename,
                'testcases': testcases
            }
            env.ddt_testcase.append(suite_info)
        env.ddt_test_index = 0

    def set_auto_run_text(self):
        """所有的GUI操作更新都要放在主线程中"""
        try:
            text_fmt = f"执行时间: {TestHandle.start_time}\n" \
                       f"测试状态: {TestHandle.run_state}\n" \
                       f"用例总数: {TestHandle.all_case_num}\n" \
                       f"已经执行: {TestHandle.total_num}\n" \
                       f"通过数量: {TestHandle.pass_num}\n" \
                       f"失败数量: {TestHandle.fail_num}\n" \
                       f"通过率  : {TestHandle.current_pass_rate}\n" \
                       f"当前用例: {TestHandle.current_running_case}\n" \
                       f"报告路径: {TestHandle.report_html_path}"
            self.auto_run_text.clear()
            self.auto_run_text.setText(text_fmt)
            if TestHandle.all_case_num:
                self.process_bar.setValue(int(round(TestHandle.total_num/TestHandle.all_case_num,2)*100))
            else:
                self.process_bar.setValue(0)
        except Exception:
            logger.error(traceback.format_exc())

    def set_sw_info_text(self):
        """
        显示当前被测设备软件信息
        """
        try:
            text_fmt = ""
            for key, val in env.xcu_info.items():
                text_fmt += f"{key}:\n{val}\n\n"
            self.sw_info_text.clear()
            self.sw_info_text.setText(text_fmt)
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
        # 初始创建新标签页后，调用 switch_current_tab() 方法
        # self.switch_current_tab()
        # 不知道需不需要重新起timer，有问题再说
        # if self.timer_right_value.isActive():
        #     self.timer_right_value.stop()
        # self.timer_right_value.start(200)

    def close_tab(self, index):
        if index != 0:
            del self.tables[index]
            self.tables = {new_index:value for new_index, value in enumerate(self.tables.values())}
            del self.current_file_paths[index]
            self.current_file_paths = {new_index: value for new_index, value in enumerate(self.current_file_paths.values())}
            tab = self.tabs.widget(index)
            tab.deleteLater()
            self.tabs.removeTab(index)

    def closeEvent(self, evt):
        # 在这里编写程序退出时需要执行的代码
        TestPostCondition(self.tester).run()
        super().closeEvent(evt)


# noinspection PyUnresolvedReferences
class Worker(QObject):
    finished = pyqtSignal(object)  # 创建一个信号
    progress = pyqtSignal(str)
    def run(self):
        try:
            # ssh connector要先启动
            self.progress.emit('Initialize ssh connector...')
            env.ssh_connector = SSHConnector(hostname=env.ssh_hostname, username=env.ssh_username, password=env.ssh_password)
            self.progress.emit('Initialize sdc connector...')
            env.sdc_connector = SDCConnector(env.dbo_filepath, server_ip=env.sil_server_ip, server_port=env.sil_server_port)
            self.progress.emit('Initialize dds connector...')
            env.dds_connector = DDSConnector(idl_filepath=env.idl_filepath)
            self.progress.emit('Initialize tester...')
            env.tester = CaseTester(
                sub_topics=env.sub_topics,
                pub_topics=env.pub_topics,
                sdc_connector=env.sdc_connector,
                dds_connector=env.dds_connector,
                ssh_connector=env.ssh_connector
            )
            self.progress.emit('Initialize TestPrecondition ...')
            TestPrecondition(env.tester).run()
            self.progress.emit('Initialization done!')
            self.finished.emit(env.tester)  # 发射信号
        except Exception as e:
            error_info = traceback.format_exc()
            logger.error(error_info)
            error_message = (f'Initialization failed: {str(e)}\n'
                             f'Error Info: {error_info}')

            self.finished.emit(error_message)


class CustomSplashScreen(QSplashScreen):
    def __init__(self, pixmap):
        # self.windowFlags() 当前窗口的标志 无边框 不可最小化
        # super(CustomSplashScreen, self).__init__(pixmap)
        # self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint | Qt.WindowMinimizeButtonHint)

        super(CustomSplashScreen, self).__init__(pixmap, Qt.Window | Qt.FramelessWindowHint)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.WindowMinimizeButtonHint)
        self.setWindowTitle('SOA XBP 测试工具')
        self.setWindowIcon(QIcon('ui/icons/icon.ico'))
        self.message = 'Initialize...'
        self._start_pos = None

    def drawContents(self, painter):
        font = QFont()
        font.setFamily('Arial')
        font.setPointSize(12)
        painter.setFont(font)
        rect = QRect(0, 250, 600, 50)  # 根据你的需要设置文字显示的位置和区域，例如这里250就是离底部100的位置
        color = QColor(Qt.black)  # 设置文字颜色
        painter.setPen(color)
        painter.drawText(rect, Qt.AlignCenter, self.message)  # 使用之前设置的message绘制文字

    def mousePressEvent(self, event):
        self._start_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        self.move(self.pos() + event.globalPos() - self._start_pos)
        self._start_pos = event.globalPos()

    def mouseReleaseEvent(self, event):
        self._start_pos = None


def handle_exception(exc_type, exc_value, exc_traceback):
    """Handle all uncaught exceptions and print them to the console."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    print("Caught exception:", file=sys.stderr)
    traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)


def parse_commandline():
    app = QCoreApplication.instance()
    args = app.arguments()[1:]  # 0是程序名称本身，所以从1开始取
    print('parse_commandline: ', args)


# noinspection PyUnresolvedReferences
def main():
    sys.excepthook = handle_exception

    def update_splash(message):
        splash.message = message  # 将要显示的message传给splash
        splash.update()  # 更新splash显示

    def show_error_message(error_message):
        # 弹出错误提示，并结束程序
        msg_box = QMessageBox()
        msg_box.setWindowFlags(msg_box.windowFlags() | Qt.WindowStaysOnTopHint)
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle('Error')
        # msg_box.setText("An error has occurred. Please see the details below.")
        msg_box.setText("糟糕!!! 程序初始化过程异常，请见报错详情并联系作者本人. ")
        msg_box.setDetailedText(error_message)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec_()

    def on_worker_finished(result):
        # 创建一个槽函数，用于在Worker完成后，接收tester并创建显示App窗口
        if isinstance(result, str):
            # 弹出错误提示，并结束程序
            show_error_message(result)
            sys.exit(-1)
        elif isinstance(result, CaseTester):
            windows = App(result)
            windows.show()
            # parse_commandline()
            splash.finish(windows)
        tester_thread.quit()  # 退出新线程
        tester_thread.wait()  # 等待新线程退出

    # 支持高dpi缩放
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    # 显示Splash Screen
    splash_pix = QPixmap('ui/icons/splash.png')
    splash = CustomSplashScreen(splash_pix)
    splash.show()
    app.processEvents()  # 更新Splash
    # 创建并开始新线程
    tester_thread = QThread()
    tester_worker = Worker()
    tester_worker.moveToThread(tester_thread)
    tester_thread.started.connect(tester_worker.run)
    tester_worker.progress.connect(update_splash)
    tester_thread.start()
    # 连接Worker完成的信号和槽函数
    tester_worker.finished.connect(on_worker_finished)
    sys.exit(app.exec_())


def main2():
    app = QApplication(sys.argv)
    windows = App(tester='')
    windows.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
    # main2()
