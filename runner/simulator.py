# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Email   : likun19941001@163.com
# @Time    : 2024/1/31 13:28
# @File    : simulator.py

import socket
import threading
import time

from runner.log import logger
from settings import env
from runner.variable import Variable

"""
在Qt应用程序中启动后台TCP多线程仿真，理论上是可以使用Python的threading模块，但这并不是最佳做法。
使用threading模块通常是在编写常规Python脚本时的选择，
在Qt环境中，为了线程安全并遵循Qt的设计理念，推荐使用Qt自身的线程管理工具QThread来处理多线程

避免在子线程中直接进行UI操作；
使用安全的方式处理数据共享和同步，例如使用threading.Lock；
尽可能将TCP服务器逻辑与Qt GUI逻辑分离，以减少线程间的耦合。
"""


class VehicleModeDiagnostic:
    """
    车模式ECU诊断信息在这里维护即可
    """
    _lock = threading.Lock()
    ecu_target_id = {
        '0c01': 'XCU',
        '0401': 'HU',
        '0409': 'FSD',
        '0792': 'FBCM',
        '0793': 'RBCM',
        '07a1': 'ASU'
    }
    # 0表示成功，1表示失败
    ecu_state = {
        'XCU': 0,
        'HU': 0,
        'FSD': 0,
        'FBCM': 0,
        'RBCM': 0,
        'ASU': 0
    }

    @classmethod
    def get_state(cls, ecu_name):
        with cls._lock:
            return cls.ecu_state[ecu_name]

    @classmethod
    def set_state(cls, ecu_name, state):
        with cls._lock:
            cls.ecu_state[ecu_name] = state
        Variable(f'SIL_VMS_{ecu_name}').Value = state


class DiagnosticMessage:
    special_for_27_dict = {
        "01": "55555555",
        "09": "00000000",
        "0a": "00"
    }
    
    @classmethod
    def get_confirm_msg(cls, pyload_data):
        try:
            veh_discovery_resp_str = '02fd800200000005'
            source_addr = pyload_data[0:2]
            target_addr = pyload_data[2:4]
            veh_discovery_resp_str = veh_discovery_resp_str + target_addr.hex() + source_addr.hex() + "00"
            resp_data = bytes.fromhex(veh_discovery_resp_str)
        except Exception as e:
            logger.error(e)
        else:
            return resp_data
    
    @classmethod
    def get_indication_msg(cls, payload_data):
        try:
            source_addr = payload_data[0:2]
            target_addr = payload_data[2:4]
            diagnostic_message = payload_data[4:len(payload_data)]
            sid = diagnostic_message[0]
            result_msg = '7f' + '{:02x}'.format(int(sid)) + '7f'  # default nrc7f

            # secure access
            if sid == 0x27:
                if diagnostic_message[1] == 0x01:  # 27 01 请求种子
                    security_access_type = '{:02x}'.format(int(diagnostic_message[1]))  # eg: 0x01 -> '01'
                    result_msg = "67" + security_access_type + cls.special_for_27_dict["01"]
                elif diagnostic_message[1] == 0x02:  # 27 92 发送密钥
                    security_access_type = "67" + '{:02x}'.format(int(diagnostic_message[1]))
                    result_msg = security_access_type
                elif diagnostic_message[1] == 0x09:
                    security_access_type = '{:02x}'.format(int(diagnostic_message[1]))
                    result_msg = "67" + security_access_type + cls.special_for_27_dict["09"]
                elif diagnostic_message[1] == 0x0A:
                    security_access_type = '{:02x}'.format(int(diagnostic_message[1]))
                    result_msg = "67" + security_access_type + cls.special_for_27_dict["0a"]
                else:
                    security_access_type = '{:02x}'.format(int(diagnostic_message[1]))
                    result_msg = "67" + security_access_type + "0000"

            elif sid == 0x10:
                result_msg = '50' + '{:02x}'.format(int(diagnostic_message[1])) + "55555555"

            # write data by did
            elif sid == 0x2E:
                write_id = diagnostic_message[1:3]
                result_msg = "6e" + write_id.hex()

            elif sid == 0x31:
                rct_id = diagnostic_message[1:4].hex()  # routine control type and routine id
                if rct_id == '01df00':  # 车辆模式切换
                    ecu_state = VehicleModeDiagnostic.get_state(VehicleModeDiagnostic.ecu_target_id[target_addr.hex()])
                    result_msg = '71' + rct_id + '{:02x}'.format(int(ecu_state))

            ret_str_head = "02fd8001"
            payload_str = target_addr.hex() + source_addr.hex() + result_msg
            len_bytes = int((len(payload_str) / 2)).to_bytes(4, byteorder='big')
            resp_str = ret_str_head + len_bytes.hex() + payload_str
            resp_data = bytes.fromhex(resp_str)
            return resp_data
        except Exception as e:
            logger.error(e)


class RoutingActivation:
    routing_activ_resp_str = "02fd000600000009"
    
    @classmethod
    def get_routing_activation_resp_data(cls, payload_data):
        try:
            src_addr = payload_data[0:2]
            routing_activ_resp_str = cls.routing_activ_resp_str + src_addr.hex() + '0c01' + '10' + '00000000'
        except Exception as e:
            logger.error(e)
        else:
            resp_data = bytes.fromhex(routing_activ_resp_str)
            return resp_data


class ConnectionHandle(threading.Thread):
    def __init__(self, connection, resp_timeout=0):
        super().__init__()
        logger.info('New connection created!')
        self.running = True
        self.conn = connection
        self.resp_timeout = resp_timeout
        self.conn.setblocking(1)

    def run(self) -> None:
        while self.running:
            try:
                header_data = self.conn.recv(8)  # 8 bytes = head(2) + payload type(2) + payload len(4)
                if len(header_data) == 8:
                    if header_data[0] == 0x02 and header_data[1] == 0xFD:  # correct 13400-2:2012 head
                        payload_type = (header_data[2] << 8) + header_data[3]
                        payload_len = ((header_data[4] << 24) + (header_data[5] << 16) + (header_data[6] << 8)
                                       + header_data[7])
                        payload_data = ''
                        if payload_len > 0:
                            payload_data = self.conn.recv(payload_len)
                            while len(payload_data) != payload_len:
                                logger.info('not full receive data, try again!!!')
                                rest_payload_data = self.conn.recv(payload_len-len(payload_data))
                                payload_data += rest_payload_data
                        else:
                            logger.info('no payload needed')

                        print_len = 30 if len(payload_data) > 30 else len(payload_data)
                        if print_len == 30:
                            logger.info(f"doip request  : {header_data.hex()} "
                                        f"{payload_data[0:4].hex()} {payload_data[4:print_len].hex()} ......")
                        else:
                            logger.info(f"doip request  : {header_data.hex()} "
                                        f"{payload_data[0:4].hex()} {payload_data[4:print_len].hex()}")

                        # Routing activation request
                        if payload_type == 0x0005:
                            logger.info("routing activation request")
                            resp_data = RoutingActivation.get_routing_activation_resp_data(payload_data)
                            self.conn.send(resp_data)
                            logger.info(f"doip response : {resp_data[0:8].hex()} "
                                        f"{resp_data[8:12].hex()} {resp_data[12:len(resp_data)].hex()}")

                        # Alive check request
                        elif payload_type == 0x0007:
                            logger.info("alive check request")

                        # Diagnostic message
                        elif payload_type == 0x8001:
                            # ack
                            resp_data = DiagnosticMessage.get_confirm_msg(payload_data)
                            self.conn.send(resp_data)
                            logger.info(f"doip confirm  : {resp_data[0:8].hex()} "
                                        f"{resp_data[8:12].hex()} {resp_data[12:len(resp_data)].hex()}")

                            # can indication
                            can_data = DiagnosticMessage.get_indication_msg(payload_data)
                            if can_data:
                                self.conn.send(can_data)
                                logger.info(f"doip indicate : {can_data[0:8].hex()} "
                                            f"{can_data[8:12].hex()} {can_data[12:len(can_data)].hex()}")
                        else:
                            logger.warning("not supported payload type")

                        if payload_data[4:8].hex() == "22f15c":
                            logger.warning(f"special diag old request 22f15c socket will be closed: "
                                           f"{payload_data[4:8].hex()}")
                            self.conn.close()
                    else:
                        logger.error("head error not 13400 frame")
                    logger.info('-'*90)

            except Exception as e:
                self.running = False
                self.conn.close()
                logger.error(e)


class DoIPMonitorThread(threading.Thread):
    def __init__(self, resp_timeout=0):
        super().__init__()
        self.resp_timeout = resp_timeout
        self.port = 13400
        self.server_host = env.local_net_segment
        self._is_running = threading.Event()
        self.sk = socket.socket()
        self.sk.settimeout(1.0)  # 改成非阻塞型
        self.sk.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sk.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sk.bind((self.server_host, self.port))
        self.sk.listen(10)
        logger.info(f"TCP socket create! bind {self.server_host} {self.port}")

    def stop(self):
        self._is_running.set()

    def run(self) -> None:
        # logger.info('DoIPMonitorThread start')
        # 车辆模式ECU状态信号添加
        for ecu_name, state in VehicleModeDiagnostic.ecu_state.items():
            Variable(f'SIL_VMS_{ecu_name}', state)
        try:
            while not self._is_running.is_set():
                try:
                    conn, addr = self.sk.accept()  # 非阻塞型 便于主线程退出
                    logger.info(f'client connected: {conn}')
                    conn_handle = ConnectionHandle(conn, resp_timeout=self.resp_timeout)
                    conn_handle.daemon = True  # 设置为守护线程 主线程退出后响应线程都强制关闭
                    conn_handle.start()
                except socket.timeout:
                    pass
        except Exception as e:
            logger.error(e)

        finally:
            self.sk.close()  # 确保所有情况下套接字都正确关闭
            logger.info('DoIP仿真监听线程退出 所有子线程均安全退出')


if __name__ == '__main__':
    doip_sim = DoIPMonitorThread()
    doip_sim.start()
    # time.sleep(1)
    # doip_sim.stop()
