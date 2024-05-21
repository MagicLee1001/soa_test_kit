# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Email   : likun19941001@163.com
# @Time    : 2023/10/19 17:30
# @File    : sdc.py

import os
import threading
import socket
import struct
import time

from runner.log import logger
from ctypes import Structure, c_char, c_float, sizeof, memmove, addressof
from select import select
from runner.variable import Variable
from settings import env

M2A_NAME_TYPE = {}


def map_data_type(signal_name):
    if M2A_NAME_TYPE.get(signal_name) == 'bool':
        return 3
    elif M2A_NAME_TYPE.get(signal_name) == 'uint32_t':
        return 4
    elif M2A_NAME_TYPE.get(signal_name) == 'uint64_t':
        return 5
    elif M2A_NAME_TYPE.get(signal_name) == 'int32_t':
        return 6
    elif M2A_NAME_TYPE.get(signal_name) == 'int64_t':
        return 7
    elif M2A_NAME_TYPE.get(signal_name) == 'float':
        return 8
    elif M2A_NAME_TYPE.get(signal_name) == 'double':
        return 9
    elif M2A_NAME_TYPE.get(signal_name) == 'uint8_t':
        return 4
    elif M2A_NAME_TYPE.get(signal_name) == 'uint16_t':
        return 4
    elif M2A_NAME_TYPE.get(signal_name) == 'uint16_t':
        return 4
    elif M2A_NAME_TYPE.get(signal_name) == 'int8_t':
        return 6
    elif M2A_NAME_TYPE.get(signal_name) == 'int16_t':
        return 6
    else:
        return 8


class StructA2M(Structure):
    _fields_ = [
        ("signalName", c_char * 64),
        ("signalValue", c_float)
    ]


class StructM2A:
    def __init__(self, name: str, value: float, signal_type: int):
        self.name = name.encode('utf-8')
        self.value = value
        self.signal_type = signal_type

    def pack(self):
        return struct.pack('64sfi', self.name, self.value, self.signal_type)


class SDCConnector(threading.Thread):
    """
    因为 sdc sil-server只允许一个客户端连接 这里将类重写成单例线程
    注意: 该实例线程整个生命周期只能启动一次 (多线程的特性)
    """
    recv_buffer = bytes()
    a2m_size = sizeof(StructA2M())
    _instance = None
    __first_init = False
    _instance_lock = threading.Lock()
    conn_lock = threading.Lock()
    _is_reconnecting = threading.Event()  # 重连事件标志

    def __init__(self, dbo_filepath, server_ip='172.31.30.32', server_port=60000):
        """创建单例并只执行一次初始化 保证只有一个socket在使用"""
        with self._instance_lock:
            if not self.__first_init:
                super().__init__()
                self.started = False
                self._is_keep_recv = threading.Event()
                self._is_reconnecting.clear()
                self.dbo_filepath = dbo_filepath
                self.pre_init()
                self.server_ip = server_ip
                self.server_port = server_port
                self.client_socket = None
                SDCConnector.__first_init = True

    def __new__(cls, *args, **kwargs):
        """单例模式"""
        with cls._instance_lock:
            if not cls._instance:
                cls._instance = super().__new__(cls)
            return cls._instance

    def connect_server(self):
        """
        实例化后必须要放在主线程先调用，否则子线程抛出异常无法阻止主线程的运行
        导致GUI操作收发接口会卡死
        Returns:

        """
        with self.conn_lock:  # 加锁防止同一时间重复连接出问题
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.server_ip, self.server_port))
            self.client_socket.setblocking(False)
            logger.info(f'连接sil成功 ip: {self.server_ip}, port: {self.server_port}')
            env.sil_node_status = 1

    def reconnect_server(self):
        """
        这里如果主动被调用一次,会导致 tcp_recv抛出异常, 从而触发这个方法会又被调用一次
        """
        if self._is_reconnecting.is_set():
            # 已有重连在进行，不需要再次重连
            return
        self._is_reconnecting.set()  # 设置重连标志
        self.close()
        while not self._is_keep_recv.is_set():
            try:
                self.connect_server()
            except socket.error:
                self.close()
                time.sleep(1)
            else:
                break
        logger.success('reconnect sil server success')
        self._is_reconnecting.clear()

    def close(self):
        self.client_socket.close()

    def tcp_send(self, signal):
        logger.info(f'发送TCP消息：{signal.name} = {signal.Value}')
        signal_name = str(signal.name).replace('M2A_', '')
        signal_value = signal.Value
        signal = StructM2A(signal_name, signal_value, map_data_type(signal_name))
        data = signal.pack()
        try:
            self.client_socket.sendall(data)
        except socket.error:
            env.sil_node_status = 2
            if not self._is_reconnecting.is_set():
                logger.warning('TCP连接断开, 正在尝试重连并重新发送消息')
                self.reconnect_server()
            else:
                # 等待重连事件结束
                logger.info('TCP连接断开, 等待重连')
                while self._is_reconnecting.is_set():
                    time.sleep(0.5)
                # 重连完成后再次尝试发送数据
                try:
                    logger.info('重新发送成功消息成功')
                    self.client_socket.sendall(data)
                except Exception as e:
                    logger.error(e)
        except Exception as e:
            logger.error(e)

    def tcp_recv(self):
        """
        非阻塞行为：没有超时参数的 select 调用默认是阻塞的，意味着它会一直等待直到有文件描述符就绪（可读、可写或出错）。
        如果网络交互不频繁，线程可能会长时间阻塞在这里。
        设置超时参数允许 select 在指定的时间后返回，即使没有文件描述符就绪。这使得线程能够定期“醒来”并执行其他可能的任务，比如检查是否有终止信号。
        改进的响应性：通过在 select 调用中设置超时，您可以让线程在低延迟的情况下检测和响应外部条件变化，如程序退出或用户输入。
        资源释放和清理：设置超时使得线程有机会进行周期性的清理工作，例如关闭无效的套接字连接，释放不再需要的资源等。
        减少死锁风险：在多线程程序中，长时间阻塞的线程可能会增加程序陷入死锁的风险。通过设置超时，可以减少线程因单一操作而导致的死锁几率。
        """
        if self.client_socket is None or self.client_socket.fileno() == -1:
            # 这里处理套接字未打开或已关闭的情况
            return
        self.recv_buffer = bytes()
        ready_to_read, ready_to_write, in_error = select([self.client_socket], [], [], 0.5)
        if ready_to_read:
            data = self.client_socket.recv(1024)
            self.recv_buffer = self.recv_buffer + data
            while len(self.recv_buffer) >= self.a2m_size:
                package = self.recv_buffer[:self.a2m_size]
                self.recv_buffer = self.recv_buffer[self.a2m_size:]
                c = StructA2M()
                memmove(addressof(c), package, sizeof(c))
                signal_name = c.signalName
                signal_value = c.signalValue
                try:
                    # if signal_name == b'StrWhlSeatAutoSeatSwReq_out_Inne':  # 信号名太长可能被截断
                    #     signal_name = b'StrWhlSeatAutoSeatSwReq_out_Inner'
                    signal_name_str = 'A2M_' + str(signal_name, encoding='utf-8')
                    signal = Variable(signal_name_str)
                except UnicodeDecodeError:
                    pass
                else:
                    if signal is not None:
                        signal.Value = signal_value
                        logger.info(f'接收TCP消息：{signal_name_str} = {signal_value}')

    def add_additional_signals(self):
        Variable('SIL_Client_CnnctSt').Value = 1
        Variable('SIL_Client_Cnnct').Value = 1
        Variable('Sw_HandWakeup').Value = 1

    def parse_dbo_a2m(self):
        if os.path.exists(self.dbo_filepath):
            with open(self.dbo_filepath, 'r') as file:
                for line in file:
                    if 'tx' in line:
                        index = line.find(',')
                        if index != -1:
                            Variable('A2M_' + line[2:index], 0)

    def parse_dbo_m2a(self):
        if os.path.exists(self.dbo_filepath):
            with open(self.dbo_filepath, 'r') as file:
                for line in file:
                    if 'rx' in line:
                        line_items = line.split(',')
                        signal_name = line_items[0][2:]
                        Variable(f'M2A_{signal_name}', 0)
                        M2A_NAME_TYPE[signal_name] = line_items[2]

    def pre_init(self):
        logger.info('Parse dbo signals to Variable')
        self.add_additional_signals()
        self.parse_dbo_m2a()
        self.parse_dbo_a2m()

    def stop(self):
        self._is_keep_recv.set()

    def run(self) -> None:
        self.started = True
        while not self._is_keep_recv.is_set():
            try:
                self.tcp_recv()  # select设置了超时时间 超过时间就会继续循环
            except socket.error:
                env.sil_node_status = 2
                if not self._is_reconnecting.is_set():
                    logger.warning('TCP连接断开, TCP消息接收线程触发重连 ...')
                    self.reconnect_server()
        logger.info('sdc 接收tcp消息线程退出')
        self.close()


if __name__ == '__main__':
    sdc_client = SDCConnector(env.dbo_filepath, server_ip=env.sil_server_ip, server_port=1111)
    sdc_client.connect_server()  # 必须要先调用
    sdc_client.start()  # I/O多路复用 持续接收
    # time.sleep(2)
    # sdc_client.reconnect_server()
    #
    # # 接收同时测试发送
    # # 这一步全局Variable已经初始化完成了，只需要改变信号值就行
    # signal = Variable('M2A_FrtACSwSts_Inner')
    # signal.Value = 1
    # while True:
    #     sdc_client.tcp_send(signal)
    #     time.sleep(2)
