# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Email   : likun19941001@163.com
# @Time    : 2024/4/26 14:23
# @File    : rtiddsxmlparser.py

import xml.etree.ElementTree as ET
from runner.variable import Variable
from runner.log import logger


class ParseXML:
    def __init__(self, xml_filepath):
        self.xml_filepath = xml_filepath
        self.tree = ET.parse(self.xml_filepath)
        self.root = self.tree.getroot()
        self.signal_map = {}
        self.topic2signal = {}
        self.dupl_signal_names = []
        self.topic_ref = {}
        self.signal2topic()
        # self.parse_topic()

    def find_struct_by_path(self, path):
        """
        根据types节点下的数据结构表达式，如 soa_messages::msg::dds_::INS_ 找到struct
        """
        module_names, struct_name = path.split("::")[:-1], path.split("::")[-1]
        xpath_expr = "."
        for name in module_names:
            xpath_expr += f"/module[@name='{name}']"
        matching_modules = self.root.find('types').findall(xpath_expr)
        # 在每个匹配的module中查找struct
        for module_element in matching_modules:
            struct_element = module_element.find(f"./struct[@name='{struct_name}']")
            if struct_element is not None:
                return struct_element
        return None

    def signal2topic(self):
        for topic in self.root.findall('.//topic'):
            topic_name = topic.get('name').replace('Topic_', '')
            type_ref = topic.get('register_type_ref')
            self.topic_ref[topic_name] = {'type_ref': type_ref, 'members': {}}
            members_node = self.find_struct_by_path(type_ref)
            for member in members_node.findall('member'):
                signal_name = member.get('name')
                _id = member.get('id')
                _type = member.get('type')
                self.topic_ref[topic_name]['members'][signal_name] = {'id': _id, 'type': _type}
                if signal_name in self.signal_map:  # 信号名相同 topic不同的情况下拼接
                    if signal_name not in self.dupl_signal_names:
                        self.dupl_signal_names.append(signal_name)
                    diff_topic_name = self.signal_map[signal_name]
                    self.signal_map.pop(signal_name, None)
                    diff_signal_name = f'{diff_topic_name}::{signal_name}'
                    self.signal_map[diff_signal_name] = diff_topic_name
                    self.signal_map[f'{topic_name}::{signal_name}'] = topic_name
                elif signal_name in self.dupl_signal_names:
                    self.signal_map[f'{topic_name}::{signal_name}'] = topic_name
                else:
                    self.signal_map[signal_name] = topic_name
        for k, v in self.signal_map.items():
            if v not in self.topic2signal:
                self.topic2signal[v] = [k]
            else:
                self.topic2signal[v].append(k)

        print_s = '\n'.join(self.dupl_signal_names)
        logger.info(f'Duplicate signal names:\n{print_s}')


if __name__ == '__main__':
    parser = ParseXML(r"D:\likun3\Downloads\simulator_configs_new(1).xml")
    print(parser.signal_map['DDSMapEvent::timestamp'])
