# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Email   : likun19941001@163.com
# @Time    : 2024/3/7 10:10
# @File    : liddssil.py
# @Modify  : Li Kun 2024/4/18

import sys
import os
import random
import threading
import time
import traceback
from runner.log import logger
from protocol.lidds130 import vbs
from runner.variable import Variable

_lock = threading.Lock()


class ReaderListener(vbs.VBS_DataReaderListener):
    def __init__(self, dyn_data, topic_name, topic_datatype, dds_xml_obj=None, is_struct=False):
        super().__init__()
        self.dyn_data = dyn_data
        self.topic_name = topic_name
        self.topic_datatype = topic_datatype
        self.is_struct = is_struct
        self.dds_xml_obj = dds_xml_obj
        self.dds_xml = self.dds_xml_obj.dds_xml
        # struct_info: parsed struct info in xml
        self.struct_info = self.dds_xml['types']['dataTypes'][topic_datatype]['members']
        self.message_info = {}

    def on_subscription_matched(self, datareader, info):
        if 0 < info.current_count_change():
            logger.info(f"Subscriber matched publisher: {self.topic_name}")
        else:
            logger.info(f"Subscriber unmatched publisher: {self.topic_name}")

    def get_message_value(self, inner_struct, message_type, message_id):
        if message_type == 'int32':
            message_value = inner_struct.get_int32_value(message_id)
        elif message_type == 'uint32':
            message_value = inner_struct.get_uint32_value(message_id)
        elif message_type == 'uint16':
            message_value = inner_struct.get_uint16_value(message_id)
        elif message_type == 'int16':
            message_value = inner_struct.get_int16_value(message_id)
        elif message_type == 'uint64':
            message_value = inner_struct.get_uint64_value(message_id)
        elif message_type == 'int64':
            message_value = inner_struct.get_int64_value(message_id)
        elif message_type == 'uint8':
            message_value = inner_struct.get_uint8_value(message_id)
        elif message_type == 'int8':
            message_value = inner_struct.get_int8_value(message_id)
        elif message_type == 'bool':
            message_value = inner_struct.get_bool_value(message_id)
        elif message_type == 'float64':
            message_value = inner_struct.get_float64_value(message_id)
        elif message_type == 'float32':
            message_value = inner_struct.get_float32_value(message_id)
        elif message_type == 'string':
            message_value = inner_struct.get_string_value(message_id)
        elif message_type == 'float128':
            message_value = inner_struct.get_float128_value(message_id)
        elif message_type == 'char8':
            message_value = inner_struct.get_char8_value(message_id)
        elif message_type == 'byte':
            message_value = inner_struct.get_byte_value(message_id)
        elif message_type == 'wstring':
            message_value = inner_struct.get_wstring_value(message_id)
        elif message_type == 'enum':
            message_value = inner_struct.get_enum_value(message_id)
        return message_value

    def on_data_available(self, reader):
        try:
            reader.take(self.dyn_data)
            for struct_datatype in self.struct_info.keys():
                struct_id = int(self.struct_info[struct_datatype]['message_id'])
                struct_type = self.struct_info[struct_datatype]['message_type']

                if struct_type == 'nonBasic':
                    non_basic_type_name = self.struct_info[struct_datatype]['nonBasicTypeName']
                    no_basic_type_ref = self.struct_info[struct_datatype]['ref']
                    inner_struct = self.dyn_data.loan_value(struct_id)
                    try:
                        if no_basic_type_ref == 'struct':
                            message_info = self.dds_xml['types']['dataTypes'][non_basic_type_name]['members']
                            for msg_name in message_info.keys():
                                message_id = int(message_info[msg_name]['message_id'])
                                message_type = message_info[msg_name]['message_type']
                                message_value = self.get_message_value(inner_struct, message_type, message_id)
                                combine_msg_name = f'{struct_datatype}.{msg_name}'
                                if combine_msg_name in self.dds_xml_obj.dupl_signal_names:
                                    signal_name = f'{self.topic_name}::{combine_msg_name}'
                                else:
                                    signal_name = combine_msg_name
                                if Variable(signal_name).Value != message_value:
                                    logger.info(f'接收DDS消息：{self.topic_name} | {combine_msg_name} = {message_value}')
                                Variable(signal_name).Value = message_value

                        elif no_basic_type_ref == 'typedef':
                            typedef_message_info = self.dds_xml['types']['typedefs'][non_basic_type_name]
                            if any(key in typedef_message_info for key in ('arrayDimensions', 'sequenceMaxLength')):
                                msg_array_value = []
                                if 'arrayDimensions' in typedef_message_info:
                                    array_length = int(typedef_message_info['arrayDimensions'])
                                elif 'sequenceMaxLength' in typedef_message_info:
                                    array_length = inner_struct.get_item_count()  # TODO 这一块可能有bug
                                else:
                                    continue
                                message_type = typedef_message_info['type']
                                for i in range(array_length):
                                    message_value = self.get_message_value(inner_struct, message_type, i)
                                    msg_array_value.append(message_value)
                                if struct_datatype in self.dds_xml_obj.dupl_signal_names:
                                    signal_name = f'{self.topic_name}::{struct_datatype}'
                                else:
                                    signal_name = struct_datatype
                                if Variable(signal_name).Value != msg_array_value:
                                    logger.info(f'接收DDS消息：{self.topic_name} | {struct_datatype} = {msg_array_value}')
                                Variable(signal_name).Value = msg_array_value

                    finally:
                        self.dyn_data.return_loaned_value(inner_struct)
                else:
                    message_value = self.get_message_value(self.dyn_data, struct_type, struct_id)
                    if struct_datatype in self.dds_xml_obj.dupl_signal_names:
                        signal_name = f'{self.topic_name}::{struct_datatype}'
                    else:
                        signal_name = struct_datatype
                    if Variable(signal_name).Value != message_value:
                        logger.info(f'接收DDS消息：{self.topic_name} | {struct_datatype} = {message_value}')
                    Variable(signal_name).Value = message_value

        except:
            logger.error(traceback.format_exc())


class WriterListener(vbs.VBS_DataWriterListener):
    def __init__(self, writer):
        self._writer = writer
        super().__init__()

    def on_publication_matched(self, datawriter, info):
        if 0 < info.current_count_change():
            logger.info(f"Publisher matched subscriber: {self._writer.topic_name}")
            self._writer._cvDiscovery.acquire()
            self._writer._matched_reader += 1
            self._writer._cvDiscovery.notify()
            self._writer._cvDiscovery.release()
        else:
            logger.info(f"Publisher unmatched subscriber: {self._writer.topic_name}")
            self._writer._cvDiscovery.acquire()
            self._writer._matched_reader -= 1
            self._writer._cvDiscovery.notify()
            self._writer._cvDiscovery.release()


class evbsReader(threading.Thread):
    def __init__(self, proxy, participant, topic_name, topic_datatype, reader_profile, topic, dyn_data, dds_xml_obj):
        super().__init__()
        self._stop_event = threading.Event()
        self.proxy = proxy
        self.dyn_data = dyn_data
        # self.dyn_type = self.dyn_data.GetVBSType()
        self.recv_data = self.dyn_data.GetVBSDynamicData()
        self.participant = participant
        self.topic = topic
        self.dds_xml_obj = dds_xml_obj
        self.topic_name = topic_name
        self.topic_datatype = topic_datatype
        self.reader_profile = reader_profile
        self.listener = ReaderListener(self.recv_data, self.topic_name, self.topic_datatype, dds_xml_obj=self.dds_xml_obj)
        self.reader = self.proxy.CreateDataReaderWithProfile_v2(self.participant, self.topic, self.reader_profile, self.listener)
        logger.info(f"Create reader topic {self.topic_name}")

    def delete(self):
        with _lock:
            if self.reader is not None:
                self.proxy.DeleteDataReader_v2(self.participant, self.reader)
                logger.info(f"release topic DataReader {self.topic_name}")

    def stop(self):
        self._stop_event.set()

    def run(self):
        self._stop_event.wait()  # 等待直到 _stop_event被设定
        self.delete()


class evbsWriter(threading.Thread):
    def __init__(self, proxy, participant, topic_name, topic_datatype, writer_profile, topic, dyn_data, dds_xml_obj):
        super(evbsWriter, self).__init__()
        self._matched_reader = 0
        self._cvDiscovery = threading.Condition()
        self._stop_event = threading.Event()
        self.proxy = proxy
        self.dyn_data = dyn_data
        # self.dyn_type = self.dyn_data.GetVBSType()
        self.dyn_data_obj = self.dyn_data.GetVBSDynamicData()
        self.participant = participant
        self.topic = topic
        self.dds_xml_obj = dds_xml_obj
        self.dds_xml = dds_xml_obj.dds_xml
        self.topic_name = topic_name
        self.topic_datatype = topic_datatype
        self.writer_profile = writer_profile
        self.listener = WriterListener(self)
        self.writer = self.proxy.CreateDataWriterWithProfile_v2(self.participant, self.topic, self.writer_profile, self.listener)
        logger.info(f"Create writer topic {self.topic_name}")

    def wait_discovery(self):
        self._cvDiscovery.acquire()
        logger.info("Writer is waiting discovery...")
        self._cvDiscovery.wait_for(lambda: self._matched_reader != 0)
        self._cvDiscovery.release()
        logger.info("Writer discovery finished...")

    def set_message_value(self, inner_struct, message_id, msg_value, message_type):
        if 'int' in message_type:
            msg_value = int(msg_value)
        if message_type == 'int32':
            inner_struct.set_int32_value(msg_value, message_id)
        elif message_type == 'uint32':
            inner_struct.set_uint32_value(msg_value, message_id)
        elif message_type == 'uint16':
            inner_struct.set_uint16_value(msg_value, message_id)
        elif message_type == 'int16':
            inner_struct.set_int16_value(msg_value, message_id)
        elif message_type == 'uint64':
            inner_struct.set_uint64_value(msg_value, message_id)
        elif message_type == 'int64':
            inner_struct.set_int64_value(msg_value, message_id)
        elif message_type == 'uint8':
            inner_struct.set_uint8_value(msg_value, message_id)
        elif message_type == 'int8':
            inner_struct.set_int8_value(msg_value, message_id)
        elif message_type == 'bool':
            inner_struct.set_bool_value(msg_value, message_id)
        elif message_type == 'float64':
            inner_struct.set_float64_value(msg_value, message_id)
        elif message_type == 'float32':
            inner_struct.set_float32_value(msg_value, message_id)
        elif message_type == 'string':
            inner_struct.set_string_value(msg_value, message_id)
        elif message_type == 'float128':
            inner_struct.set_float128_value(msg_value, message_id)
        elif message_type == 'char8':
            inner_struct.set_char8_value(msg_value, message_id)
        elif message_type == 'byte':
            inner_struct.set_byte_value(msg_value, message_id)
        elif message_type == 'wstring':
            inner_struct.set_wstring_value(msg_value, message_id)
        elif message_type == 'enum':
            inner_struct.set_enum_value(msg_value, message_id)

    def set_value(self, msg_name, msg_value):
        inner_msg_name = ''
        struct_info = self.dds_xml['types']['dataTypes'][self.topic_datatype]['members']
        if '.' in msg_name:
            struct_name, inner_msg_name = msg_name.split('.')
        else:
            struct_name = msg_name

        struct_id = int(struct_info[struct_name]['message_id'])
        struct_type = struct_info[struct_name]['message_type']

        if inner_msg_name:
            if struct_type == 'nonBasic' and struct_info[struct_name]['ref'] == 'struct':  # 结构体嵌套
                inner_struct = self.dyn_data_obj.loan_value(struct_id)  # 指向新的struct内存地址
                try:
                    non_basic_type_name = struct_info[struct_name]['nonBasicTypeName']
                    inner_struct_info = self.dds_xml['types']['dataTypes'][non_basic_type_name]['members']
                    message_id = int(inner_struct_info[inner_msg_name]['message_id'])
                    message_type = inner_struct_info[inner_msg_name]['message_type']
                    self.set_message_value(inner_struct, message_id, msg_value, message_type)
                finally:
                    self.dyn_data_obj.return_loaned_value(inner_struct)
            else:
                logger.error(f'{self.topic_name} | {struct_name} not a valid Structure nesting format, please check.')

        else:
            if struct_type == 'nonBasic':  # typedef结构
                non_basic_type_name = struct_info[struct_name]['nonBasicTypeName']
                typedef_message_info = self.dds_xml['types']['typedefs'][non_basic_type_name]
                if 'arrayDimensions' in typedef_message_info.keys():
                    array_type = 'arrayDimensions'
                    dimensions = int(typedef_message_info[array_type])
                    if dimensions != len(msg_value):
                        logger.error(f'{self.topic_name} | {struct_name} typedef arrayDimensions is {array_type}, but given {len(msg_value)}')
                        return
                elif 'sequenceMaxLength' in typedef_message_info.keys():
                    array_type = 'sequenceMaxLength'
                    seq_len = int(typedef_message_info[array_type])
                    if len(msg_value) > seq_len:
                        logger.error(f'{self.topic_name} | {struct_name} typedef sequenceMaxLength max {seq_len}, but given {len(msg_value)}')
                        return
                else:
                    return

                inner_struct = self.dyn_data_obj.loan_value(struct_id)  # 指向新的struct内存地址
                try:
                    message_type = typedef_message_info['type']
                    for i in range(len(msg_value)):
                        if array_type == 'sequenceMaxLength':
                            inner_struct.insert_sequence_data(0)  # 申请 member_id内存空间 todo vbs底层有问题 等待释放
                        self.set_message_value(inner_struct, i, msg_value[i], message_type)
                finally:
                    self.dyn_data_obj.return_loaned_value(inner_struct)

            else:  # 基础数据结构
                message_id = struct_id
                message_type = struct_type
                self.set_message_value(self.dyn_data_obj, message_id, msg_value, message_type)

    def write(self):
        self.writer.write(self.dyn_data_obj)

    def delete(self):
        with _lock:
            if self.writer is not None:
                self.proxy.DeleteDataWriter_v2(self.participant, self.writer)
                logger.info(f"release topic DataWriter: {self.topic_name}")

    def stop(self):
        self._stop_event.set()

    def run(self):
        self._stop_event.wait()  # 等待直到 _stop_event被设定
        self.delete()


class evbsWriterDoS(evbsWriter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.stop_event = threading.Event()
        self.interval = kwargs.get('interval', 1)

    def run(self):
        signal_names = [i.split(':')[-1] for i in self.dds_xml_obj.topic2signal[self.topic_name.lstrip('Topic_')]]
        while not self.stop_event.is_set():
            for signal_name in signal_names:
                signal_value = float(random.randint(0, 2**8-1))
                try:
                    self.set_value(signal_name, signal_value)
                    self.write()
                except Exception as e:
                    print(e, f'{self.topic_name} | {signal_name} = {signal_value}')
                else:
                    print(f'pub msg: {self.topic_name} | {signal_name} = {signal_value}')
            time.sleep(self.interval)

    def stop(self):
        self.stop_event.set()


if __name__ == '__main__':
    from protocol.lidds130.liddsxmlparser import Parser

    proxy = vbs.VBSPythonDynamicProxy().getInstance()
    dds_xml_filepath = r"D:\Project\soa-sil-xbp\data\matrix\vbs_XBP2.2.0.xml"
    dds_xml_obj = Parser(dds_xml_filepath)
    proxy.LoadXML(dds_xml_filepath)
    participant_name = 'mySubscriber'
    participant = proxy.CreateDomainParticipantWithProfile_v2(dds_xml_filepath, participant_name)
    logger.success(f'Create DPF {participant_name}')

    topic_name = 'MUploadCanDataRequest'
    prefix_topic_name = f'{topic_name}'  # f'Topic_{topic_name}'
    topic_profile = dds_xml_obj.get_topic_profile_name(topic_name)
    topic_datatype = dds_xml_obj.get_topic_datatype(topic_name)
    reader_profile = dds_xml_obj.get_reader_profile_name(topic_name)
    writer_profile = dds_xml_obj.get_writer_profile_name(topic_name)

    tmp = proxy.CreateDynamicData(topic_datatype)
    dyn_data = vbs.VBSPythonDynamicData(tmp)
    dyn_type = dyn_data.GetVBSType()
    topic = proxy.CreateTopicWithProfile_v2(participant, prefix_topic_name, topic_datatype, dyn_type, topic_profile)

    # 读消息
    reader = evbsReader(
        proxy,
        participant,
        prefix_topic_name,
        topic_datatype,
        reader_profile,
        topic,
        dyn_data,
        dds_xml_obj
    )
    reader.start()

    # 发消息
    # writer = evbsWriter(
    #     proxy,
    #     participant,
    #     prefix_topic_name,
    #     topic_datatype,
    #     writer_profile,
    #     topic,
    #     dyn_data,
    #     dds_xml_obj
    # )
    # writer.start()

    # writer.set_value('MSG_ActuBrkPdlPrsdSts',  1)  # Topic BrakeSystemStatus 不同topic同信号名
    # writer.set_value('m_MUploadCanDataHeader.Timestamp',  2)  # Topic MUploadCanDataRequest 测试结构体嵌套
    # writer.set_value('MSG_CellVolt_32960',  [1]*260)  # Topic RESSVoltageData32960  测试typedef定长数组
    # writer.set_value('m_Data',  [1]*50)  # Topic MUploadCanDataRequest  测试typedef不定长数组
    # writer.write()

    # 释放资源
    # time.sleep(2)
    # # proxy.DestroyDynamicData(dyn_data)
    #
    # reader.stop()
    # writer.stop()
    #
    # writer.join()
    # reader.join()
    #
    # # 删topic前多等一会 等reader先删完
    # time.sleep(1)
    # proxy.DeleteTopic_v2(participant, topic)
    # proxy.clear()
    # logger.info(f"release Topic: {topic_name}")
    #
