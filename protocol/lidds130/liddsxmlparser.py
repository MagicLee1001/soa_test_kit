# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2024/04/01 16:50
# @File    : liddsxmlparser.py

import xml.etree.ElementTree as ET


class Parser:
    def __init__(self, xml):
        self.dds_xml = {}
        self.types = {}
        self.profiles = {}
        self.dds_xml['profiles'] = self.profiles
        self.dds_xml['types'] = self.types
        self.profiles['topics'] = {}
        self.profiles['data_writers'] = {}
        self.profiles['data_readers'] = {}
        self.types['dataTypes'] = {}
        self.xml = xml
        self.tree = ET.parse(xml)
        self.root = self.tree.getroot()
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
            self.parse_struct(dds_type)
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

    def parse_topic_in_profile(self, object):
        for topic in object.findall(f'{self.prefix}topic'):
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

    def parse_struct(self, object):
        '''
        object: type
        '''
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
                if self.profiles['topics'][topic_name]['topic_dataType'] is None:
                    self.profiles['topics'][topic_name]['topic_dataType'] = struct_name
                self.types['dataTypes'][struct_name]['members'] = {}
                for member in struct.iter(f'{self.prefix}member'):
                    message_name = member.get('name')
                    message_id = member.get('id')
                    message_type = member.get('type')
                    self.types['dataTypes'][struct_name]['members'][message_name] = {}
                    self.types['dataTypes'][struct_name]['members'][message_name]['message_id'] = message_id
                    self.types['dataTypes'][struct_name]['members'][message_name]['message_type'] = message_type
                    if 'nonBasicTypeName' in member.keys():
                        nonBasicTypeName = member.get('nonBasicTypeName')
                        self.types['dataTypes'][struct_name]['members'][message_name]['nonBasicTypeName'] = nonBasicTypeName
                if topic_name in self.profiles['topics']:
                    if self.profiles['topics'][topic_name]['topic_dataType'] is None:
                        self.profiles['topics'][topic_name]['topic_dataType'] = struct_name
            except BaseException:
                pass

    def parse_writer_reader_in_profile(self, object, writer_or_reader: str):
        '''
        param: writer_or_reader: str, data_writer, or data_reader required
        object: profile in xml
        '''
        if 'writer' in writer_or_reader:
            strings = f'{self.prefix}data_writer'
            key = 'data_writers'
        elif 'reader' in writer_or_reader:
            strings = f'{self.prefix}data_reader'
            key = 'data_readers'

        for item in object.findall(strings):
            profile_name = item.get('profile_name')
            topic = item.find(f'{self.prefix}topic')
            if topic:
                topic_name = topic.find(f'{self.prefix}name').text
                topic_dataType = topic.find(f'{self.prefix}dataType').text
            else:
                if profile_name.startswith(
                        'Soa') and profile_name.endswith('er'):
                    topic_name = profile_name.replace(
                        'Soa',
                        '').replace(
                        'Writer',
                        '').replace(
                        'Reader',
                        '')
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


if __name__ == "__main__":
    import json
    xml_file = r"D:\Project\soa-sil-xbp\data\matrix\XBP.xml"
    parser = Parser(xml_file)
