# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Email   : likun19941001@163.com
# @Time    : 2024/2/6 15:09
# @File    : rtiddssil.py

import json
import time
import math
import random
import threading
import traceback
from protocol.rtidds import rticonnextdds_connector as rti
from runner.log import logger
from runner.variable import Variable
from settings import env

# rti.Connector.set_max_objects_per_thread(65536)

_input_lock = threading.RLock()
_output_lock = threading.Lock()


class RtiDDSReader(threading.Thread):
    def __init__(self, connector, topic_name, dupl_signal_names=None):
        super().__init__()
        self.connector = connector
        self.topic_name = topic_name
        self.duplicate_signal_names = dupl_signal_names if dupl_signal_names else []
        self.datareader = self.create_datareader()
        self._is_running = threading.Event()

    def create_datareader(self):
        with _input_lock:
            try:
                return self.connector.get_input(f'SoaSubscriber::Soa{self.topic_name}Reader')
            except rti.Error:
                raise Exception(f'Failed to create datareader: {self.topic_name}')

    def is_log_message(self, key, last_value, value):
        def is_nan(f):
            return isinstance(f, float) and math.isnan(f)

        # 规则 1: key里有'xcu_system_time_'就不打印
        if 'xcu_system_time_' in key:
            return False

        # 规则 2: 两个值全为nan的时候不打印
        if is_nan(last_value) and is_nan(value):
            return False

        # 规则 3: 如果两个值都不为nan，且两个值不相等的时候，打印
        if not is_nan(last_value) and not is_nan(value) and last_value != value:
            return True

        # 如果以上情况都不满足，默认不打印
        return False

    def run(self):
        while not self._is_running.is_set():
            try:
                self.datareader.wait()  # 阻塞等待数据接收进来
                with _input_lock:
                    self.datareader.take()
                    # # if self.datareader.samples.length:
                    for sample in self.datareader.samples.valid_data_iter:
                        pass
                        data = sample.get_dictionary()
                        for key in data.keys():
                            try:
                                value = sample.get_string(key)
                                if value == '"NaN"':
                                    value = math.nan
                            except:
                                value = sample.get_number(key)
                            try:
                                # 特殊信号的值存到自定义信号中便于测试区分
                                if key == 'msg_all_ecumode_feedback_':  # 处理车辆模式信号
                                    ecu_mode_data = json.loads(value)
                                    Variable('msg_all_ecumode_feedback_ecumode_XCU').Value = ecu_mode_data[0]['Workmode']
                                    Variable('msg_all_ecumode_feedback_ecumode_HU').Value = ecu_mode_data[1]['Workmode']
                                    Variable('msg_all_ecumode_feedback_ecumode_FSD').Value = ecu_mode_data[2]['Workmode']
                                    Variable('msg_all_ecumode_feedback_ecumode_FBCM').Value = ecu_mode_data[3]['Workmode']
                                    Variable('msg_all_ecumode_feedback_ecumode_RBCM').Value = ecu_mode_data[4]['Workmode']
                                    if len(ecu_mode_data) == 6:
                                        Variable('msg_all_ecumode_feedback_ecumode_Sus').Value = ecu_mode_data[5]['Workmode']

                                elif key in ['msg_resssys_temp_', 'msg_cell_volt_']:  # 处理列表类型信号
                                    value = json.loads(value)  # [0, 0, 255, ...., 255]

                                # 不同topic同一信号名时进行处理
                                if key in self.duplicate_signal_names:
                                    new_key = f'{self.topic_name}::{key}'
                                else:
                                    new_key = key

                                # 只打印变化的信号值
                                last_value = Variable(new_key).Value
                                if self.is_log_message(new_key, last_value, value):
                                    logger.info(f'接收DDS消息：{self.topic_name} | {key} = {value}')
                                Variable(new_key).Value = value
                            except:
                                logger.error(traceback.format_exc())
            except:
                logger.error(traceback.format_exc())
        logger.info(f'reader exit: {self.topic_name}')

    def stop(self):
        self._is_running.set()


class RtiDDSWriter(threading.Thread):
    def __init__(self, connector, topic_name):
        super().__init__()
        # 最好每一个线程一个独立的connector dos测试发现所有线程共用connector会有资源抢占导致崩溃的问题
        self.connector = connector
        self.topic_name = topic_name
        self.datawriter = self.create_datawriter()
        self._is_running = threading.Event()

    def create_datawriter(self):
        with _output_lock:
            try:
                if self.topic_name.find('Soa') >= 0:
                    datawriter = "SoaPublisher::%s" % self.topic_name
                else:
                    datawriter = "SoaPublisher::Soa%sWriter" % self.topic_name
                return self.connector.get_output(datawriter)
            except rti.Error:
                raise Exception(f'Failed to create datawriter: {self.topic_name}')

    def set_value(self, signal_name, signal_value):
        with _output_lock:
            try:
                if isinstance(signal_value, str):
                    self.datawriter.instance.set_string(signal_name, signal_value)
                elif isinstance(signal_value, dict):
                    self.datawriter.instance.set_dictionary(signal_value)
                else:
                    self.datawriter.instance.set_number(signal_name, signal_value)
                # wait是保证有接收端接收再往下走,不wait就直接发出去就不管了
                # self.datawriter.wait()
            except Exception as e:
                logger.error(e)

    def write(self):
        self.datawriter.write()

    def stop(self):
        self._is_running.set()

    def run(self):
        self._is_running.wait()
        logger.info(f'writer exit: {self.topic_name}')


class RtiDDSWriterDoS(RtiDDSWriter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.stop_event = threading.Event()
        self.dds_xml_obj = kwargs.get('dds_xml_obj')
        self.interval = kwargs.get('interval', 1)

    def run(self):
        signal_names = [i.split(':')[-1] for i in self.dds_xml_obj.topic2signal[self.topic_name]]
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
    pass
    filepath = r"D:\likun3\Downloads\simulator_configs_new(1).xml"
    sub_connector = rti.Connector(config_name="SoaParticipantLibrary::SoaSubParticipant", url=filepath)
    dr = RtiDDSReader(sub_connector, topic_name='DDSMapEvent')
    dr.start()
    dr = RtiDDSReader(sub_connector, topic_name='RESSTempData32960')
    dr.start()
    dr = RtiDDSReader(sub_connector, topic_name='DDSRouteLinkInfo')
    dr.start()

    pub_connector = rti.Connector(config_name="SoaParticipantLibrary::SoaPubParticipant", url=filepath)
    dw = RtiDDSWriter(pub_connector, topic_name='DDSMapEvent')
    dw.set_value('type', 1)
    dw.write()
    pub_connector = rti.Connector(config_name="SoaParticipantLibrary::SoaPubParticipant", url=filepath)
    dw = RtiDDSWriter(pub_connector, topic_name='RESSTempData32960')
    dw.set_value('msg_resssys_temp_', {'msg_resssys_temp_': [1]*100})
    dw.write()
    pub_connector = rti.Connector(config_name="SoaParticipantLibrary::SoaPubParticipant", url=filepath)
    dw = RtiDDSWriter(pub_connector, topic_name='DDSRouteLinkInfo')
    dyna_value = {
        "timestamp": 1641838209182,
        "pathId": 100,
        "linkInfos": [
            {"id": 1, "length": 500, "travelTime": 300, "staticTravelTime": 290},
            {"id": 2, "length": 1000, "travelTime": 900, "staticTravelTime": 850},
            # ... 更多 LinkInfo
        ]
    }
    dw.set_value('linkInfos', dyna_value)
    dw.write()

