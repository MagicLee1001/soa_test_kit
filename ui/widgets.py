# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Email   : likun19941001@163.com
# @Time    : 2024/3/29 14:15
# @File    : widgets.py

import os
import time
import json
import traceback
import subprocess
from runner.log import logger
from PyQt5 import QtWidgets, QtGui, QtCore, sip
from PyQt5.QtCore import Qt, QPoint, QRect, QSize, QModelIndex, pyqtSignal, QCoreApplication, QDateTime
from PyQt5.QtGui import QStandardItemModel, QTextCursor, QFont, QIcon, QBrush, QPixmap, QColor, QTextOption
from PyQt5.Qt import QStringListModel, QCompleter, QLineEdit, QListView, QMutex, QThread, QObject, QTimer
from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QSplashScreen, QTabWidget, QVBoxLayout, QPushButton, QWidget, QTableWidget, QSpacerItem,
    QHBoxLayout, QHeaderView, QTableWidgetItem, QLabel, QCheckBox, QScrollArea, QTextEdit, QMessageBox, QFormLayout,
    QFrame, QAction, QFileDialog, QStyle, QStyleOptionViewItem, QStyleOptionButton, QInputDialog, QTabBar, QDialog,
    QComboBox, QListWidget, QListWidgetItem, QProgressBar, QMenu, QPlainTextEdit, QSplitter, QSizePolicy, QActionGroup,
    QRadioButton, QButtonGroup, QDateTimeEdit, QDialogButtonBox
)
from runner.simulator import VehicleModeDiagnostic


class DDSFuzzDatePickerDialog(QDialog):
    datetime_selected = pyqtSignal(QDateTime)

    def __init__(self, app, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app = app
        self.init_ui()

    def init_ui(self):
        self.resize(200, 200)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # 取消帮助
        self.setWindowIcon(QIcon('ui/icons/icon.ico'))
        self.setWindowTitle("选择日期和时间")
        layout = QVBoxLayout(self)
        self.datetime_edit = QDateTimeEdit(QDateTime.currentDateTime(), self)
        self.datetime_edit.setCalendarPopup(True)
        layout.addWidget(self.datetime_edit)
        buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        layout.addWidget(buttonBox)
        buttonBox.accepted.connect(self.accept_selection)
        buttonBox.rejected.connect(self.reject)

    def accept_selection(self):
        selected_datetime = self.datetime_edit.dateTime()
        self.datetime_selected.emit(selected_datetime)
        self.accept()


class CustomListWidget(QListWidget):
    """ 加载用例的显示列表"""
    def __init__(self, app, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app = app
        self.setSortingEnabled(False)
        # 允许多选
        self.setSelectionMode(QListWidget.ExtendedSelection)

    def contextMenuEvent(self, event):
        """
        用例列表提供选择，自由框选，全选，删除，全选删除功能
        """
        try:
            menu = QMenu(self)
            delete_action = menu.addAction("删除")
            delete_all_action = menu.addAction("全部删除")
            select_all_action = menu.addAction("全选")
            open_folder_action = menu.addAction("打开文件所在位置")
            action = menu.exec_(self.mapToGlobal(event.pos()))

            selected_items = self.selectedItems()
            if action == delete_action and selected_items:
                # 从后往前删除以避免索引变化问题
                for item in sorted(selected_items, key=lambda x: self.row(x), reverse=True):
                    row_index = self.row(item)
                    self.takeItem(row_index)
                    # 注意：这里假设self.app.case_filepaths和列表项目保持同步
                    self.app.case_filepaths.pop(row_index)
            elif action == delete_all_action:
                    self.clear()
                    self.app.case_filepaths = []
            elif action == select_all_action:
                self.selectAll()
            elif action == open_folder_action:
                if selected_items and self.app.case_filepaths:
                    folder_path = os.path.normpath(os.path.dirname(self.app.case_filepaths[self.row(selected_items[0])]))
                    subprocess.run(f'explorer "{folder_path}"')  # 执行带空格的路径时，确保路径用引号包围
        except:
            logger.error(traceback.format_exc())


class CustomTableWidget(QTableWidget):
    """ 表格控件，手动测试使用"""
    def __init__(self, app, *args, **kwargs):
        super(CustomTableWidget, self).__init__(*args, **kwargs)
        self.app = app

    def keyPressEvent(self, event):
        # 判断是否按下了删除键
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.app.delete_row(self)
        # 按下回车键 直接运行
        elif event.key() in (Qt.Key_Enter, Qt.Key_Return):
            self.app.input_table_process()
        super().keyPressEvent(event)


class CheckBoxHeader(QHeaderView):
    """ 表格第一列勾选框 已取消该功能"""
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
    """ 搜索补全器滚动条"""
    def sizeHintForColumn(self, column):
        return self.sizeHintForIndex(self.model().index(0, column)).width()


class CustomLogText(QPlainTextEdit):
    """ 日志文本框"""
    def __init__(self, max_lines=1000):
        super().__init__()
        self.max_lines = max_lines
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

    def appendPlainText(self, text):
        super().appendPlainText(text)
        try:
            if self.document().blockCount() > self.max_lines:
                # 移除旧日志，保持日志行数
                cursor = self.textCursor()
                cursor.movePosition(cursor.Start)
                cursor.select(cursor.BlockUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()
        except Exception as e:
            logger.error(e)


class SafeLogHandler(QtCore.QObject):
    """
    在Qt框架中，几乎所有的GUI组件，包括QPlainTextEdit，都不是线程安全的。
    这就意味着你不能在除主线程之外的任何线程中操作它们。
    如果你试图在其他线程中操作GUI组件，可能会导致不可预见的行为，包括闪退、数据错误和死锁等。
    不应该直接在该线程中操作QPlainTextEdit，应该使用信号和槽机制来将内容发送给主线程，并在槽函数中更新QPlainTextEdit
    """
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


class CustomerLogArea(QScrollArea):
    """ 日志滚动区域"""
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
        try:
            self.log_widget.appendPlainText(text)
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
        except:
            pass


class ECUSelectionDialog(QDialog):
    """
    模态 (Modal) 和非模态 (Non-modal) 对话框的主要区别在于它们是否允许用户与父窗口（或主应用程序）的其他部分进行交互。
    模态对话框 (Modal dialog):
        一旦弹出，用户必须先响应完模态对话框（关闭或隐藏该对话框），才能返回到父窗口进行其他操作。
        模态对话框通常用于需要用户完成某些必要操作或作出决策之后才能继续的情况，如保存文件、确认删除等。在模态对话框打开时，父窗口的控件不可用。
    非模态对话框 (Non-modal dialog):
        当非模态对话框打开时，用户仍然可以与父窗口的其他控件交互，不需要显式地关闭对话框。
        非模态对话框适用于不阻断主窗口操作的场合，如提供额外信息、显示日志、实时更新数据等
    """

    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.setModal(False)  # 设置非模态
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # 取消帮助
        self.setWindowTitle('车辆模式ECU选择')
        layout = QVBoxLayout(self)

        # 创建并添加复选框到布局
        for ecu_name, ecu_state in VehicleModeDiagnostic.ecu_state.items():
            checkbox = QCheckBox(ecu_name)
            if ecu_state == 0:
                checkbox.setChecked(True)
            else:
                checkbox.setChecked(False)
            checkbox.toggled.connect(lambda option_state, ecu=ecu_name: self.callback(ecu, option_state))
            layout.addWidget(checkbox)

        self.setLayout(layout)
        self.setMinimumSize(200, 300)


class CustomSplashScreen(QSplashScreen):
    """ 软件正式启动前的加载界面"""
    def __init__(self, pixmap):
        # self.windowFlags() 当前窗口的标志 无边框 不可最小化
        # super(CustomSplashScreen, self).__init__(pixmap)
        # self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint | Qt.WindowMinimizeButtonHint)

        super(CustomSplashScreen, self).__init__(pixmap, Qt.Window | Qt.FramelessWindowHint)
        # 保持窗口始终在顶部，并能最小化
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.WindowMinimizeButtonHint)
        self.setWindowTitle('SOA A核测试工具')
        self.setWindowIcon(QIcon('ui/icons/icon.ico'))
        self.message = 'Initialize...'
        self._start_pos = None
        # 设置窗口的大小不可变 不可被拉伸
        self.setFixedSize(self.size())

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


class ErrorDialog(QDialog):
    def __init__(self, error_message, parent=None):
        super().__init__(parent)

        # 设置对话框为最大化
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setWindowTitle('Error')
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        # 使用垂直布局
        layout = QVBoxLayout()

        # 错误消息标签
        label = QLabel("糟糕! 程序初始化过程异常，请见报错详情并联系作者本人.")
        layout.addWidget(label)

        # 显示详细错误信息的文本框
        text_edit = QTextEdit()
        text_edit.setFont(QFont("Segoe UI", 10))  # 设置字体和字号
        text_edit.setText(error_message)
        text_edit.setReadOnly(True)
        layout.addWidget(text_edit)

        # 确定按钮
        ok_button = QPushButton("Ok")
        ok_button.clicked.connect(self.accept)
        layout.addWidget(ok_button)

        self.setLayout(layout)

    def exec_(self):
        # Make dialog resizable and maximizable
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint | Qt.WindowSystemMenuHint)
        return super().exec_()


class SilConnectionLabel(QLabel):
    def __init__(self, app, *args, **kwargs):
        super(SilConnectionLabel, self).__init__(*args, **kwargs)
        self.app = app

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.show_context_menu(event.pos())
        else:
            # 调用基类实现以处理其他类型的点击，例如左键点击
            super().mousePressEvent(event)

    def show_context_menu(self, position):
        try:
            context_menu = QMenu(self)
            deploy = context_menu.addAction('部署sil仿真程序并建立连接')
            undeploy = context_menu.addAction('移除sil仿真程序')
            action = context_menu.exec_(self.mapToGlobal(position))
            if action == deploy:
                self.app.deploy_sil_node_task.start()
            elif action == undeploy:
                self.app.undeploy_sil_node_task.start()
        except:
            logger.error(traceback.format_exc())
