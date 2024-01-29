# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2023/10/19 17:30
# @File    : dds.py

import time
import threading
from loguru import logger
from runner.variable import Variable
from lidds import evbs
from lidds.liddssil import Parser, evbsWriter, evbsReader
from connector import ConnectorPool


class DDSConnector:
    _instance_lock = threading.Lock()
    _instance = None

    def __init__(self, idl_filepath=''):
        self.idl_filepath = idl_filepath
        self.dds_proxy = evbs.VBSPythonDynamicProxy().getInstance()
        self.dds_proxy.LoadXML(self.idl_filepath)
        self.xml_parser = Parser(self.idl_filepath)
        self.signal_map = {}  # {signal_name:topic_name}
        self.signal2topic()

    def __new__(cls, *args, **kwargs):
        """单例模式"""
        with cls._instance_lock:
            if not cls._instance:
                cls._instance = super().__new__(cls)
            return cls._instance

    def signal2topic(self):
        data_types = self.xml_parser.types['dataTypes']
        for key, val in data_types.items():
            topic_name = val['topic_name']
            members = val['members']
            for signal_name in members.keys():
                Variable(signal_name, 0)
                self.signal_map[signal_name] = topic_name

    def create_subscriber(self, topic_name):
        topic_profile = self.xml_parser.profiles['topics'][topic_name]['topic_profile_name']
        reader_profile = self.xml_parser.profiles['data_readers'][topic_name]['topic']['profile_name']
        topic_datatype = self.xml_parser.profiles['data_readers'][topic_name]['topic']['topic_dataType']
        if not ConnectorPool.dds_reader_pool.get(topic_name):
            logger.info(f'Create subscriber, TopicName:{topic_name}, TopicDatatype:{topic_datatype}')
            reader = evbsReader(self.xml_parser.dds_xml)
            reader.create(
                self.dds_proxy,
                topic_profile,
                topic_name,
                reader_profile,
                topic_datatype
            )
            reader.start()
            ConnectorPool.dds_reader_pool[topic_name] = reader

    def create_publisher(self, topic_name):
        topic_profile = self.xml_parser.profiles['topics'][topic_name]['topic_profile_name']
        reader_profile = self.xml_parser.profiles['data_writers'][topic_name]['topic']['profile_name']
        topic_datatype = self.xml_parser.profiles['data_writers'][topic_name]['topic']['topic_dataType']
        if not ConnectorPool.dds_writer_pool.get(topic_name):
            writer = evbsWriter(self.xml_parser.dds_xml)
            writer.create(
                self.dds_proxy,
                topic_profile,
                topic_name,
                reader_profile,
                topic_datatype
            )
            writer.start()
            time.sleep(2)  # 这一步多等一会儿，等writer真正创建完成后发送才生效
            ConnectorPool.dds_writer_pool[topic_name] = writer
            logger.info(f'Create DataWriter, TopicName:{topic_name}, TopicDatatype:{topic_datatype}')

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
        logger.info('release dds_writer_pool.')
        # 现在是释放不了的
        for pub_tp_name, writer in ConnectorPool.dds_writer_pool.items():
            writer.delete()
            writer.release_proxy()
        logger.info('release dds_reader_pool.')
        for sub_tp_name, reader in ConnectorPool.dds_reader_pool.items():
            reader.delete()
            reader.release_proxy()


if __name__ == '__main__':
    connector = DDSConnector(idl_filepath=r"D:\Project\soa-sil-xbp\data\matrix\XBP.xml")
    # xml_parser = connector.xml_parser
    # print(json.dumps(xml_parser.profiles['topics']))
    # print(json.dumps(xml_parser.profiles['data_writers']))
    # print(json.dumps(xml_parser.profiles['data_readers']))
    # print(json.dumps(xml_parser.types['dataTypes']))
    # print(json.dumps(connector.signal_map))

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
