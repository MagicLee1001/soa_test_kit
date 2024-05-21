# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Email   : likun19941001@163.com
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
from protocol.rtidds.rtiddsxmlparser import ParseXML
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
        self.signal_map = self.xml_parser.signal_map  # {signal_name:topic_name}
        self.signal2var()
        self.get_topic_names_from_xml()

    def __new__(cls, *args, **kwargs):
        """单例模式"""
        with cls._instance_lock:
            if not cls._instance:
                cls._instance = super().__new__(cls)
            return cls._instance

    def signal2var(self):
        for signal_name in self.signal_map.keys():
            Variable(signal_name, 0)

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
        if '::' in signal_name:  # 处理topic不同但信号名相同的场景
            signal_name = signal_name.split('::')[-1]
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
            if '::' in signal_name:  # 处理topic不同但信号名相同的场景
                signal_name = signal_name.split('::')[-1]
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
        self.dom_tree = parse(self.idl_filepath)
        self.reader_topic_names = []
        self.writer_topic_names = []
        self.dupl_signal_names = []
        self.xml_parser = ParseXML(self.idl_filepath)
        self.signal_map = self.xml_parser.signal_map  # {signal_name:topic_name}
        self.dupl_signal_names = self.xml_parser.dupl_signal_names
        self.signal2var()
        self.add_additional_signals()
        self.get_topic_names_from_xml()
        self.sub_connector = rti.Connector(config_name="SoaParticipantLibrary::SoaSubParticipant", url=idl_filepath)
        self.pub_connector = rti.Connector(config_name="SoaParticipantLibrary::SoaPubParticipant", url=idl_filepath)

    def signal2var(self):
        for signal_name in self.signal_map.keys():
            Variable(signal_name, 0)

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
            dds_reader = RtiDDSReader(connector=self.sub_connector, topic_name=topic_name, dupl_signal_names=self.dupl_signal_names)
            dds_reader.start()
            ConnectorPool.dds_reader_pool[topic_name] = dds_reader

    def create_publisher(self, topic_name):
        if not ConnectorPool.dds_writer_pool.get(topic_name):
            dds_writer = RtiDDSWriter(connector=self.pub_connector, topic_name=topic_name)
            dds_writer.start()
            ConnectorPool.dds_writer_pool[topic_name] = dds_writer

    def release_connector(self):
        try:
            logger.info('release rti dds_writer_pool')
            for writer_thread in ConnectorPool.dds_writer_pool.values():
                writer_thread.stop()
                writer_thread.join()
            logger.info('release rti dds_reader_pool ')
            for reader_thread in ConnectorPool.dds_reader_pool.values():
                reader_thread.stop()
            time.sleep(1)
            self.pub_connector.close()
            logger.info('release pub connector')
            self.sub_connector.close()
            logger.info('release sub connector')
        except:
            logger.error(traceback.format_exc())


if __name__ == '__main__':
    pass
    # 测试 lidds
    env.load(r"D:\Project\soa-sil-xbp\data\conf\settings_xbp.yaml")
    dds_connector = DDSConnector(idl_filepath=r"D:\Project\soa-sil-xbp\data\matrix\vbs_XBP2.2.0.xml")
    dds_connector.create_subscriber('BrakeSystemStatus')
    dds_connector.create_subscriber('AdUploadCanFrequencyRequest')
    signal = Variable('AdUploadCanFrequencyRequest::AdUploadCanFrequencyHeader.Timestamp')
    signal.Value = 100
    dds_connector.dds_send(signal)
    signal = Variable('BrakeSystemStatus::MSG_ActuBrkPdlPrsdSts')
    signal.Value = 100
    dds_connector.dds_send(signal)
    signal = Variable('m_Data')
    signal.Value = [8] * 10
    dds_connector.dds_send(signal)
    time.sleep(1)
    dds_connector.release_connector()

    # 测试 rti
    # env.load(r"D:\Project\soa-sil-xbp\data\conf\settings_xap.yaml")
    # dds_connector = DDSConnectorRti(idl_filepath=r"D:\Project\soa-sil-xbp\data\matrix\rti_XAP241&XPP361.xml")
    # dds_connector.create_subscriber('ToolBoxDsp')
    #
    # # 测试信号发送
    # signal = Variable('ToolBoxDsp::msg_blwr_vol_fdbk_')
    # signal.Value = 2
    # time.sleep(1)
    # dds_connector.dds_send(signal)
    # dds_connector.release_connector()
