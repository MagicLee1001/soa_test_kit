# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2024/3/7 10:10
# @File    : liddssil.py
# @Modify  : Li Kun 2024/4/18


import sys
import os
import threading
import time
import traceback
from runner.log import logger
from protocol.lidds130 import vbs
from runner.variable import Variable

path_dir = os.path.abspath(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + "..")
if path_dir not in sys.path:
    sys.path.append(path_dir)


_lock = threading.Lock()


class ReaderListener(vbs.VBS_DataReaderListener):
    def __init__(self, dyn_data, topic_name, topic_datatype, dds_xml=None, is_struct=False):
        super().__init__()
        self.data = dyn_data
        self.topic_name = topic_name
        self.topic_datatype = topic_datatype
        self.is_struct = is_struct
        self.dds_xml = dds_xml
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
            reader.take(self.data)
            for struct_datatype in self.struct_info.keys():
                struct_id = int(self.struct_info[struct_datatype]['message_id'])
                struct_type = self.struct_info[struct_datatype]['message_type']
                if struct_type == 'nonBasic':
                    inner_struct = self.data.loan_value(struct_id)
                    non_basic_type_name = self.struct_info[struct_datatype]['nonBasicTypeName']
                    message_info = self.dds_xml['types']['dataTypes'][non_basic_type_name]['members']
                    for msg_name in message_info.keys():
                        message_id = int(message_info[msg_name]['message_id'])
                        message_type = message_info[msg_name]['message_type']
                        message_value = self.get_message_value(inner_struct, message_type, message_id)
                        if Variable(msg_name).Value != message_value:
                            logger.info(f'接收DDS消息：{self.topic_name} | {msg_name} = {message_value}')
                        Variable(msg_name).Value = message_value
                    self.data.return_loaned_value(inner_struct)
                else:
                    message_value = self.get_message_value(self.data, struct_type, struct_id)
                    if Variable(struct_datatype).Value != message_value:
                        logger.info(f'接收DDS消息：{self.topic_name} | {struct_datatype} = {message_value}')
                    Variable(struct_datatype).Value = message_value
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
        self.listener = ReaderListener(self.recv_data, self.topic_name, self.topic_datatype, dds_xml=self.dds_xml_obj.dds_xml)
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

    def set_value(self, msg_name, msg_value, struct_name=None):
        if struct_name:
            struct_datatype = f'{self.topic_name}_{struct_name}'
            struct_info = self.dds_xml['types']['dataTypes'][self.topic_datatype]['members']
            message_info = self.dds_xml['types']['dataTypes'][struct_datatype]['members']
            inner_struct = None
            for key in struct_info.keys():
                if struct_datatype == struct_info[key]['nonBasicTypeName']:
                    struct_id = int(struct_info[key]['message_id'])
                    inner_struct = self.dyn_data_obj.loan_value(struct_id)
                    break
            message_id = int(message_info[msg_name]['message_id'])
            message_type = message_info[msg_name]['message_type']
        else:
            message_info = self.dds_xml['types']['dataTypes'][self.topic_datatype]
            messages = message_info['members']

            message_id = int(messages[msg_name]['message_id'])
            message_type = messages[msg_name]['message_type']
            inner_struct = self.dyn_data_obj

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

        if struct_name:
            self.dyn_data_obj.return_loaned_value(inner_struct)

    def write(self):
        self.writer.write(self.dyn_data_obj)

    def delete(self):
        with _lock:
            # self.proxy.DestroyDynamicData(self.dyn_data)
            if self.writer is not None:
                self.proxy.DeleteDataWriter_v2(self.participant, self.writer)
                logger.info(f"release topic DataWriter: {self.topic_name}")

    def stop(self):
        self._stop_event.set()

    def run(self):
        self._stop_event.wait()  # 等待直到 _stop_event被设定
        self.delete()


if __name__ == '__main__':
    from protocol.lidds130.liddsxmlparser import Parser

    proxy = vbs.VBSPythonDynamicProxy().getInstance()
    dds_xml_filepath = r"D:\Project\soa-sil-xbp\data\matrix\vbs_XDP2.3.1_8092.xml"
    dds_xml_obj = Parser(dds_xml_filepath)
    proxy.LoadXML(dds_xml_filepath)
    participant_name = 'mySubscriber'
    participant = proxy.CreateDomainParticipantWithProfile_v2(dds_xml_filepath, participant_name)
    logger.success(f'Create DPF {participant_name}')

    topic_name = 'ExteriorLightControl'
    topic_profile = dds_xml_obj.get_topic_profile_name(topic_name)
    topic_datatype = dds_xml_obj.get_topic_datatype(topic_name)
    reader_profile = dds_xml_obj.get_reader_profile_name(topic_name)
    writer_profile = dds_xml_obj.get_writer_profile_name(topic_name)

    tmp = proxy.CreateDynamicData(topic_datatype)
    dyn_data = vbs.VBSPythonDynamicData(tmp)
    dyn_type = dyn_data.GetVBSType()
    topic = proxy.CreateTopicWithProfile_v2(participant, f'Topic_{topic_name}', topic_datatype, dyn_type, topic_profile)

    # 读消息
    reader = evbsReader(
        proxy,
        participant,
        f'Topic_{topic_name}',
        topic_datatype,
        reader_profile,
        topic,
        dyn_data,
        dds_xml_obj
    )
    reader.start()

    # 发消息
    writer = evbsWriter(
        proxy,
        participant,
        f'Topic_{topic_name}',
        topic_datatype,
        writer_profile,
        topic,
        dyn_data,
        dds_xml_obj
    )
    writer.start()

    writer.set_value('srv_rear_fog_req_', 5)
    writer.write()

    # 释放资源
    time.sleep(2)
    # proxy.DestroyDynamicData(dyn_data)

    reader.stop()
    writer.stop()

    writer.join()
    reader.join()

    # 删topic前多等一会 等reader先删完
    time.sleep(1)
    proxy.DeleteTopic_v2(participant, topic)
    proxy.clear()
    logger.info(f"release Topic: {topic_name}")

