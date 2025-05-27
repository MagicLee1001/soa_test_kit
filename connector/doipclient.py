# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2025/4/2 14:08
# @File    : doipclient.py

import os
import queue
import sys
import time
import threading
import socket
import select
import traceback
import math
import binascii
from queue import Queue
from loguru import logger
from functools import wraps
from ctypes import Structure, cdll, c_uint8, c_uint, c_int, c_uint16, c_char, c_int64
from settings import work_dir
from runner.variable import Variable

"""
DoIP协议报文规范 -- Li.Auto.2025
------------------------------------------------------
Header: 
    0x02                  // Protocol Version
    0xFD                  // Inverse Protocol Version 
    0x80 0x01             // Payload Type（诊断消息）
    0x00 0x00 0x00 0x06   // Payload Length = Payload字节长度

Payload:  
    0X0E 0x02             // 源逻辑地址
    0x0C 0x01             // 目标逻辑地址
    0x10                  // Service ID
    0x03                  // Sub-Function、DID...
    ...
------------------------------------------------------

Payload Type如下:
0x0001 - Vehicle Identification Request      车辆发现请求
0x0004 - Vehicle Identification Response     车辆发现响应
0x0002 - Generic DoIP Header ACK             通用头部确认
0x0003 - Generic DoIP Header NACK            通用头部错误：表示Header字段非法（如协议版本不兼容）
0x0005 - Routing Activation Request          路由激活请求
0x0006 - Routing Activation Response         路由激活响应
0x0007 - Alive Check Request                 心跳检测请求
0x0008 - Alive Check Response                心跳检测响应
0x8001 - Diagnostic Message                  诊断消息（包括请求与响应）
0x8002 - Diagnostic Message ACK              诊断消息确认 （非具体响应）
0x8003 - Diagnostic Message NACK             诊断消息拒绝 （表示诊断消息格式错误或无法处理）

"""


class SAInputStructure(Structure):
    _fields_ = [("seed", c_uint8 * 256), ("seed_length", c_int), ("level", c_int), ("param", c_uint8 * 256),
                ("key_length", c_int)]


class SAOutputStructure(Structure):
    _fields_ = [("ret_value", c_uint8), ("key", c_uint8 * 256), ("key_len", c_uint)]


def seed_cal_key(seed: int, mask: int, level=1):
    sa_key_str = ""
    # logger.info(f"Seed: {hex(seed)}, Mask: {hex(mask)}")
    if level == 1:
        w_sub_seed = seed  # 将种子的值赋值给变量w_sub_seed
        middle = int((mask & 0x00010000) >> 15) | (
                (mask & 0x00004000) >> 14)  # 掩码与值位与运算，保留低字节后两位
        if middle == 0:
            w_middle = seed & 0x000000ff  # 种子与值进行位与运算
        elif middle == 1:
            w_middle = (seed & 0x0000ff00) >> 8  # 种子与值进行与运算后右移8位
        elif middle == 2:
            w_middle = (seed & 0x00ff0000) >> 16  # 种子与值进行与运算后右移16位
        elif middle == 3:
            w_middle = (seed & 0xff000000) >> 24  # 种子与值进行与运算后右移24位
        else:
            return False

        db1 = ((mask & 0x000007F8) >> 3)  # 掩码与值位与运算，保留低字节
        db2 = (((mask & 0x7F800000) >> 23) ^ 0xA5)  # 掩码与值进行位运算后右移23位，再与0xA5进行异或运算
        db3 = (((mask & 0x003FC000) >> 14) ^ 0x5A)  # 掩码与值进行位运算后右移14位，再与0x5A进行异或运算
        counter = (((w_middle ^ db1) & db2) + db3)

        for i in range(counter):
            w_middle = int(((w_sub_seed & 0x20000000) / 0x20000000)) ^ int(
                ((w_sub_seed & 0x01000000) / 0x01000000)) ^ int((
                    (w_sub_seed & 0x2000) / 0x2000)) ^ int(((w_sub_seed & 0x08) / 0x08))
            w_last_bit = (w_middle & 0x00000001)
            w_sub_seed = (w_sub_seed << 1)
            w_left31_bits = (w_sub_seed & 0xFFFFFFFE)
            w_sub_seed = (w_left31_bits | w_last_bit)

        if mask & 0x00000002:  # if 语句判断，若表达式为真，执行下面语句
            w_left31_bits = ((w_sub_seed & 0x00FF0000) >> 16) | ((w_sub_seed & 0xFF000000) >> 16) | \
                            ((w_sub_seed & 0x000000FF) << 24) | ((w_sub_seed & 0x0000FF00) << 8)
        else:
            w_left31_bits = w_sub_seed  # 第一个for循环中计算的值赋值给w_left31_bits

        key = w_left31_bits ^ mask  # 最后计算出的w_left31_bits与掩码位异或得到最终Key
        sa_key_str = "{0:08x}".format(key)  # 填充为8个字
    elif level == 2:
        seed_bytes = bytes.fromhex('{:08x}'.format(seed))
        mask_bytes = bytes.fromhex('{:08x}'.format(mask))
        sa_handle = cdll.LoadLibrary(os.path.normpath(os.path.join(work_dir, 'data\\key\\sa.dll')))
        input_param = SAInputStructure()
        sa_handle.diag_sa_algorithm_api.restype = SAOutputStructure
        input_param.seed[0] = seed_bytes[0]
        input_param.seed[1] = seed_bytes[1]
        input_param.seed[2] = seed_bytes[2]
        input_param.seed[3] = seed_bytes[3]
        input_param.seed_length = 4
        input_param.level = 9
        input_param.param[0] = mask_bytes[3]
        input_param.param[1] = mask_bytes[2]
        input_param.param[2] = mask_bytes[1]
        input_param.param[3] = mask_bytes[0]
        input_param.key_length = 4
        output = sa_handle.diag_sa_algorithm_api(input_param)
        sa_key = output.key
        for i in range(4):
            key = sa_key[i]
            byte_str = "".join(['%02x' % key])
            sa_key_str = sa_key_str + byte_str
    else:
        logger.error(f'不支持安全认证等级: {level}, 当前支持: 1、2')
    return sa_key_str


class Sessions:
    DEFAULT = 0x01
    PROGRAMMING = 0x02
    EXTENDED = 0x03


class ResetTypes:
    HARD = 0x01
    KEY_OFF_ON = 0x02
    SOFT = 0x03
    ENABLE_RAPID_POWER_SHUTDOWN = 0x04
    DISABLE_RAPID_POWER_SHUTDOWN = 0x05


class RoutineSubFunction:
    START = 0x01
    STOP = 0x02
    REQUEST_RESULTS = 0x03


class ModeOfOperation:
    ADD_FILE = 0x01
    DELETE_FILE = 0x02
    REPLACE_FILE = 0x03
    READ_FILE = 0x04
    READ_DIR = 0x05
    RESUME_FILE = 0x06


class RequestFileTransferParams(Structure):
    _fields_ = [
        ("modeOfOperation", c_uint16),
        ("filePathAndNameLength", c_uint8 * 2),
        ("filePathAndName", c_char * 1024),
        ("dataFormatIdentifier", c_uint8),
        ("fileSizeParameterLength", c_uint8),
        ("fileSizeUnCompressed", c_int64),
        ("fileSizeCompressed", c_int64)
    ]


class DoIPClient(threading.Thread):
    def __init__(
            self,
            server_ip="172.31.10.31",
            server_port=13400,
            client_logical_addr='0e02',
            server_logical_addr='0c01',
            uds_timeout=5,
            security_level=1,
            security_mask='30002212'
    ):
        super().__init__()
        self.server_ip = server_ip
        self.server_port = server_port
        self.source_id = client_logical_addr
        self.target_id = server_logical_addr
        self.security_level = security_level
        self.security_mask = security_mask
        self.get_seed_func = 0x01 if self.security_level == 1 else 0x09
        self.send_key_func = 0x02 if self.security_level == 1 else 0x0a
        # 客户端socket
        self.socket_handler = None
        self.uds_timeout = uds_timeout
        # 响应消息队列，响应消息线程终止信号
        self.response_queue = Queue()
        self.stop_event = threading.Event()
        self.active_ret = False  # routing active result
        # 心跳保持线程
        self.keep_alive_thread: threading.Thread = None
        self.keep_alive_interval = 2
        self.keep_alive_event = threading.Event()
        # 信号注册
        self.registration_signals()
        # 重连机制
        self.connected = False
        self.reconnect_lock = threading.Lock()

    def registration_signals(self):
        Variable('doip_resp').Value = ''
        Variable('doip_req').Value = ''
        Variable('doip_proc_read_did').Value = ''
        Variable('doip_proc_write_did').Value = ''
        Variable('doip_proc_ecu_reset').Value = ''
        Variable('doip_proc_read_dtc').Value = ''
        Variable('doip_proc_security_access').Value = ''

    def connect(self):
        logger.info(f"DoIP客户端连接至 {self.server_ip}:{self.server_port}")
        self.socket_handler = socket.socket()
        if self.uds_timeout:
            self.socket_handler.settimeout(self.uds_timeout)
        try:
            self.socket_handler.connect((self.server_ip, self.server_port))
            logger.info("DoIP客户端已成功连接")
            self.start()
            self.connected = True
            logger.info("DoIP客户端接收线程已开启")
        except socket.error as e:
            logger.error(f"DoIP客户都连接异常: {e}")
            self.close()
            return

        if not self.routing_activate():
            logger.error("路由激活失败，DoIP客户端退出")
            self.close()
        else:
            # 心跳保持线程
            if not self.keep_alive_thread:
                self.keep_alive_thread = threading.Thread(target=self.keep_alive, daemon=True)
                self.keep_alive_event.clear()
                self.keep_alive_thread.start()

    def reconnect(self, source='接收端'):
        with self.reconnect_lock:
            logger.info(f'DoIP {source} 正在尝试重连')
            if self.connected:
                logger.info(f'DoIP其他端已重连成功，{source}无需重连')
                return
            while True:
                try:
                    if self.socket_handler:
                        self.socket_handler.close()
                        self.socket_handler = None
                    self.socket_handler = socket.socket()
                    self.socket_handler.settimeout(self.uds_timeout)
                    self.socket_handler.connect((self.server_ip, self.server_port))
                    break
                except:
                    pass
            self.connected = True
            logger.success(f'DoIPClient {source}重连成功, 重新路由激活')
            if not self.routing_activate():
                logger.error("路由激活失败，DoIP客户端退出")
                self.close()

    def close(self):
        self.stop_event.set()
        time.sleep(1)
        if self.socket_handler:
            self.socket_handler.close()

    def response_callback(self, response_message):
        self.response_queue.put(response_message.hex())

    def recv_frame(self, timeout=1):
        try:
            if not self.socket_handler or self.socket_handler.fileno() == -1:
                # 这里处理套接字未打开或已关闭的情况
                return
            # Use select to wait for the socket to be ready for reading
            ready_to_read, _, _ = select.select([self.socket_handler], [], [], timeout)
            if ready_to_read:
                header = self.socket_handler.recv(8)
                if not header or header[:2] != b'\x02\xFD':
                    logger.error(f"响应消息头数据异常: {header}")
                    self.stop_event.set()
                    return None
                payload_len = int.from_bytes(header[4:], byteorder='big')

                # Use select again to wait for payload
                ready_to_read, _, _ = select.select([self.socket_handler], [], [], timeout)
                if ready_to_read:
                    payload = self.socket_handler.recv(payload_len)
                    return header + payload if len(payload) == payload_len else None
        except socket.error as e:
            logger.error(f"接收响应时连接异常: {e}")
            self.connected = False
            self.reconnect(source='接收端')
            # self.stop_event.set()
            return None

    def process_frame(self, frame: bytes):
        frame_hex = frame.hex()
        # 心跳检测不打印
        if frame_hex[-4:] != '3e80':
            logger.info(f"DoIP响应: ".rjust(11) + f"{frame_hex[:16]} {frame_hex[16:24]} {frame_hex[24:]}")

        frame_type = int.from_bytes(frame[2:4], byteorder='big')
        if frame_type == 0x0006:  # Routing activation response
            self.active_ret = frame[12] == 0x10
        elif frame_type == 0x8001:  # Diagnostic message response
            # 帧头去掉，只保留payload
            self.response_callback(frame[8:])

    def run(self):
        while not self.stop_event.is_set():
            frame = self.recv_frame()
            if frame:
                self.process_frame(frame)

    def send_diagnostic(self, msg: str, console=True):
        """
        DoIP诊断消息发送
        Args:
            msg: target_logic_addr + payload
            console: 是否打印日志（pyqt日志显示精简），3e80会持续发送可设置成 False
        Returns:
        """
        head = "02fd8001"
        msg = msg.lower()
        len_byte_str = int((len(msg) / 2) + 2).to_bytes(4, byteorder='big').hex()
        frame = f"{head}{len_byte_str}{self.source_id}{msg}"
        try:
            if console:
                logger.info(f" DoIP请求: {frame[:16]} {frame[16:24]} {frame[24:64]}")
            self.socket_handler.send(bytes.fromhex(frame))
        except socket.error as e:
            logger.error(f"诊断消息请求失败: {e}")
            self.connected = False
            # 重连
            self.reconnect(source='发送端')

    def keep_alive(self):
        while not self.keep_alive_event.is_set():
            try:
                self.send_diagnostic('e4ff3e80', console=False)  # Keep-alive message
                time.sleep(self.keep_alive_interval)
            except Exception as e:
                logger.warning(f"维持心跳异常: {e}")
                self.keep_alive_event.set()

    def routing_activate(self):
        activation_msg = f"02fd00050000000b {self.source_id}0000 00000000000000"
        try:
            logger.success("开始路由激活")
            self.socket_handler.send(bytes.fromhex(activation_msg))
            logger.info(f"DoIP请求: {activation_msg}")
            for i in range(50):
                if not self.active_ret:
                    time.sleep(0.1)
                else:
                    logger.success("路由激活成功")
                    return True
            logger.error("路由激活失败")
            return False
        except socket.error as e:
            logger.error(f"路径激活异常: {e}")
            return False

    def _request_response(self, request_msg):
        self.send_diagnostic(request_msg)
        try:
            response_msg = self.response_queue.get(timeout=self.uds_timeout)
            Variable('doip_resp').Value = response_msg
            return response_msg
        except Exception as e:  # 过了超时时间可能会抛出 queue.Empty
            logger.error(f"诊断消息接收超时: {e}，超时时间: {self.uds_timeout} 秒")
            return ""

    def uds_request(self, msg: str, max_wait=60):
        """
        uds请求到响应的完整处理流程
        Args:
            msg: msg: target_logic_addr + payload
            max_wait: nrc78的最大超时时间

        Returns:
            Tuple(bool, str)
        """
        resp = self._request_response(msg)
        if not resp:
            return False, ""
        req_func = msg[4:6]
        resp_code = resp[8:10]
        resp_func = resp[10:12]

        if resp_code == '7f' and resp_func == req_func:
            nrc = resp[12:14]
            if nrc == '78':  # 服务端正在处理请求，客户端需要等待
                st_time = time.time()
                while time.time() - st_time <= max_wait:  # 持续接收nrc 78
                    try:
                        resp = self.response_queue.get(timeout=self.uds_timeout)
                        if resp[8:10] != '7f' and resp[12:14] != '78':
                            break
                    except queue.Empty:  # 过了超时时间可能会抛出 queue.Empty
                        return False, resp
            else:  # 否定响应
                return False, resp

        return True, resp

    # Add appropriate methods for secure access, file transfer, etc.
    def session_control(self, session: int):
        req_msg = self.target_id + "10" + '{:02x}'.format(session)
        return self.uds_request(req_msg)

    def secure_access_get_seed(self, level: int):
        request_message = self.target_id + "27" + '{:02x}'.format(level)
        return self.uds_request(request_message)

    def secure_access_send_key(self, level: int, key: str):
        request_message = self.target_id + "27" + '{:02x}'.format(level) + key
        return self.uds_request(request_message)

    def edge_node_route_active_process(self):
        """
        # 0xDF11
           - 0x00 成功
           - 0x01 未收到证书
           - 0x02 证书合法性校验失败
        """
        request_result = self.routine_control(RoutineSubFunction.START, 0xdf11, "")
        if not request_result[0]:
            return False
        result_bytes = bytes.fromhex(request_result[1])
        if result_bytes[len(result_bytes) - 1] != 0x00:
            return False
        # route active
        request_result = self.routine_control(RoutineSubFunction.START, 0xdf12, "")
        if not request_result[0] or result_bytes[len(result_bytes) - 1] != 0x00:
            return False
        return True

    # this version of code set const file size to 4 '{:04X}'.format(param.fileSizeUnCompressed)
    def request_file_transfer(self, param: RequestFileTransferParams):
        """ 证书文件请求传输 """
        request_message = self.target_id + "38" + '{:02x}'.format(param.modeOfOperation) \
                          + '{:02X}'.format(param.filePathAndNameLength[0]) \
                          + '{:02X}'.format(param.filePathAndNameLength[1]) \
                          + str(param.filePathAndName, encoding="utf-8") \
                          + '{:02X}'.format(param.dataFormatIdentifier) \
                          + '{:02X}'.format(param.fileSizeParameterLength) \
                          + '{:04X}'.format(param.fileSizeUnCompressed) \
                          + '{:04X}'.format(param.fileSizeCompressed)
        return self.uds_request(request_message)

    def transfer_data(self, block_sequence_counter: int, trans_data: bytes):
        """ 数据传输 """
        request_message = self.target_id + "36" + '{:02x}'.format(block_sequence_counter) + trans_data.hex()
        return self.uds_request(request_message)

    def request_transfer_exit(self):
        """ 数据传输结束 """
        request_message = self.target_id + "37"
        return self.uds_request(request_message)

    def transfer_file_process(self, filepath, filename="TESTER_CRT", moo=ModeOfOperation.ADD_FILE, dfi=0x00):
        """
        38 01 000A 5445535445525F435254 00 04 00000d5C 00000d5C
        """
        logger.success('开始文件传输')
        with open(filepath, 'rb') as file_handler:
            file_contain = file_handler.read()
            request_param = RequestFileTransferParams()
            request_param.modeOfOperation = moo
            request_param.filePathAndNameLength[0] = 0x00
            request_param.filePathAndNameLength[1] = len(filename.encode('ascii'))
            request_param.filePathAndName = binascii.hexlify(filename.encode('utf-8'))
            request_param.dataFormatIdentifier = dfi
            request_param.fileSizeParameterLength = math.ceil(math.log2(len(file_contain) + 1) / 8)
            request_param.fileSizeUnCompressed = len(file_contain)
            request_param.fileSizeCompressed = len(file_contain)
            request_result = self.request_file_transfer(request_param)
            if not request_result[0]:
                return False
            else:
                request_result = self.transfer_data(0x01, file_contain)
                if not request_result[0]:
                    return False
                else:
                    request_result = self.request_transfer_exit()
                    if not request_result[0]:
                        return False
                logger.success("文件传输成功")
                return True

    def secure_access_process(self, security_mask: str, level: int = None):
        """
        Args:
            security_mask: 安全掩码 十六进制字符串
            level: 安全认证等级 0x01 0x02
        Returns:
        """
        logger.success('开始安全认证')
        security_level = self.security_level
        get_seed_func = self.get_seed_func
        send_key_func = self.send_key_func
        if level:
            security_level = level
            get_seed_func = 0x01 if level == 0x01 else 0x09
            send_key_func = 0x02 if level == 0x01 else 0x0a
        if security_level not in (0x01, 0x02):
            logger.error(f'不支持次安全认证等级: 当前 {security_level}，只支持: 0x01、0x02')
            return False
        request_result = self.secure_access_get_seed(get_seed_func)
        security_mask_bytes = bytes.fromhex(security_mask.replace('0x', '').replace('0X', ''))
        seed_resp_bytes = bytes.fromhex(request_result[1])
        seed_bytes = seed_resp_bytes[6:len(seed_resp_bytes)]
        seed_hex_int = int.from_bytes(seed_bytes, byteorder='big', signed=False)
        mask_hex_int = int.from_bytes(security_mask_bytes, byteorder='big', signed=False)
        sa_key_str = seed_cal_key(seed_hex_int, mask_hex_int, level=security_level)
        # logger.info(f"SA Key: {sa_key_str}")
        is_positive, resp_data = self.secure_access_send_key(send_key_func, sa_key_str)
        if is_positive:
            logger.success('安全认证成功')
        else:
            logger.warning('安全认证失败')
        return is_positive, resp_data

    def ecu_reset(self, reset_type: int):
        request_message = self.target_id + "11" + '{:02X}'.format(int(reset_type))
        return self.uds_request(request_message)

    def factory_reset(self, reset=True):
        self.session_control(session=Sessions.EXTENDED)
        self.secure_access_process(security_mask=self.security_mask, level=self.security_level)
        is_positive, resp_data = self.routine_control(0x01, 0x821e, "")
        if reset:
            self.ecu_reset(ResetTypes.HARD)
        return is_positive, resp_data

    def routine_control(self, routine_action: int, routine_id: int, param: str = ""):
        request_message = self.target_id + "31" + '{:02x}'.format(int(routine_action)) + '{:04x}'.format(
            int(routine_id)) + param
        return self.uds_request(request_message)

    def read_data_by_id(self, did: int):
        req_msg = self.target_id + "22" + '{:04x}'.format(int(did))
        return self.uds_request(req_msg)

    def write_data_by_id(self, did: int, data: str, reset=True):
        self.session_control(session=Sessions.EXTENDED)
        self.secure_access_process(security_mask=self.security_mask, level=self.security_level)
        req_msg = self.target_id + "2e" + '{:04x}'.format(int(did)) + data
        self.uds_request(req_msg)
        if reset:
            self.ecu_reset(ResetTypes.HARD)

    def read_dtc(self, sid: int):
        req_msg = self.target_id + "19" + '{:04x}'.format(int(sid))
        return self.uds_request(req_msg)

    def send_msg(self, var: Variable):
        if var.name == 'doip_req':
            self.uds_request(var.Value)
        if var.name == 'doip_proc_write_did':
            did = int(var.Value[:4], 16)
            data = var.Value[4:]
            self.write_data_by_id(did, data)
        elif var.name == 'doip_proc_read_did':
            self.read_data_by_id(var.Value)
        elif var.name == 'doip_proc_read_dtc':
            self.read_dtc(var.Value)
        elif var.name == 'doip_proc_ecu_reset':
            self.ecu_reset(var.Value)
        elif var.name == 'doip_proc_security_access':
            self.secure_access_process(self.security_mask, level=var.Value)


if __name__ == '__main__':
    client = DoIPClient(
        server_ip="172.31.10.31",
        server_port=13400,
        client_logical_addr='0e02',
        server_logical_addr='0c01'
    )
    client.connect()
    # success, response = client.uds_request("0c01190201")
    # logger.info(f"Request success: {success}, response: {response}")
    client.write_data_by_id(0xf1a1, '0150110634fbff6bfc1c3fff01e3e20fff')
    time.sleep(10)
    client.close()
