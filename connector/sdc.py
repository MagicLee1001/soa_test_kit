# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2023/10/19 17:30
# @File    : sdc.py


import os
import threading
import socket
import struct
import time
from loguru import logger
from ctypes import *
from select import select
from runner.variable import Variable

# VARS_M2A = []
# VARS_M2A.append(Variable('M2A_test', 0))

VARS_A2M = {}
VARS_A2M['A2M_test'] = Variable('A2M_test', 0)
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
        ("signalName", c_char * 32),
        ("signalValue", c_float)
    ]


class StructM2A:
    def __init__(self, name: str, value: float, signal_type: int):
        self.name = name.encode('utf-8')
        self.value = value
        self.signal_type = signal_type

    def pack(self):
        return struct.pack('40sfi', self.name, self.value, self.signal_type)


class SDCConnector(threading.Thread):
    """
    因为sdc sil-server只允许一个客户端连接 这里将类重写成单例线程
    """
    recv_buffer = bytes()
    a2m_size = sizeof(StructA2M())
    _instance = None
    __first_init = False
    _instance_lock = threading.Lock()

    def __init__(self, dbo_filepath, server_ip='172.31.30.32', server_port=60000):
        """创建单例并只执行一次初始化 保证只有一个socket在使用"""
        with self._instance_lock:
            if not self.__first_init:
                super().__init__()
                self.keep_recv = True
                self.good_connection = False
                self.dbo_filepath = dbo_filepath
                self.pre_init()
                self.server_ip = server_ip
                self.server_port = server_port
                self.connect_server()
                SDCConnector.__first_init = True

    def __new__(cls, *args, **kwargs):
        """单例模式"""
        with cls._instance_lock:
            if not cls._instance:
                cls._instance = super().__new__(cls)
            return cls._instance

    def connect_server(self):
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket.connect((self.server_ip, self.server_port))
        self.client_socket.setblocking(False)
        self.good_connection = True

    def reconnect_server(self):
        """
        这里如果主动被调用一次,会导致 tcp_recv抛出异常, 从而触发这个方法会又被调用一次
        """
        self.close()
        self.good_connection = False
        self.__first_init = False
        while True:
            try:
                self.connect_server()
            except socket.error:
                self.close()
                time.sleep(2)
            else:
                break
        logger.success('reconnect sil server success')

    def close(self):
        self.client_socket.close()
        self.good_connection = False

    def tcp_send(self, signal):
        logger.info(f'发送TCP消息：{signal.name} = {signal.Value}')
        signal_name = str(signal.name).replace('M2A_', '')
        signal_value = signal.Value
        signal = StructM2A(signal_name, signal_value, map_data_type(signal_name))
        data = signal.pack()
        try:
            self.client_socket.sendall(data)
        except socket.error:
            logger.warning('TCP连接断开,正在尝试重连')
            self.good_connection = False
            self.reconnect_server()
            try:
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
                    signal_name_str = 'A2M_' + str(signal_name, encoding='utf-8')
                    signal = VARS_A2M.get(signal_name_str)
                except UnicodeDecodeError as e:
                    pass
                else:
                    if signal is not None:
                        signal.Value = signal_value
                        logger.info(f'接收TCP消息：{signal_name_str} = {signal_value}')

    def add_additional_signals(self):
        Variable('SIL_Client_CnnctSt', 0)
        Variable('SIL_Client_Cnnct', 0)
        Variable('Sw_HandWakeup', 0)

    def parse_dbo_a2m(self):
        if os.path.exists(self.dbo_filepath):
            with open(self.dbo_filepath, 'r') as file:
                for line in file:
                    if 'tx' in line:
                        index = line.find(',')
                        if index != -1:
                            VARS_A2M['A2M_' + line[2:index]] = Variable('A2M_' + line[2:index], 0)

    def parse_dbo_m2a(self):
        if os.path.exists(self.dbo_filepath):
            with open(self.dbo_filepath, 'r') as file:
                for line in file:
                    if 'rx' in line:
                        index = line.split(',')
                        Variable('M2A_' + index[0][2:], 0)
                        # data = Variable('M2A_' + index[0][2:], 0)
                        # VARS_M2A.append(data)
                        M2A_NAME_TYPE[index[0][2:]] = index[2]

    def pre_init(self):
        logger.info('Parse dbo signals to Variable')
        self.add_additional_signals()
        self.parse_dbo_m2a()
        self.parse_dbo_a2m()

    def run(self) -> None:
        while self.keep_recv:
            try:
                self.tcp_recv()
            except socket.error:
                logger.warning('TCP连接断开,正在尝试重连')
                if not self.good_connection:
                    self.reconnect_server()
                self.good_connection = False
        logger.info('sdc 接收线程退出')
        self.close()


if __name__ == '__main__':
    from settings import env
    # # 创建TCP socket并连接到指定的IP和端口
    # ip = '172.31.30.32'
    # port = 60000
    # client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # client_socket.connect((ip, port))
    # client_socket.setblocking(False)
    # while True:
    #     SIL_Client_CnnctSt.Value = 1
    #     signal = StructM2A('SIL_Client_CnnctSt', 1, map_data_type('SIL_Client_CnnctSt'))
    #     data = signal.pack()
    #     try:
    #         res = client_socket.sendall(data)
    #     except Exception as e:
    #         logger.error(e)
    #     time.sleep(10)

    # 类调试
    sdc_client = SDCConnector(env.dbo_filepath, server_ip=env.sil_server_ip, server_port=env.sil_server_port)
    sdc_client.start()  # I/O多路复用 持续接收
    time.sleep(2)

    # 接收同时测试发送
    # 这一步全局Variable已经初始化完成了，只需要改变信号值就行

    signal = Variable('M2A_FrtACSwSts_Inner')
    signal.Value = 1
    while True:
        sdc_client.tcp_send(signal)
        time.sleep(2)
    # print(sizeof(StructA2M()))
    # sdc_client.close()
