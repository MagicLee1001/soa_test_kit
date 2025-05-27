#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2023/8/23 10:40
# @Author  :Liu Xi

import xml.etree.ElementTree as ET
from runner.log import logger


class Parser:
    def __init__(self, xml):
        self.dds_xml = {}
        self.types = {}
        self.profiles = {}
        self.signal_map = {}
        self.signal2type = {}
        self.topic2signal = {}
        self.dupl_signal_names = []
        self.dds_xml['profiles'] = self.profiles
        self.dds_xml['types'] = self.types
        self.profiles['topics'] = {}
        self.profiles['data_writers'] = {}
        self.profiles['data_readers'] = {}
        self.types['dataTypes'] = {}
        self.types['typedefs'] = {}
        self.xml = xml
        self.tree = ET.parse(xml)
        self.root = self.tree.getroot()
        self.struct_names = []
        self.typedef_names = []
        dds_profile = self.root.find(
            '{http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles}profiles')
        if dds_profile:
            self.prefix = '{http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles}'
        else:
            self.prefix = ''
        dds_profile = self.root.find(f'{self.prefix}profiles')
        dds_type = self.root.find(f'{self.prefix}types')
        try:
            self.parse_topic_in_profile(dds_profile)
        except BaseException:
            pass
        try:
            self.parse_writer_reader_in_profile(dds_profile, 'writer')
        except BaseException:
            pass
        try:
            self.parse_writer_reader_in_profile(dds_profile, 'reader')
        except BaseException:
            pass
        try:
            self.parse_typedef()
        except BaseException:
            pass
        try:
            self.parse_struct()
        except BaseException:
            pass
        try:
            self.parse_signal2topic()
        except BaseException:
            pass

    def get_topic_profile_name(self, topic_name):
        return self.profiles['topics'][topic_name]['topic_profile_name']

    def get_reader_profile_name(self, topic_name):
        return self.profiles['data_readers'][topic_name]['topic']['profile_name']

    def get_writer_profile_name(self, topic_name):
        return self.profiles['data_writers'][topic_name]['topic']['profile_name']

    def get_topic_datatype(self, topic_name):
        return self.profiles['topics'][topic_name]['topic_dataType']

    def parse_topic_in_profile(self, profile_object):
        for topic in profile_object.findall(f'{self.prefix}topic'):
            topic_profile_name = topic.get('profile_name')
            try:
                topic_name = topic.find(f'{self.prefix}name').text
            except BaseException:
                topic_name = topic_profile_name.replace('_prof', '')
            try:
                topic_dataType = topic.find(f'{self.prefix}dataType').text
            except BaseException:
                topic_dataType = None
            self.profiles['topics'][topic_name] = {}
            self.profiles['topics'][topic_name]['self'] = 'name'
            self.profiles['topics'][topic_name]['topic_profile_name'] = topic_profile_name
            self.profiles['topics'][topic_name]['topic_dataType'] = topic_dataType

    def parse_struct(self):
        for struct in self.root.iter(f'{self.prefix}struct'):
            name = struct.get('name')
            if name:
                self.struct_names.append(name)
        for struct in self.root.iter(f'{self.prefix}struct'):
            try:
                struct_name = struct.get('name')
                if "::" in struct_name:
                    topic_name = struct_name.split("::")[-1]
                    if topic_name.endswith('_'):
                        topic_name = topic_name[:-1]
                else:
                    topic_name = struct_name.split('_')[-1]
                self.types['dataTypes'][struct_name] = {}
                self.types['dataTypes'][struct_name]['topic_name'] = topic_name
                self.types['dataTypes'][struct_name]['members'] = {}
                for member in struct.iter(f'{self.prefix}member'):
                    message_name = member.get('name')
                    message_id = member.get('id')
                    message_type = member.get('type')
                    self.types['dataTypes'][struct_name]['members'][message_name] = {}
                    self.types['dataTypes'][struct_name]['members'][message_name]['message_id'] = message_id
                    self.types['dataTypes'][struct_name]['members'][message_name]['message_type'] = message_type
                    if 'nonBasicTypeName' in member.keys():
                        non_basic_type_name = member.get('nonBasicTypeName')
                        self.types['dataTypes'][struct_name]['members'][message_name]['nonBasicTypeName'] = non_basic_type_name
                        if non_basic_type_name in self.struct_names:
                            self.types['dataTypes'][struct_name]['members'][message_name]['ref'] = 'struct'
                        elif non_basic_type_name in self.typedef_names:
                            self.types['dataTypes'][struct_name]['members'][message_name]['ref'] = 'typedef'
                if topic_name in self.profiles['topics']:
                    if self.profiles['topics'][topic_name]['topic_dataType'] is None:
                        self.profiles['topics'][topic_name]['topic_dataType'] = struct_name
            except BaseException:
                pass

    def parse_typedef(self):
        for type_def in self.root.iter(f'{self.prefix}typedef'):
            try:
                name = type_def.get('name')
                if name:
                    self.typedef_names.append(name)
                    self.types['typedefs'][name] = type_def.attrib
            except BaseException:
                pass

    def parse_writer_reader_in_profile(self, profile_object, writer_or_reader: str):
        '''
        param:
            profile_object: profile in xml
            writer_or_reader: str, data_writer, or data_reader required
        '''
        if 'writer' in writer_or_reader:
            strings = f'{self.prefix}data_writer'
            key = 'data_writers'
        elif 'reader' in writer_or_reader:
            strings = f'{self.prefix}data_reader'
            key = 'data_readers'
        else:
            return

        for item in profile_object.findall(strings):
            profile_name = item.get('profile_name')
            topic = item.find(f'{self.prefix}topic')
            if topic:
                topic_name = topic.find(f'{self.prefix}name').text
                topic_dataType = topic.find(f'{self.prefix}dataType').text
            else:
                if profile_name.startswith('Soa') and profile_name.endswith('er'):
                    topic_name = profile_name.replace('Soa', '').replace('Writer', '').replace('Reader', '')
                    topic_dataType = None
                else:
                    topic_name = profile_name
                    topic_dataType = None
            self.profiles[key][topic_name] = {}
            self.profiles[key][topic_name]['topic'] = {}
            self.profiles[key][topic_name]['topic']['name'] = topic_name
            self.profiles[key][topic_name]['topic']['profile_name'] = profile_name
            self.profiles[key][topic_name]['topic']['topic_dataType'] = topic_dataType

            self.profiles[key][topic_name]['qos'] = {}
            qos = item.find(f'{self.prefix}qos')
            if not qos:
                qos = item
            reliability = qos.find(f'{self.prefix}reliability')
            if reliability:
                reliability_kind = reliability.find(f'{self.prefix}kind').text
            else:
                reliability_kind = None
            durability = qos.find(f'{self.prefix}durability')
            if durability:
                durability_kind = durability.find(f'{self.prefix}kind').text
            else:
                durability_kind = None
            liveliness = qos.find(f'{self.prefix}liveliness')
            if liveliness:
                liveliness_kind = liveliness.find(f'{self.prefix}kind').text
            else:
                liveliness_kind = None
            ownership = qos.find(f'{self.prefix}ownership')
            if ownership:
                ownership_kind = ownership.find(f'{self.prefix}kind').text
            else:
                ownership_kind = None
            historyQos = qos.find(f'{self.prefix}historyQos')
            if historyQos:
                historyQos_kind = historyQos.find(f'{self.prefix}kind').text
                try:
                    historyQos_depth = historyQos.find(
                        f'{self.prefix}depth').text
                except BaseException:
                    historyQos_depth = None
            else:
                historyQos_kind = None
                historyQos_depth = None
            e2e_protection = qos.find(f'{self.prefix}e2e_protection')
            if e2e_protection is not None:
                e2e_protection_value = e2e_protection.text
            else:
                e2e_protection_value = 'False'
            self.profiles[key][topic_name]['qos']['reliability'] = {}
            self.profiles[key][topic_name]['qos']['reliability']['kind'] = reliability_kind
            self.profiles[key][topic_name]['qos']['durability'] = {}
            self.profiles[key][topic_name]['qos']['durability']['kind'] = durability_kind
            self.profiles[key][topic_name]['qos']['liveliness'] = {}
            self.profiles[key][topic_name]['qos']['liveliness']['kind'] = liveliness_kind
            self.profiles[key][topic_name]['qos']['ownership'] = {}
            self.profiles[key][topic_name]['qos']['ownership']['kind'] = ownership_kind
            self.profiles[key][topic_name]['qos']['historyQos'] = {}
            self.profiles[key][topic_name]['qos']['historyQos']['kind'] = historyQos_kind
            self.profiles[key][topic_name]['qos']['historyQos']['depth'] = historyQos_depth
            self.profiles[key][topic_name]['qos']['e2e_protection'] = {}
            self.profiles[key][topic_name]['qos']['e2e_protection']['e2e_protection'] = e2e_protection_value

    def parse_signal2topic(self):
        """
        不同topic(struct) 但member name相同时信号名用 topicName::signalName标识
        nonBasic 结构体嵌套类型的信号，信号名格式为 message_name.noBasicMemberName
        """
        data_types = self.types['dataTypes']  # struct
        for key, val in data_types.items():
            topic_name = val['topic_name']
            try:
                if topic_name in self.profiles['topics']:  # 有些struct不是topic:
                    members = val['members']
                    signal_name_list = []
                    for signal_name in members.keys():
                        message_type = members[signal_name]['message_type']
                        self.signal2type[signal_name] = message_type
                        if message_type == 'nonBasic':
                            no_basic_ref = members[signal_name]['ref']
                            if no_basic_ref == 'struct':  # 结构体嵌套格式
                                no_basic_type_name = members[signal_name]['nonBasicTypeName']
                                for member_name in data_types[no_basic_type_name]['members'].keys():
                                    combine = f'{signal_name}.{member_name}'
                                    signal_name_list.append(combine)
                            elif no_basic_ref == 'typedef':
                                signal_name_list.append(signal_name)
                        else:
                            signal_name_list.append(signal_name)

                    for signal_name_ in signal_name_list:
                        if signal_name_ in self.signal_map:  # 信号名相同 topic不同的情况下拼接
                            if signal_name_ not in self.dupl_signal_names:
                                self.dupl_signal_names.append(signal_name_)
                            diff_topic_name = self.signal_map[signal_name_]
                            self.signal_map.pop(signal_name_, None)
                            diff_signal_name = f'{diff_topic_name}::{signal_name_}'
                            self.signal_map[diff_signal_name] = diff_topic_name
                            self.signal_map[f'{topic_name}::{signal_name_}'] = topic_name
                        elif signal_name_ in self.dupl_signal_names:
                            self.signal_map[f'{topic_name}::{signal_name_}'] = topic_name
                        else:
                            self.signal_map[signal_name_] = topic_name
            except Exception as e:
                logger.error(f'signal2topic fail: {e}, topic_name: {topic_name}')

        for k, v in self.signal_map.items():
            if v not in self.topic2signal:
                self.topic2signal[v] = [k]
            else:
                self.topic2signal[v].append(k)

        print_s = '\n'.join(self.dupl_signal_names)
        logger.info(f'Duplicate signal names:\n{print_s}')


if __name__ == "__main__":
    import json
    xml_file = r"D:\Project\soa-sil-xbp\data\matrix\vbs_XBP2.2.0.xml"
    # xml_file = r"D:\2_work\37_EEA2.5\matrix\V0.2.1\QoS.xml"
    parser = Parser(xml_file)
    print(json.dumps(parser.profiles['topics']))
    # print(json.dumps(parser.profiles['data_writers']))
    # print(json.dumps(parser.profiles['data_readers']))
    # print(json.dumps(parser.types['dataTypes']))
