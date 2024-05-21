# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Email   : likun19941001@163.com
# @Time    : 2024/3/29 15:37
# @File    : start_up.py

import os
import json
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIcon, QTextOption
from PyQt5.Qt import QLineEdit
from PyQt5.QtWidgets import (
    QVBoxLayout, QPushButton, QSpacerItem, QHBoxLayout, QLabel, QTextEdit, QFormLayout, QFrame, QFileDialog, QDialog,
    QSizePolicy, QRadioButton, QButtonGroup
)
from settings import env, work_dir
from connector.dds import DDSConnector, DDSConnectorRti


class PlatformConfigurationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_config_file = './data/cache/memory.json'
        self.load_last_config()
        self.setup_ui()

    def select_setting(self):
        # PyQt5中使用QFileDialog.getOpenFileName()方法选择一个文件
        # 参数依次是 窗口名字，起始路径，文件格式过滤器
        find_dir = os.path.normpath(os.path.join(work_dir, 'data', 'conf'))
        filepath, _ = QFileDialog.getOpenFileName(self, "选择配置文件", find_dir, "Setting File (*.yaml);;All Files (*)")
        if filepath:
            env.load(filepath)
            self.refresh_ui()

    def load_last_config(self):
        try:
            with open(self.last_config_file, 'r', encoding='utf-8') as f:
                res = json.load(f)
                env.load(res['settings_filepath'])
                env.disable_sdc = res['disable_sdc']
                env.has_topic_prefix = res['has_topic_prefix']
        except:
            pass

    def save_last_config(self):
        dir_path = './data/cache'
        if not os.path.exists(dir_path):
            os.mkdir(dir_path)
        with open(self.last_config_file, 'w', encoding='utf-8') as f:
            json.dump(
                {
                    'disable_sdc': self.disable_sdc_yes.isChecked(),
                    'settings_filepath': env.settings_filepath,
                    'has_topic_prefix': self.has_topic_prefix_yes.isChecked(),
                },
                f,
                ensure_ascii=False,
                indent=4
            )

    def refresh_ui(self):
        """ 从 env 对象更新界面元素"""
        if 'vbs_' in env.idl_filepath.lower():
            self.radio_platform_25.setChecked(True)
        else:
            self.radio_platform_20.setChecked(True)
        if self.disable_sdc_yes.isChecked():
            env.disable_sdc = True
        else:
            env.disable_sdc = False
        if self.has_topic_prefix_yes.isChecked():
            env.has_topic_prefix = True
        else:
            env.has_topic_prefix = False
        self.setting_file.setText(env.settings_filepath)
        self.ssh_hostname_edit.setText(env.ssh_hostname)
        self.ssh_username_edit.setText(env.ssh_username)
        self.ssh_password_edit.setText(env.ssh_password)
        self.local_net_segment_edit.setText(env.local_net_segment)
        self.idl_filepath_edit.setText(env.idl_filepath)
        self.case_dir_edit.setText(env.case_dir)
        self.sil_local_filepath_edit.setText(env.sil_local_filepath)
        self.sil_sdf_local_filepath_edit.setText(env.sil_sdf_local_filepath)
        self.sub_topics_edit.setPlainText('\n'.join(env.sub_topics))
        self.pub_topics_edit.setPlainText('\n'.join(env.pub_topics))

    def setup_ui(self):
        """
        # 没有帮助按钮；
        # 总是保持在其他窗口之上；
        # 显示最小化按钮。
        # 添加最大化按钮
        """
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowContextHelpButtonHint | Qt.WindowStaysOnTopHint | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
        )
        self.setWindowTitle('SOA A核测试工具 - 环境配置选择')
        self.setWindowIcon(QIcon('ui/icons/icon.ico'))
        layout = QVBoxLayout(self)
        # 选择配置
        # 左侧第一行
        setting_layout = QHBoxLayout()
        self.select_setting_btn = QPushButton('选择配置')
        self.select_setting_btn.clicked.connect(self.select_setting)
        setting_layout.addWidget(self.select_setting_btn)
        self.setting_file = QLineEdit()
        self.setting_file.setPlaceholderText(env.settings_filepath)
        setting_layout.addWidget(self.setting_file)
        layout.addLayout(setting_layout)
        # 是否禁用sdc
        layout.addWidget(QLabel('禁用sdc'))
        hbox0 = QHBoxLayout()
        self.disable_sdc_button_group = QButtonGroup(self)
        self.disable_sdc_yes = QRadioButton('是')
        self.disable_sdc_no = QRadioButton('否')
        self.disable_sdc_button_group.addButton(self.disable_sdc_yes)
        self.disable_sdc_button_group.addButton(self.disable_sdc_no)
        if env.disable_sdc:
            self.disable_sdc_yes.setChecked(True)
        else:
            self.disable_sdc_no.setChecked(True)
        hbox0.addWidget(self.disable_sdc_yes)
        hbox0.addWidget(self.disable_sdc_no)
        layout.addLayout(hbox0)
        # 平台选择的单选按钮
        layout.addWidget(QLabel('平台'))
        hbox1 = QHBoxLayout()
        self.platform_button_group = QButtonGroup(self)
        self.radio_platform_20 = QRadioButton('EEA2.0')
        self.radio_platform_25 = QRadioButton('EEA2.5')
        # self.radio_platform_20.setEnabled(False)
        # self.radio_platform_25.setEnabled(False)
        self.platform_button_group.addButton(self.radio_platform_20)
        self.platform_button_group.addButton(self.radio_platform_25)
        # 平台默认选项
        if 'vbs_' in env.idl_filepath:
            self.radio_platform_25.setChecked(True)
        else:
            self.radio_platform_20.setChecked(True)
        hbox1.addWidget(self.radio_platform_20)
        hbox1.addWidget(self.radio_platform_25)
        layout.addLayout(hbox1)
        # 是否带topic前缀
        layout.addWidget(QLabel('带Topic_前缀'))
        hbox2 = QHBoxLayout()
        self.select_box2 = QButtonGroup(self)
        self.has_topic_prefix_yes = QRadioButton('是')
        self.has_topic_prefix_no = QRadioButton('否')
        # self.radio_platform_20.setEnabled(False)
        # self.radio_platform_25.setEnabled(False)
        self.select_box2.addButton(self.has_topic_prefix_yes)
        self.select_box2.addButton(self.has_topic_prefix_no)
        # 平台默认选项
        if env.has_topic_prefix:
            self.has_topic_prefix_yes.setChecked(True)
        else:
            self.has_topic_prefix_no.setChecked(True)
        hbox2.addWidget(self.has_topic_prefix_yes)
        hbox2.addWidget(self.has_topic_prefix_no)
        layout.addLayout(hbox2)
        # -------------- 分割线 -------------- #
        hline = QFrame()
        hline.setFrameShape(QFrame.HLine)
        hline.setFrameShadow(QFrame.Sunken)
        layout.addWidget(hline)
        # 配置项的输入栏位
        layout.addWidget(QLabel('配置项'))
        form_layout = QFormLayout()
        self.ssh_hostname_edit = QLineEdit(env.ssh_hostname)
        self.ssh_username_edit = QLineEdit(env.ssh_username)
        self.ssh_password_edit = QLineEdit(env.ssh_password)
        self.local_net_segment_edit = QLineEdit(env.local_net_segment)
        self.idl_filepath_edit = QLineEdit(env.idl_filepath)
        self.case_dir_edit = QLineEdit(env.case_dir)
        self.sil_local_filepath_edit = QLineEdit(env.sil_local_filepath)
        self.sil_sdf_local_filepath_edit = QLineEdit(env.sil_sdf_local_filepath)
        self.sub_topics_edit = QTextEdit(self)
        self.sub_topics_edit.setWordWrapMode(QTextOption.WordWrap)
        self.sub_topics_edit.insertPlainText('\n'.join(env.sub_topics))
        self.pub_topics_edit = QTextEdit(self)
        self.pub_topics_edit.setWordWrapMode(QTextOption.WordWrap)
        self.pub_topics_edit.insertPlainText('\n'.join(env.pub_topics))
        form_layout.addRow('目标地址       ', self.ssh_hostname_edit)
        form_layout.addRow('目标用户名      ', self.ssh_username_edit)
        form_layout.addRow('目标密码       ', self.ssh_password_edit)
        form_layout.addRow('本地网卡       ', self.local_net_segment_edit)
        form_layout.addRow('SOA矩阵文件    ', self.idl_filepath_edit)
        form_layout.addRow('用例路径       ', self.case_dir_edit)
        form_layout.addRow('SiL仿真程序    ', self.sil_local_filepath_edit)
        form_layout.addRow('sdf文件路径    ', self.sil_sdf_local_filepath_edit)
        topic_layout = QHBoxLayout()
        sub_topic_layout = QVBoxLayout()
        sub_topic_layout.addWidget(QLabel('订阅topic'))
        sub_topic_layout.addWidget(self.sub_topics_edit)
        pub_topic_layout = QVBoxLayout()
        pub_topic_layout.addWidget(QLabel('发布topic'))
        pub_topic_layout.addWidget(self.pub_topics_edit)
        topic_layout.addLayout(sub_topic_layout)
        topic_layout.addLayout(pub_topic_layout)
        layout.addLayout(form_layout)
        layout.addLayout(topic_layout)
        layout.addItem(QSpacerItem(0, 20, QSizePolicy.Minimum, QSizePolicy.Fixed))
        # 确认和取消按钮
        buttons_layout = QHBoxLayout()
        button_confirm = QPushButton('确认')
        button_confirm.clicked.connect(self.confirm)
        button_cancel = QPushButton('取消')
        button_cancel.clicked.connect(self.reject)  # QDialog的reject方法将关闭对话框并返回0
        buttons_layout.addWidget(button_confirm)
        buttons_layout.addWidget(button_cancel)
        layout.addLayout(buttons_layout)
        # 根据内容自动调整大小
        self.setFont(QFont("Segoe UI", 10))  # 设置字体和字号
        self.setMinimumSize(600, 600)

    def confirm(self):
        # 更新配置
        env.ssh_hostname = self.ssh_hostname_edit.text()
        env.ssh_username = self.ssh_username_edit.text()
        env.ssh_password = self.ssh_password_edit.text()
        env.local_net_segment = self.local_net_segment_edit.text()
        env.idl_filepath = self.idl_filepath_edit.text()
        env.case_dir = self.case_dir_edit.text()
        env.sil_local_filepath = self.sil_local_filepath_edit.text()
        env.sil_sdf_local_filepath = self.sil_sdf_local_filepath_edit.text()
        env.sub_topics = [i for i in self.sub_topics_edit.toPlainText().split('\n') if i]
        env.pub_topics = [i for i in self.pub_topics_edit.toPlainText().split('\n') if i]
        # ...更新其他配置

        # 根据选择更新平台连接器
        if self.radio_platform_20.isChecked():
            env.DDSConnectorClass = DDSConnectorRti
            env.platform_version = 2.0
        elif self.radio_platform_25.isChecked():
            env.DDSConnectorClass = DDSConnector
            env.platform_version = 2.5
        if self.disable_sdc_yes.isChecked():
            env.disable_sdc = True
        else:
            env.disable_sdc = False
        if self.has_topic_prefix_yes.isChecked():
            env.has_topic_prefix = True
        else:
            env.has_topic_prefix = False
        self.accept()  # QDialog的accept方法将关闭对话框并返回1
        self.save_last_config()


if __name__ == '__main__':
    import sys
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    # 运行平台选择对话框
    dialog = PlatformConfigurationDialog()
    dialog.show()
    sys.exit(app.exec_())