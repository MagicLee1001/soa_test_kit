#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/8/29 10:40
# @Author  : Liu Xi
# @Modify  : likun3

"""
类似fastdds的二次开发
内部项目脱敏, 这里只显示SOA信号测试过程中的处理思路
"""

import sys
import os
import time
import threading
import xml.etree.ElementTree as ET
from loguru import logger
from lidds import evbs
from runner.variable import Variable

path_dir = os.path.abspath(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + "..")
if path_dir not in sys.path:
    sys.path.append(path_dir)


class ReaderDataFormat:
    def __init__(self):
        self.timestamp = None
        self.info = None


class ReaderPoolFormat:
    def __init__(self):
        self.topic_name = None
        self.reader = None
        self.data = []
        self.writer_name = None


class Parser:
    def __init__(self, xml_filepath):
        self.dds_xml = {}
        self.types = {}
        self.profiles = {}
        self.dds_xml['profiles'] = self.profiles
        self.dds_xml['types'] = self.types
        self.profiles['topics'] = {}
        self.profiles['data_writers'] = {}
        self.profiles['data_readers'] = {}
        self.types['dataTypes'] = {}
        self.xml = xml_filepath
        self.tree = ET.parse(xml_filepath)
        self.root = self.tree.getroot()
        dds_profile = self.root.find(
            '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}profiles')
        dds_type = self.root.find(
            '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}types')
        self.parse_topic_in_profile(dds_profile)
        self.parse_writer_reader_in_profile(dds_profile, 'writer')
        self.parse_writer_reader_in_profile(dds_profile, 'reader')
        self.parse_struct(dds_type)

    def parse_topic_in_profile(self, object):
        for topic in object.findall(
                '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}topic'):
            topic_profile_name = topic.get('profile_name')
            topic_name = topic.find(
                '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}name').text
            topic_dataType = topic.find(
                '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}dataType').text
            self.profiles['topics'][topic_name] = {}
            self.profiles['topics'][topic_name]['self'] = 'name'
            self.profiles['topics'][topic_name]['topic_profile_name'] = topic_profile_name
            self.profiles['topics'][topic_name]['topic_dataType'] = topic_dataType

    def parse_struct(self, object):
        '''
        object: type
        '''
        for struct in self.root.iter(
                '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}struct'):

            struct_name = struct.get('name')
            topic_name = struct_name.split('_')[-1]
            self.types['dataTypes'][struct_name] = {}
            self.types['dataTypes'][struct_name]['topic_name'] = topic_name
            self.types['dataTypes'][struct_name]['members'] = {}
            for member in struct.iter(
                    '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}member'):
                message_name = member.get('name')
                message_id = member.get('id')
                message_type = member.get('type')
                self.types['dataTypes'][struct_name]['members'][message_name] = {}
                self.types['dataTypes'][struct_name]['members'][message_name]['message_id'] = message_id
                self.types['dataTypes'][struct_name]['members'][message_name]['message_type'] = message_type
                if 'nonBasicTypeName' in member.keys():
                    nonBasicTypeName = member.get('nonBasicTypeName')
                    self.types['dataTypes'][struct_name]['members'][message_name]['nonBasicTypeName'] = nonBasicTypeName

    def parse_writer_reader_in_profile(self, object, writer_or_reader: str):
        '''
        param: writer_or_reader: str, data_writer, or data_reader required
        object: profile in xml
        '''
        if 'writer' in writer_or_reader:
            strings = '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}data_writer'
            key = 'data_writers'
        elif 'reader' in writer_or_reader:
            strings = '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}data_reader'
            key = 'data_readers'

        for item in object.findall(strings):
            profile_name = item.get('profile_name')
            topic = item.find(
                '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}topic')
            topic_name = topic.find(
                '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}name').text
            topic_dataType = topic.find(
                '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}dataType').text
            self.profiles[key][topic_name] = {}
            self.profiles[key][topic_name]['topic'] = {}
            self.profiles[key][topic_name]['topic']['name'] = topic_name
            self.profiles[key][topic_name]['topic']['profile_name'] = profile_name
            self.profiles[key][topic_name]['topic']['topic_dataType'] = topic_dataType

            self.profiles[key][topic_name]['qos'] = {}
            qos = item.find(
                '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}qos')
            reliability = qos.find(
                '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}reliability')
            if reliability:
                reliability_kind = reliability.find(
                    '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}kind').text
            else:
                reliability_kind = None
            durability = qos.find(
                '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}durability')
            if durability:
                durability_kind = durability.find(
                    '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}kind').text
            else:
                durability_kind = None
            liveliness = qos.find(
                '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}liveliness')
            if liveliness:
                liveliness_kind = liveliness.find(
                    '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}kind').text
            else:
                liveliness_kind = None
            ownership = qos.find(
                '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}ownership')
            if ownership:
                ownership_kind = ownership.find(
                    '{http://www.evbs.com/XMLSchemas/fastRTPS_Profiles}kind').text
            else:
                ownership_kind = None
            self.profiles[key][topic_name]['qos']['reliability'] = {}
            self.profiles[key][topic_name]['qos']['reliability']['kind'] = reliability_kind
            self.profiles[key][topic_name]['qos']['durability'] = {}
            self.profiles[key][topic_name]['qos']['durability']['kind'] = durability_kind
            self.profiles[key][topic_name]['qos']['liveliness'] = {}
            self.profiles[key][topic_name]['qos']['liveliness']['kind'] = liveliness_kind
            self.profiles[key][topic_name]['qos']['ownership'] = {}
            self.profiles[key][topic_name]['qos']['ownership']['kind'] = ownership_kind


class ReaderListener(evbs.DataReaderListener):
    def __init__(
            self,
            dds_xml,
            dyn_data,
            topic_name,
            topic_datatype,
            is_struct=False):

        super().__init__()
        self.data = dyn_data
        # self.event = event
        self.topic_name = topic_name
        self.topic_datatype = topic_datatype
        self.is_struct = is_struct
        self.message_infos = {}
        self.dds_xml = dds_xml
        self.struct_infos = self.dds_xml['types']['dataTypes'][topic_datatype]['members']

        # self.messages = list(message_infos.keys())

    '''
    struct_info: parsed struct info in xml
    '''

    def on_subscription_matched(self, datareader, info):
        if (0 < info.current_count_change):
            print(
                "Subscriber matched publisher {}".format(
                    info.last_publication_handle))
        else:
            print(
                "Subscriber unmatched publisher {}".format(
                    info.last_publication_handle))

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
            # logger.info(f'Listener --> sub topic name: {self.topic_name}')
            data_new = {}
            received_data = ReaderDataFormat()
            received_data.timestamp = time.time()
            info = evbs.SampleInfo()
            reader.take_next_sample(self.data, info)

            for struct_datatype in self.struct_infos.keys():
                struct_id = int(self.struct_infos[struct_datatype]['message_id'])
                struct_type = self.struct_infos[struct_datatype]['message_type']
                if struct_type == 'nonBasic':
                    inner_struct = self.data.loan_value(struct_id)
                    non_basic_type_name = self.struct_infos[struct_datatype]['nonBasicTypeName']
                    message_info = self.dds_xml['types']['dataTypes'][non_basic_type_name]['members']
                    for msg_name in message_info.keys():
                        message_id = int(message_info[msg_name]['message_id'])
                        message_type = message_info[msg_name]['message_type']
                        message_value = self.get_message_value(inner_struct, message_type, message_id)
                        if Variable(msg_name).data_array[-1] != message_value:
                            logger.info(f'接收DDS消息：{self.topic_name} | {msg_name} = {message_value}')
                        Variable(msg_name).Value = message_value  # TODO Debug
                    self.data.return_loaned_value(inner_struct)
                else:
                    message_value = self.get_message_value(self.data, struct_type, struct_id)
                    if Variable(struct_datatype).data_array[-1] != message_value:
                        logger.info(f'接收DDS消息：{self.topic_name} | {struct_datatype} = {message_value}')
                    Variable(struct_datatype).Value = message_value  # TODO Debug
        except Exception as e:
            pass
            # TODO 这里需要处理特殊MSG的类型
            # TODO 否则这行可能会报错程序阻塞 nonBasicTypeName = self.struct_infos[struct_datatype]['nonBasicTypeName']


class WriterListener(evbs.DataWriterListener):
    def __init__(self, writer):
        self._writer = writer
        super().__init__()

    def on_publication_matched(self, datawriter, info):
        if (0 < info.current_count_change):
            print(
                "Publisher matched subscriber {}".format(
                    info.last_subscription_handle))
            self._writer._cvDiscovery.acquire()
            self._writer._matched_reader += 1
            self._writer._cvDiscovery.notify()
            self._writer._cvDiscovery.release()
        else:
            print(
                "Publisher unmatched subscriber {}".format(
                    info.last_subscription_handle))
            self._writer._cvDiscovery.acquire()
            self._writer._matched_reader -= 1
            self._writer._cvDiscovery.notify()
            self._writer._cvDiscovery.release()


class evbsReader(threading.Thread):
    def __init__(self, dds_xml):
        super(evbsReader, self).__init__()
        self.is_running = True
        self.topic_name = None
        self.topic_datatype = None
        self.struct_name = None
        self.struct_datatype = None
        self.dds_xml = dds_xml

    def create(
            self,
            proxy,
            topic_profile: str,
            topic_name: str,
            reader_profile: str,
            topic_datatype: str):
        # event = threading.Event
        event = None
        self.topic_name = topic_name
        self.topic_datatype = topic_datatype
        participant_name = 'mySubscriber'
        domainID = 0
        self._matched_reader = 0
        self._cvDiscovery = threading.Condition()
        self.proxy = proxy
        tmp = self.proxy.CreateDynamicData(topic_datatype)
        self.dyn_data = evbs.VBSPythonDynamicData(tmp)
        self.dyn_type = self.dyn_data.GetVBSType()
        self.dyn_data_obj = self.dyn_data.GetDynamicData()
        ret = self.proxy.GetDomainParticipantFactory()
        if ret != 0:
            print('GetDomainParticipantFactory failed')
            return
        print("Get DPF")

        self.participant = self.proxy.CreateDomainParticipantWithProfile_v2(
            domainID, participant_name)
        print("Create DP")
        self.participant.register_type(self.dyn_type)
        print("register type")
        self.topic_listener = evbs.TopicListener()
        self.topic_mask = evbs.StatusMask().all()
        self.topic = self.proxy.CreateTopicWithProfile_v2(
            self.participant,
            topic_name,
            topic_datatype,
            topic_profile,
            self.topic_listener,
            self.topic_mask)
        print("Create topic")
        self.subscriber_qos = evbs.SUBSCRIBER_QOS_DEFAULT
        self.subscriber = self.participant.create_subscriber(
            self.subscriber_qos)
        print("Create data reader")
        self.listener = ReaderListener(
            self.dds_xml,
            self.dyn_data_obj,
            topic_name,
            topic_datatype)
        self.r_mask = evbs.StatusMask().all()
        self.reader = self.proxy.CreateDataReaderWithProfile_v2(
            self.subscriber, self.topic, reader_profile, self.listener, self.r_mask)

    def delete(self):
        print("release C++ resource")
        if self.reader is not None:
            print("release DataWriter")
            self.subscriber.delete_datareader(self.reader)
        if self.subscriber is not None:
            print("release Publisher")
            self.participant.delete_subscriber(self.subscriber)
        if self.topic is not None:
            print("release Topic")
            self.participant.delete_topic(self.topic)

    def release_proxy(self):
        if self.participant is not None:
            print("release DomainParticipant")
            self.proxy.DeleteDomainParticipant_v2(self.participant)
            self.proxy = None
            print("release proxy")

    def run(self):
        while True:
            try:
                pass
                # self.func.wait_for_subscriptions(timeout=3000)
                # print('reader running')
                time.sleep(2)
            except BaseException:
                continue


class evbsReaderSiL(evbsReader):
    """ SiL自动化测试兼容"""

    def create(
            self,
            proxy,
            topic_profile: str,
            topic_name: str,
            reader_profile: str,
            topic_datatype: str):
        # event = threading.Event
        event = None
        self.topic_name = topic_name
        self.topic_datatype = topic_datatype
        participant_name = 'mySubscriber'
        domainID = 0
        self._matched_reader = 0
        self._cvDiscovery = threading.Condition()
        self.proxy = proxy
        tmp = self.proxy.CreateDynamicData(topic_datatype)
        self.dyn_data = evbs.VBSPythonDynamicData(tmp)
        self.dyn_type = self.dyn_data.GetVBSType()
        self.dyn_data_obj = self.dyn_data.GetDynamicData()
        ret = self.proxy.GetDomainParticipantFactory()
        if ret != 0:
            print('GetDomainParticipantFactory failed')
            return
        print("Get DPF")

        self.participant = self.proxy.CreateDomainParticipantWithProfile_v2(
            domainID, participant_name)
        print("Create DP")
        self.participant.register_type(self.dyn_type)
        print("register type")
        self.topic_listener = evbs.TopicListener()
        self.topic_mask = evbs.StatusMask().all()
        self.topic = self.proxy.CreateTopicWithProfile_v2(
            self.participant,
            topic_name,
            topic_datatype,
            topic_profile,
            self.topic_listener,
            self.topic_mask)
        print("Create topic")
        self.subscriber_qos = evbs.SUBSCRIBER_QOS_DEFAULT
        self.subscriber = self.participant.create_subscriber(
            self.subscriber_qos)
        print("Create data reader")
        self.listener = ReaderListener(
            self.dds_xml,
            self.dyn_data_obj,
            topic_name,
            topic_datatype)
        self.r_mask = evbs.StatusMask().all()
        self.reader = self.proxy.CreateDataReaderWithProfile_v2(
            self.subscriber, self.topic, reader_profile, self.listener, self.r_mask)


class evbsWriter(threading.Thread):
    def __init__(self, dds_xml):
        super(evbsWriter, self).__init__()
        self.is_running = True
        self.topic_name = None
        self.topic_datatype = None
        self.struct_name = None
        self.struct_datatype = None
        self.dds_xml = dds_xml

    def create(
            self,
            proxy,
            topic_profile: str,
            topic_name: str,
            writer_profile: str,
            topic_datatype: str):
        self.topic_name = topic_name
        self.topic_datatype = topic_datatype
        domainID = 0
        self._matched_reader = 0
        self._cvDiscovery = threading.Condition()
        self.proxy = proxy
        # domain id :0

        tmp = self.proxy.CreateDynamicData(topic_datatype)  # 创建topic
        self.dyn_data = evbs.VBSPythonDynamicData(tmp)

        self.dyn_type = self.dyn_data.GetVBSType()
        self.dyn_data_obj = self.dyn_data.GetDynamicData()

        ret = self.proxy.GetDomainParticipantFactory()
        if ret != 0:
            sys.exit(1)
            return
        # # print("Get DPF")

        # print("Create DP")
        self.participant = self.proxy.CreateDomainParticipantWithProfile_v2(
            domainID, 'myPublisher')
        self.participant.register_type(self.dyn_type)
        # print("register type")
        self.topic_listener = evbs.TopicListener()
        self.topic_mask = evbs.StatusMask().all()
        self.topic = self.proxy.CreateTopicWithProfile_v2(
            self.participant,
            topic_name,
            topic_datatype,
            topic_profile,
            self.topic_listener,
            self.topic_mask)
        print("Create topic")
        self.pub_qos = evbs.PUBLISHER_QOS_DEFAULT
        self.publisher = self.participant.create_publisher(self.pub_qos)

        print("Create publisher")
        self.listener = WriterListener(self)

        # self.publisher.get_default_datawriter_qos(self.writer_qos)
        self.w_mask = evbs.StatusMask().all()
        self.writer = self.proxy.CreateDataWriterWithProfile_v2(
            self.publisher, self.topic, writer_profile, self.listener, self.w_mask)
        print("Create DataWriter")

    def wait_discovery(self):
        self._cvDiscovery.acquire()
        print("Writer is waiting discovery...")
        self._cvDiscovery.wait_for(lambda: self._matched_reader != 0)
        self._cvDiscovery.release()
        print("Writer discovery finished...")

    def set_value(self, msg_name, msg_value, struct_name=None):
        if struct_name:
            struct_datatype = f'{self.topic_name}_{struct_name}'
            struct_infos = self.dds_xml['types']['dataTypes'][self.topic_datatype]['members']
            message_infos = self.dds_xml['types']['dataTypes'][struct_datatype]['members']
            inner_struct = None
            for key in struct_infos.keys():
                if struct_datatype == struct_infos[key]['nonBasicTypeName']:
                    struct_id = int(struct_infos[key]['message_id'])
                    inner_struct = self.dyn_data_obj.loan_value(struct_id)
                    break
            message_id = int(message_infos[msg_name]['message_id'])
            message_type = message_infos[msg_name]['message_type']
        else:
            struct_dataType = None
            struct_infos = None
            message_infos = self.dds_xml['types']['dataTypes'][self.topic_datatype]
            messages = message_infos['members']

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
        # print('-----------------debug-----------------')

    def write(self):
        # self.wait_discovery()
        self.writer.write(self.dyn_data_obj)

    def delete(self):
        print("release C++ resource")
        if self.writer is not None:
            print("release DataWriter")
            self.publisher.delete_datawriter(self.writer)
        if self.publisher is not None:
            print("release Publisher")
            self.participant.delete_publisher(self.publisher)
        if self.topic is not None:
            print("release Topic")
            self.participant.delete_topic(self.topic)

    def release_proxy(self):
        if self.participant is not None:
            print("release DomainParticipant")
            self.proxy.DeleteDomainParticipant_v2(self.participant)
            self.proxy = None
            print("release proxy")
            exit()

    def run(self):
        while True:
            try:
                pass
                # self.func.wait_for_subscriptions(timeout=3000)
                # print('writer running')
                time.sleep(2)
                pass
            except BaseException:
                continue


if __name__ == '__main__':
    print('')

    proxy = evbs.VBSPythonDynamicProxy().getInstance()
    xml = r"..\data\matrix\XBP.xml"
    proxy.LoadXML(xml)
    topic_profile = '123_prof'
    topic_name = '123'
    writer_profile = 'Soa123Writer'
    topic_dataType = '123_123'
    dds_xml = Parser(xml)
    writer = evbsWriter(dds_xml.dds_xml)
    writer.create(
        proxy,
        topic_profile,
        topic_name,
        writer_profile,
        topic_dataType)

    writer.start()
    while True:
        writer.set_value('MSG_123', 1)
        print('write value MSG_123', 1)
        writer.write()
        time.sleep(6)
        writer.set_value('MSG_456', 5)
        print('write value MSG_456', 5)
        writer.write()
        time.sleep(6)

    writer.delete()
    writer.release_proxy()
