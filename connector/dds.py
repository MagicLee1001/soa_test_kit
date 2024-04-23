# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2023/10/19 17:30
# @File    : dds.py

import time
import re
import threading
import traceback
from xml.dom.minidom import parse
from settings import env
from runner.log import logger
from runner.variable import Variable

# 1.3.0版本
from protocol.lidds130 import vbs
from protocol.lidds130.liddssil import evbsWriter, evbsReader
from protocol.lidds130.liddsxmlparser import Parser

from protocol.rtidds import rticonnextdds_connector as rti
from protocol.rtidds.rtiddssil import RtiDDSReader, RtiDDSWriter
from connector import ConnectorPool


class DDSConnector:
    """
    vbs DDSConnector工厂类
    """
    _instance_lock = threading.Lock()
    _instance = None
    _pool_lock = threading.Lock()

    def __init__(self, idl_filepath=''):
        self.idl_filepath = idl_filepath
        self.reader_topic_names = []
        self.writer_topic_names = []
        self.dds_proxy = vbs.VBSPythonDynamicProxy().getInstance()
        self.dds_proxy.LoadXML(self.idl_filepath)
        participant_name = 'mySubscriber'
        self.participant = self.dds_proxy.CreateDomainParticipantWithProfile_v2(self.idl_filepath, participant_name)
        logger.success(f'Create DPF {participant_name}')
        self.xml_parser = Parser(self.idl_filepath)
        self.signal_map = {}  # {signal_name:topic_name}
        self.signal2topic()
        self.get_topic_names_from_xml()

    def __new__(cls, *args, **kwargs):
        """单例模式"""
        with cls._instance_lock:
            if not cls._instance:
                cls._instance = super().__new__(cls)
            return cls._instance

    def signal2topic(self):
        data_types = self.xml_parser.types['dataTypes']
        for key, val in data_types.items():
            try:
                topic_name = val['topic_name']
                members = val['members']
                for signal_name in members.keys():
                    Variable(signal_name, 0)
                    self.signal_map[signal_name] = topic_name
            except Exception as e:
                logger.error(f'signal2topic fail: {e}, topic_name: {topic_name}')

    def get_topic_names_from_xml(self):
        self.reader_topic_names = sorted(list(self.xml_parser.profiles['data_readers'].keys()))
        self.writer_topic_names = sorted(list(self.xml_parser.profiles['data_writers'].keys()))

    def create_subscriber(self, topic_name):
        topic_name_prefix = 'Topic_' if env.has_topic_prefix else ''
        topic_profile = self.xml_parser.get_topic_profile_name(topic_name)
        topic_datatype = self.xml_parser.get_topic_datatype(topic_name)
        reader_profile = self.xml_parser.get_reader_profile_name(topic_name)
        with self._pool_lock:
            if not ConnectorPool.topic_obj_pool.get(topic_name):
                tmp = self.dds_proxy.CreateDynamicData(topic_datatype)
                dyn_data = vbs.VBSPythonDynamicData(tmp)
                dyn_type = dyn_data.GetVBSType()
                topic = self.dds_proxy.CreateTopicWithProfile_v2(
                    self.participant,
                    f'{topic_name_prefix}{topic_name}',
                    topic_datatype,
                    dyn_type,
                    topic_profile
                )
                ConnectorPool.topic_obj_pool[topic_name] = {
                    'topic': topic,
                    'dyn_data': dyn_data,
                }

            if not ConnectorPool.dds_reader_pool.get(topic_name):
                topic = ConnectorPool.topic_obj_pool[topic_name]['topic']
                dyn_data = ConnectorPool.topic_obj_pool[topic_name]['dyn_data']
                reader = evbsReader(
                    self.dds_proxy,
                    self.participant,
                    f'{topic_name_prefix}{topic_name}',
                    topic_datatype,
                    reader_profile,
                    topic,
                    dyn_data,
                    self.xml_parser
                )
                reader.start()
                ConnectorPool.dds_reader_pool[topic_name] = reader

    def create_publisher(self, topic_name):
        topic_name_prefix = 'Topic_' if env.has_topic_prefix else ''
        topic_profile = self.xml_parser.get_topic_profile_name(topic_name)
        topic_datatype = self.xml_parser.get_topic_datatype(topic_name)
        writer_profile = self.xml_parser.get_writer_profile_name(topic_name)
        with self._pool_lock:
            if not ConnectorPool.topic_obj_pool.get(topic_name):
                tmp = self.dds_proxy.CreateDynamicData(topic_datatype)
                dyn_data = vbs.VBSPythonDynamicData(tmp)
                dyn_type = dyn_data.GetVBSType()
                topic = self.dds_proxy.CreateTopicWithProfile_v2(
                    self.participant,
                    f'{topic_name_prefix}{topic_name}',
                    topic_datatype,
                    dyn_type,
                    topic_profile
                )
                ConnectorPool.topic_obj_pool[topic_name] = {
                    'topic': topic,
                    'dyn_data': dyn_data,
                }

            if not ConnectorPool.dds_writer_pool.get(topic_name):
                topic = ConnectorPool.topic_obj_pool[topic_name]['topic']
                dyn_data = ConnectorPool.topic_obj_pool[topic_name]['dyn_data']
                writer = evbsWriter(
                    self.dds_proxy,
                    self.participant,
                    f'{topic_name_prefix}{topic_name}',
                    topic_datatype,
                    writer_profile,
                    topic,
                    dyn_data,
                    self.xml_parser
                )
                writer.start()
                ConnectorPool.dds_writer_pool[topic_name] = writer

    def publish(self, writer, signal_name, signal_value):
        logger.info(f'发送DDS消息：{writer.topic_name} | {signal_name} = {signal_value}')
        writer.set_value(signal_name, signal_value)
        writer.write()

    def dds_send(self, signal):
        signal_name, signal_value = signal.name, signal.Value
        topic_name = self.signal_map[signal_name]
        self.create_publisher(topic_name)
        dds_writer = ConnectorPool.dds_writer_pool[topic_name]
        self.publish(dds_writer, signal_name, signal_value)

    def dds_multi_send(self, topic_name, signals):
        self.create_publisher(topic_name)
        dds_writer = ConnectorPool.dds_writer_pool[topic_name]
        for signal in signals:
            signal_name, signal_value = signal.name, signal.Value
            logger.info(f'发送DDS消息：{topic_name} | {signal_name} = {signal_value}')
            dds_writer.set_value(signal_name, signal_value)
        dds_writer.write()

    def release_connector(self):
        # 阻塞等待所有线程结束
        threads = []
        threads.extend(list(ConnectorPool.dds_writer_pool.values()))
        threads.extend(list(ConnectorPool.dds_reader_pool.values()))
        # reader/writer 线程退出
        for reader_thread in ConnectorPool.dds_reader_pool.values():
            reader_thread.stop()
            reader_thread.join()
        for writer_thread in ConnectorPool.dds_writer_pool.values():
            writer_thread.stop()
            writer_thread.join()
        for topic_name, topic_dict in ConnectorPool.topic_obj_pool.items():
            self.dds_proxy.DeleteTopic_v2(self.participant, topic_dict['topic'])
            logger.info(f'release topic {topic_name}')
        logger.success('release all topics')
        # 释放 proxy participant
        self.dds_proxy.clear()
        self.dds_proxy = None
        logger.info('release proxy and all participants')


class DDSConnectorRti(DDSConnector):
    """
    rti DDSConnector工厂类
    """
    # noinspection PyMissingConstructor
    def __init__(self, idl_filepath=''):
        self.idl_filepath = idl_filepath
        self.reader_topic_names = []
        self.writer_topic_names = []
        self.sub_connector = rti.Connector(config_name="SoaParticipantLibrary::SoaSubParticipant", url=idl_filepath)
        self.pub_connector = rti.Connector(config_name="SoaParticipantLibrary::SoaPubParticipant", url=idl_filepath)
        self.dom_tree = parse(self.idl_filepath)
        self.signal_map = {}  # {signal_name:topic_name}
        self.signal2topic()
        self.add_additional_signals()
        self.get_topic_names_from_xml()

    def signal2topic(self):
        root_node = self.dom_tree.documentElement
        structs = root_node.getElementsByTagName('struct')
        for topic_ in structs:
            topic_name = topic_.getAttribute('name')
            members = topic_.getElementsByTagName('member')
            for member in members:
                signal_name = member.getAttribute('name')
                # 区分不同topic但是相同信号名的场景
                if signal_name in env.signals_one2many:
                    signal_name += f'{topic_name.lower()}_'
                    Variable(signal_name, 0)
                # elif signal_name in ['srv_res_chrg_end_times_', 'srv_res_chrg_star_times_']:
                #     signal_name += f'{topic_name.lower()}_'
                #     Variable(signal_name, '20230101000000')
                else:
                    Variable(signal_name, 0)
                topic_name = topic_name.strip('_')
                self.signal_map[signal_name] = topic_name

    def get_topic_names_from_xml(self):
        data_readers = self.dom_tree.getElementsByTagName("data_reader")
        data_writers = self.dom_tree.getElementsByTagName("data_writer")
        for reader in data_readers:
            topic_ref = reader.getAttribute("topic_ref")
            self.reader_topic_names.append(topic_ref.replace('Topic_', ''))
        for writer in data_writers:
            topic_ref = writer.getAttribute("topic_ref")
            self.writer_topic_names.append(topic_ref.replace('Topic_', ''))
        self.reader_topic_names = sorted(self.reader_topic_names)
        self.writer_topic_names = sorted(self.writer_topic_names)

    def add_additional_signals(self):
        # 用于区分各个ECU的车辆模式
        Variable('msg_all_ecumode_feedback_ecumode_XCU', 0)
        Variable('msg_all_ecumode_feedback_ecumode_HU', 0)
        Variable('msg_all_ecumode_feedback_ecumode_FSD', 0)
        Variable('msg_all_ecumode_feedback_ecumode_FBCM', 0)
        Variable('msg_all_ecumode_feedback_ecumode_RBCM', 0)
        Variable('msg_all_ecumode_feedback_ecumode_Sus', 0)

    def create_subscriber(self, topic_name):
        if not ConnectorPool.dds_reader_pool.get(topic_name):
            dds_reader = RtiDDSReader(connector=self.sub_connector, topic_name=topic_name)
            dds_reader.start()
            ConnectorPool.dds_reader_pool[topic_name] = dds_reader

    def create_publisher(self, topic_name):
        if not ConnectorPool.dds_writer_pool.get(topic_name):
            dds_writer = RtiDDSWriter(connector=self.pub_connector, topic_name=topic_name)
            dds_writer.start()
            ConnectorPool.dds_writer_pool[topic_name] = dds_writer

    def publish(self, writer, signal_name, signal_value):
        # 处理topic不同但是信号名相同的场景
        format_signals_match = '|'.join(env.signals_one2many)
        if re.match("^({})".format(format_signals_match), signal_name):
            signal_name = '_'.join(signal_name.split('_')[0:-2]) + '_'
        logger.info(f'发送DDS消息：{writer.topic_name} | {signal_name} = {signal_value}')
        writer.set_value(signal_name, signal_value)

    def release_connector(self):
        try:
            logger.info('release rti dds_writer_pool')
            for writer_thread in ConnectorPool.dds_writer_pool.values():
                writer_thread.stop()
                writer_thread.join()
            logger.info('release rti dds_reader_pool ')
            for reader_thread in ConnectorPool.dds_reader_pool.values():
                reader_thread.stop()
            self.pub_connector.close()
            logger.info('release pub connector')
            self.sub_connector.close()
            logger.info('release sub connector')
        except:
            logger.error(traceback.format_exc())


if __name__ == '__main__':
    connector = DDSConnector(idl_filepath=r"D:\Project\soa-sil-xbp\data\matrix\XBP.xml")
    
    # logger.info('初始化 dds订阅器')
    # sub_topic_names = ['EPSModeSts']
    # for sub_tp_name in sub_topic_names:
    #     connector.create_subscriber(sub_tp_name)

    # 测试信号发送
    # signal = Variable('MSG_CellMinVolt_32960')
    # while True:
    #     signal.Value = float('nan')
    #     connector.dds_send(signal)
    #     time.sleep(1)
    #     signal.Value = float(1)
    #     connector.dds_send(signal)
    #     time.sleep(5)

    signal3 = Variable('SRV_FrtACSwReq')
    while True:
        signal3.Value = 1
        connector.dds_send(signal3)
        time.sleep(1)
        signal3.Value = 2
        connector.dds_send(signal3)
        time.sleep(1)
