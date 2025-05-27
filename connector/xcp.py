# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2025/4/8 13:33
# @File    : xcp.py
# original by: liuxi1

import os
import sys
import traceback
import re
import struct
import threading
import time
from ctypes import c_ubyte, c_uint, c_ulong, c_ushort
from pyxcp.cmdline import ArgumentParser
import pyxcp.types as types
from runner.variable import Variable
from settings import work_dir
try:
    from runner.log import logger
except:
    from loguru import logger


MEASUREMENT_OPTIONAL_PARAMETERS = [
    "ADDRESS_TYPE",
    "ANNOTATION",
    "ARRAY_SIZE",
    "BIT_MASK",
    "BIT_OPERATION",
    "BYTE_ORDER",
    "DISCRETE",
    "DISPLAY_IDENTIFIER",
    "ECU_ADDRESS",
    "ECU_ADDRESS_EXTENSION",
    "ERROR_MASK",
    "FORMAT",
    "FUNCTION_LIST",
    "IF_DATA",
    "LAYOUT",
    "MATRIX_DIM",
    "MAX_REFRESH",
    "MODEL_LINK",
    "PHYS_UNIT",
    "READ_WRITE",
    "REF_MEMORY_SEGMENT",
    "SYMBOL_LINK"
    "VIRTUAL"
]
CHARACTERISTIC_OPTIONAL_PARAMETERS = [
    "ANNOTATION",
    "AXIS_DESCR",
    "BIT_MASK",
    "BYTE_ORDER",
    "CALIBRATION_ACCESS",
    "COMPARISON_QUANTITY",
    "DEPENDENT_CHARACTERISTIC",
    "DISCRETE",
    "DISPLAY_IDENTIFIER",
    "ECU_ADDRESS_EXTENSION",
    "ENCODING",
    "EXTENDED_LIMITS",
    "FORMAT",
    "FUNCTION_LIST",
    "GUARD_RAILS",
    "IF_DATA",
    "MAP_LIST",
    "MATRIX_DIM",
    "MAX_REFRESH",
    "MODEL_LINK",
    "NUMBER",
    "PHYS_UNIT",
    "READ_ONLY",
    "REF_MEMORY_SEGMENT",
    "STEP_SIZE",
    "SYMBOL_LINK",
    "VIRTUAL_CHARACTERISTIC"
]
COMPU_METHOD_OPTIONAL_PARAMETERS = [
    "COEFFS",
    "COEFFS_LINEAR",
    "COMPU_TAB_REF",
    "FORMULA",
    "REF_UNIT",
    "STATUS_STRING_REF"
]
COMPU_TAB_OPTIONAL_PARAMETERS = [
    "DEFAULT_VALUE",
    "DEFAULT_VALUE_NUMERIC"
]
COMPU_VTAB_OPTIONAL_PARAMETERS = [
    "DEFAULT_VALUE"
]
RECORD_LAYOUT_OPTIONAL_PARAMETERS = [
    "ALIGNMENT_BYTE",
    "ALIGNMENT_FLOAT32_IEEE",
    "ALIGNMENT_FLOAT64_IEEE",
    "ALIGNMENT_INT64",
    "ALIGNMENT_LONG",
    "ALIGNMENT_WORD",
    "AXIS_PTS_X/_Y/_Z/_4/_5",
    "AXIS_RESCALE_X",
    "DIST_OP_X/_Y/_Z/_4/_5",
    "FIX_NO_AXIS_PTS_X/_Y/_Z/_4/_5",
    "FNC_VALUES",
    "IDENTIFICATION",
    "NO_AXIS_PTS_X/_Y/_Z/_4/_5",
    "NO_RESCALE_X",
    "OFFSET_X/_Y/_Z/_4/_5",
    "RESERVED",
    "RIP_ADDR_W/_X/_Y/_Z/_4/_5",
    "SRC_ADDR_X/_Y/_Z/_4/_5",
    "SHIFT_OP_X/_Y/_Z/_4/_5",
    "STATIC_ADDRESS_OFFSETS"
    "STATIC_RECORD_LAYOUT"
]
DESCRIPTORS = [
    "MEASUREMENT",
    "CHARACTERISTIC",
    "COMPU_TAB",
    "COMPU_METHOD",
    "RECORD_LAYOUT",
    "COMPU_VTAB"
]
ESCAPTION_SYMBOLS = [
    '.', '^', '$', '*', '+', '?', '{', '}', '[', '\\', '|', '(', ')'
]

# set up empty dicts to use for storing objects
axesDefs = {}
mapDefs = {}
compuMethods = {}
compuTabs = {}
compuVtabs = {}
measurements = {}
characteristics = {}
record_layouts = {}

# 不同的数据类型对应的数据Size
DataSize = {'UBYTE': 1,
            'SBYTE': 1,
            'UWORD': 2,
            'SWORD': 2,
            'ULONG': 4,
            'SLONG': 4,
            'A_UINT64': 8,
            'A_INT64': 8,
            'FLOAT32_IEEE': 4,
            'FLOAT64_IEEE': 8}
DATATYPE_PATTERN = ' UBYTE | SBYTE | UWORD | SWORD | ULONG | SLONG | A_UINT64 | A_INT64 | FLOAT32_IEEE | FLOAT64_IEEE '
CHARACTERISTIC_TYPE_STRING = 'ASCII'
CHARACTERISTIC_TYPE_SCALAR = 'VALUE'
CHARACTERISTIC_TYPE_1D_ARR = 'CURVE'
CHARACTERISTIC_TYPE_2D_ARR = 'MAP'
CHARACTERISTIC_TYPE_3D_ARR = 'CUBOID'
CHARACTERISTIC_TYPE_4D_ARR = 'CUBE_4'
CHARACTERISTIC_TYPE_5D_ARR = 'CUBE_5'
CHARACTERISTIC_TYPE_0D_ARR = 'VAL_BLK'
CAN_ID_MASTER_PATTERN_WHOLE = r'CAN_ID_MASTER +(0x)?\w+'
CAN_ID_MASTER_PATTERN = r'(?<=CAN_ID_MASTER) +(0x)?\w+'
CAN_ID_SLAVE_PATTERN_WHOLE = r'CAN_ID_SLAVE +(0x)?\w+'
CAN_ID_SLAVE_PATTERN = r'(?<=CAN_ID_SLAVE) +(0x)?\w+'
BAUDRATE_PATTERN_WHOLE = r'BAUDRATE +(0x)?\w+'
BAUDRATE_PATTERN = r'(?<=BAUDRATE) +(0x)?\w+'
SAMPLE_POINT_PATTERN_WHOLE = r'SAMPLE_POINT +(0x)?\w+'
SAMPLE_POINT_PATTERN = r'(?<=SAMPLE_POINT) +(0x)?\w+'

STATUS_OK = 0x00  # PCCP工作状态 ：OK
STATUS_NG_A2L_NOT_LOAD = 0x01  # PCCP工作状态 ：NG A2l文件未加载或加载失败
STATUS_NG_CAN_NOT_INIT = 0x02  # PCCP工作状态 ：NG CAN未初始化或初始化失败
STATUS_NG_CCP_NOT_INIT = 0x04  # PCCP工作状态 ：NG CCP未初始化或初始化失败

# CCP
STATUS_RSM_CALIBRATION = 0x1  # 功能受限状态 ： CALIBRATION功能处于受保护
STATUS_RSM_DATA_ADQUISITION = 0x2  # 功能受限状态 ： DATA_ADQUISITION功能处于受保护
STATUS_RSM_MEMORY_PROGRAMMING = 0x40  # 功能受限状态 ： MEMORY_PROGRAMMING功能处于受保护

# XCP
STATUS_RSM_XCP_CAL_PAG = 0x1  # 功能受限状态 ： CALibration/PAGing commands处于受保护
STATUS_RSM_XCP_DAQ = 0x4  # 功能受限状态 ： DAQ list commands (DIRECTION = DAQ)处于受保护
STATUS_RSM_XCP_STIM = 0x08  # 功能受限状态 ： DAQ list commands (DIRECTION = STIM)处于受保护
STATUS_RSM_XCP_PGM = 0x10  # 功能受限状态 ： ProGraMming commands处于受保护

IS_SHORT_UP_LOAD = True


class CanLogStruct:
    def __init__(self):
        self.data = []
        self.utc_timestamp = []


class Map3D:
    name = ""
    description = ""
    ecu_address = ""
    function = ""
    displayFormat = ""
    xAxisLabel = ""
    xAxisAddress = ""
    xAxisFunction = ""
    yAxisLabel = ""
    yAxisAddress = ""
    yAxisFunction = ""


# An Axis is part of a map
class Axis:
    name = ""
    ecu_address = ""
    function = ""


# CompuMethod is the way the raw data is converted into human readable/actual numnbers
class CompuMethod:
    def __init__(self):
        self.name = ""
        self.long_identifier = ""  # name of the compute method
        self.conversion_type = ""
        self.format = ""
        self.unit = ""
        self.coeffs = ""  ##OPTIONAL PROPERTIES
        self.coeffs_linear = ""
        self.compu_tab_ref = ""
        self.formula = ""
        self.ref_unit = ""
        self.status_string_ref = ""  ##OPTIONAL PROPERTIES
        self.function = ""  ##self-defined parameter
        self.Coefficients = ""


class XCPProtocol:
    def __init__(self):
        self.CAN_ID_MASTER = None
        self.CAN_ID_SLAVE = None
        self.BAUDRATE = None
        self.SAMPLE_POINT = None


class FncValues:
    def __init__(self):
        self.position = ""
        self.datatype = ""
        self.index_mode = ""
        self.address_type = ""


# RecordLayout is the storing construction of characteristics
class RecordLayout:
    def __init__(self):
        self.name = ""
        self.fnc_values = FncValues()


# Measurements are memory locations
class Measurement:
    def __init__(self):
        self.name = ""
        self.long_identifier = ""
        self.ecu_address = ""
        self.ecu_address_extension = ""
        self.conversion = ""  # compute method
        self.datatype = ""
        self.size = ""
        self.display_identifier = ""
        self.format = ""
        self.resolution = ""
        self.accuracy = ""
        self.lower_limit = ""
        self.upper_limit = ""
        self.matrix_dim = ""


# Characteristics are memory locations
class Characteristic:
    def __init__(self):
        self.name = ""
        self.long_identifier = ""
        self.ecu_address = ""
        self.ecu_address_extension = ""
        self.conversion = ""  # compute method
        self.type = ""
        self.deposit = ""  ## record layout
        self.max_diff = ""
        self.display_identifier = ""
        self.record_layout = ""
        self.matrix_dim = ""


class CompuTab:
    def __init__(self):
        self.name = ""
        self.long_identifier = ""
        self.conversion_type = ""
        self.number_value_pairs = ""
        self.default_value = ""
        self.default_value_numeric = ""


class CompuVtab:
    def __init__(self):
        self.name = ""
        self.long_identifier = ""
        self.conversion_type = ""
        self.number_value_pairs = ""
        self.default_value = ""


class A2LParser:
    def __init__(self):
        self.measurements = {}
        self.characteristics = {}
        self.record_layouts = {}
        self.compuTabs = {}
        self.compuVtabs = {}
        self.compuMethods = {}
        self.axesDefs = {}
        self.mapDefs = {}
        self._vendor = ''
        self.display_id_map = {}
        self.asap2_version = None

    def escape_specfic_symbol(self, strings: str):
        new_strings = ""
        for i in strings:
            if i in ESCAPTION_SYMBOLS:
                new_strings = new_strings + ('\\' + i)
            else:
                new_strings = new_strings + i
        return new_strings

    def stanza_split(self, block, key_word_list):
        # lineNum = 0
        line_list = block.split("\n")
        position_param_list = []
        # keyword_param_list = copy.deepcopy(line_list)
        keyword_param_list = []
        # keyword_param_list.reverse()
        IF_DATA_BLOCK = False
        for line in line_list:
            line = line.strip()
            if '/begin IF_DATA' in line:
                IF_DATA_BLOCK = True
                continue
            elif '/end IF_DATA' in line:
                IF_DATA_BLOCK = False
                continue
            if IF_DATA_BLOCK:
                continue
            elif " " in line:
                if line.split(" ")[0] in key_word_list:
                    keyword_param_list.append(line)
                    continue
                    # break
                elif line.split(" ")[0] == r'\/begin':
                    if line.split(" ")[1] in key_word_list:
                        keyword_param_list.append(line)
                        continue
                        # break
            position_param_list.append(line)
            # keyword_param_list.pop()
            # lineNum = lineNum + 1
        # if keyword_param_list:
        #     keyword_param_list.reverse()
        return position_param_list, keyword_param_list

    # These are functions used to parse a stanza
    def parseMeasurement(self, stanza):
        position_param_list = stanza[0]
        keyword_param_list = stanza[1]

        thisMeasurement = Measurement()
        if self.asap2_version == '1.61':
            for sentence in position_param_list:
                if '/* Name'.lower() in sentence.lower():
                    thisMeasurement.name = sentence.split('*/')[-1].strip()
                elif '/* Long identifier'.lower() in sentence.lower():
                    thisMeasurement.long_identifier = sentence.split('*/')[-1].strip()
                elif '/* Data type'.lower() in sentence.lower():
                    thisMeasurement.datatype = sentence.split('*/')[-1].strip()
                elif '/* Conversion method'.lower() in sentence.lower():
                    thisMeasurement.conversion = sentence.split('*/')[-1].strip()
                elif '/* Resolution'.lower() in sentence.lower():
                    thisMeasurement.resolution = sentence.split('*/')[-1].strip()
                elif '/* Accuracy'.lower() in sentence.lower():
                    thisMeasurement.accuracy = sentence.split('*/')[-1].strip()
                elif '/* Lower limit'.lower() in sentence.lower():
                    thisMeasurement.lower_limit = sentence.split('*/')[-1].strip()
                elif '/* Upper limit'.lower() in sentence.lower():
                    thisMeasurement.upper_limit = sentence.split('*/')[-1].strip()
            for line in keyword_param_list:
                line = line.strip()
                if re.match("^ECU_ADDRESS .*", line):
                    thisMeasurement.ecu_address = line.split()[1]
                if re.match("^ECU_ADDRESS_EXTENSION .*", line):
                    thisMeasurement.ecu_address_extension = line.split()[1]
                if re.match("^DISPLAY_IDENTIFIER.*", line):
                    thisMeasurement.display_identifier = line.split()[1]
                    if thisMeasurement.name:
                        self.display_id_map[thisMeasurement.display_identifier] = thisMeasurement.name
                if re.match("^MATRIX_DIM.*", line):
                    thisMeasurement.matrix_dim = re.findall(r'\d+ +\d+ +\d+', line)[0]
        else:
            position_param_block = ' '.join(position_param_list)
            position_param_block = ' '.join(position_param_block.split())
            try:
                thisMeasurement.name = re.search(r'(?<=MEASUREMENT )\S+', position_param_block).group().strip()
                description_start_index = re.search(r'(?<=MEASUREMENT )\S+', position_param_block).span()[1]
                # description                     = re.search('(?<= )(\".*\")', position_param_block[description_start_index:])
                # thisMeasurement.long_identifier = description.group().strip()
                # datatype_start_index            = description.span()[1]
                # thisMeasurement.datatype        = re.search('(?<= )(\w+ )',position_param_block[description_start_index+datatype_start_index:]).group().strip()
                #
                thisMeasurement.datatype = re.search(DATATYPE_PATTERN, position_param_block).group().strip()
                datatype_start_index = re.search(DATATYPE_PATTERN, position_param_block).span()[0]
                description = position_param_block[description_start_index:datatype_start_index + 1]
                thisMeasurement.long_identifier = description[description.find('"'):description.rfind('"') + 1]
                thisMeasurement.conversion = re.search(r'(?<=%s )\S+' % thisMeasurement.datatype,
                                                       position_param_block).group().strip()
            except:
                print("measurement parse error, : %s" % position_param_list)
            if keyword_param_list:
                for line in keyword_param_list:
                    line = line.strip()
                    if re.match(r"^ECU_ADDRESS .*", line):
                        thisMeasurement.ecu_address = line.split(" ")[1]
                    if re.match(r"^ECU_ADDRESS_EXTENSION .*", line):
                        thisMeasurement.ecu_address_extension = line.split(" ")[1]
                    if re.match(r"^DISPLAY_IDENTIFIER.*", line):
                        thisMeasurement.display_identifier = line.split(" ")[1]
                        if thisMeasurement.name:
                            self.display_id_map[thisMeasurement.display_identifier] = thisMeasurement.name
                    if re.match(r"^MATRIX_DIM.*", line):
                        thisMeasurement.matrix_dim = re.findall(r'\d+ +\d+ +\d+', line)[0]

        self.measurements[thisMeasurement.name] = thisMeasurement

    # These are functions used to parse a stanza
    def parseRecordLayout(self, stanza):
        position_param_list = stanza[0]
        keyword_param_list = stanza[1]
        thisRecordLayout = RecordLayout()

        position_param_block = ' '.join(position_param_list)
        position_param_block = ' '.join(position_param_block.split())
        try:
            thisRecordLayout.name = re.search(r'(?<=RECORD_LAYOUT )\w+', position_param_block).group().strip()
        except:
            print("record layout parse error, : %s" % position_param_block)

        if keyword_param_list:
            for line in keyword_param_list:
                line = line.strip()
                if re.match("FNC_VALUES", line):
                    thisRecordLayout.fnc_values.position = line.split()[1]
                    thisRecordLayout.fnc_values.datatype = line.split()[2]
                    thisRecordLayout.fnc_values.index_mode = line.split()[3]
                    thisRecordLayout.fnc_values.address_type = line.split()[4]
        self.record_layouts[thisRecordLayout.name] = thisRecordLayout

    # These are functions used to parse a stanza
    def parseCompuTab(self, stanza):
        position_param_list = stanza[0]
        keyword_param_list = stanza[1]
        position_param_block = ' '.join(position_param_list)
        position_param_block = ' '.join(position_param_block.split())
        thisCompuTab = CompuTab()
        try:
            thisCompuTab.name = re.search(r'(?<=COMPU_TAB )\w+', position_param_block).group().strip()
            description = re.search(r'(?<=%s )(\".*\")' % thisCompuTab.name, position_param_block)
            thisCompuTab.long_identifier = description.group().strip()
            start_index = description.span()[1]
            thisCompuTab.conversion_type = re.search(r'(?<= )(\w+ )',
                                                     position_param_block[start_index:]).group().strip()
            thisCompuTab.number_value_pairs = re.search(r'(?<=%s )(\w+ )' % thisCompuTab.conversion_type,
                                                        position_param_block).group().strip()
            self.compuTabs[thisCompuTab.name] = thisCompuTab
        except:
            print('Compu Tab parse error : %s' % position_param_list)

    def parseCompuVtab(self, stanza):
        position_param_list = stanza[0]
        keyword_param_list = stanza[1]
        position_param_block = ' '.join(position_param_list)
        position_param_block = ' '.join(position_param_block.split())
        thisCompuVtab = CompuVtab()
        try:
            thisCompuVtab.name = re.search(r'(?<=COMPU_VTAB )\w+', position_param_block).group().strip()
            description = re.search(r'(?<=%s )(\".*?\")' % thisCompuVtab.name, position_param_block)
            thisCompuVtab.long_identifier = description.group().strip()
            start_index = description.span()[1]
            thisCompuVtab.conversion_type = re.search(r'(?<= )(\w+ )',
                                                      position_param_block[start_index:]).group().strip()
            thisCompuVtab.number_value_pairs = re.search(r'(?<=%s )(\w+ )' % thisCompuVtab.conversion_type,
                                                         position_param_block).group().strip()

            self.compuVtabs[thisCompuVtab.name] = thisCompuVtab
        except:
            print('Compu Vtab parse error : %s' % position_param_list)

    def parseCharacteristic(self, stanza):
        position_param_list = stanza[0]
        keyword_param_list = stanza[1]
        thisCharacteristic = Characteristic()
        if self.asap2_version == '1.61':
            for sentence in position_param_list:
                if '/* Name' in sentence:
                    thisCharacteristic.name = sentence.split('*/')[-1].strip()
                elif '/* Long identifier' in sentence:
                    thisCharacteristic.long_identifier = sentence.split('*/')[-1].strip()
                elif '/* Type' in sentence:
                    thisCharacteristic.datatype = sentence.split('*/')[-1].strip()
                elif '/* ECU_ADDRESS' in sentence:
                    thisCharacteristic.datatype = sentence.split('*/')[-1].strip()
                elif '/* Record Layout' in sentence:
                    thisCharacteristic.deposit = sentence.split('*/')[-1].strip()
                elif '/* Conversion Method' in sentence:
                    thisCharacteristic.conversion = sentence.split('*/')[-1].strip()
                elif '/* Lower limit' in sentence:
                    thisCharacteristic.lower_limit = sentence.split('*/')[-1].strip()
                elif '/* Upper limit' in sentence:
                    thisCharacteristic.upper_limit = sentence.split('*/')[-1].strip()
            for line in keyword_param_list:
                line = line.strip()
                if re.match("^ECU_ADDRESS_EXTENSION .*", line):
                    thisCharacteristic.ecu_address_extension = line.split()[1]
                if re.match("^DISPLAY_IDENTIFIER.*", line):
                    thisCharacteristic.display_identifier = line.split()[1]
                    if thisCharacteristic.name:
                        self.display_id_map[thisCharacteristic.display_identifier] = thisCharacteristic.name
                if re.match("^MATRIX_DIM.*", line):
                    thisCharacteristic.matrix_dim = re.findall(r'\d+ +\d+ +\d+', line)[0]
        else:
            position_param_block = ' '.join(position_param_list)
            position_param_block = ' '.join(position_param_block.split())

            try:
                thisCharacteristic.name = re.search(r'(?<=CHARACTERISTIC )\S+', position_param_block).group().strip()
                description = re.search(r'(?<=%s )(\".*\")' % thisCharacteristic.name, position_param_block)
                if description is None:
                    description = re.search('(?<=\")(.*?)(?=\")', position_param_block)
                # description = re.search('(?<=\")(.*?)(?=\")', position_param_block)
                thisCharacteristic.long_identifier = description.group().strip()
                start_index = description.span()[1]
                # start_index = position_param_block.find('\"')
                # end_index = position_param_block[start_index+1:].find('\"')
                # thisCharacteristic.long_identifier =position_param_block[start_index+1:][:end_index]
                # start_index = start_index + len(thisCharacteristic.long_identifier)

                thisCharacteristic.type = re.search(r'(?<= )(\w+ )', position_param_block[start_index:]).group().strip()
                thisCharacteristic.ecu_address = re.search(r'(?<= %s )(\w+ )' % thisCharacteristic.type,
                                                           position_param_block).group().strip()
                thisCharacteristic.deposit = re.search(r'(?<= %s )(\w+ )' % thisCharacteristic.ecu_address,
                                                       position_param_block).group().strip()
                thisCharacteristic.max_diff = re.search(r'(?<= %s )(\S+ )' % thisCharacteristic.deposit,
                                                        position_param_block).group().strip()
                thisCharacteristic.conversion = re.search(r'(?<= %s )(\w+ )' % thisCharacteristic.max_diff,
                                                          position_param_block).group().strip()
            except:
                try:
                    ###work for canape a2l###
                    thisCharacteristic.name = re.search(r'(?<=CHARACTERISTIC )\S+',
                                                        position_param_block).group().strip()
                    thisCharacteristic.ecu_address = re.search(r'0x[0-9A-Fa-f]{2,8}', position_param_block).group()
                    thisCharacteristic.deposit = re.search(r'(?<= %s )(\w+ )' % thisCharacteristic.ecu_address,
                                                           position_param_block).group().strip()
                    thisCharacteristic.max_diff = re.search(r'(?<= %s )(\S+ )' % thisCharacteristic.deposit,
                                                            position_param_block).group().strip()
                    thisCharacteristic.conversion = re.search(r'(?<= %s )(\w+ )' % thisCharacteristic.max_diff,
                                                              position_param_block).group().strip()

                except:
                    print("characteristic parse error, : %s" % position_param_list)

            if keyword_param_list:
                for line in keyword_param_list:
                    line = line.strip()
                    if re.match("^ECU_ADDRESS_EXTENSION.*", line):
                        thisCharacteristic.ecu_address_extension = line.split(" ")[1]
                    if re.match("^DISPLAY_IDENTIFIER.*", line):
                        thisCharacteristic.display_identifier = line.split(" ")[1]
                        if thisCharacteristic.name:
                            self.display_id_map[thisCharacteristic.display_identifier] = thisCharacteristic.name
                    if re.match("^MATRIX_DIM.*", line):
                        thisCharacteristic.matrix_dim = re.findall(r'\d+ +\d+ +\d+', line)[0]
        self.characteristics[thisCharacteristic.name] = thisCharacteristic

    def parseCompuMethod(self, stanza):
        position_param_list = stanza[0]
        keyword_param_list = stanza[1]

        thisCompu = CompuMethod()
        if self.asap2_version == '1.61':
            for sentence in position_param_list:
                if '/* Name of CompuMethod' in sentence:
                    thisCompu.name = sentence.split('*/')[-1].strip()
                elif '/* Long identifier' in sentence:
                    thisCompu.long_identifier = sentence.split('*/')[-1].strip()
                elif '/* conversion Type' in sentence:
                    thisCompu.conversion_type = sentence.split('*/')[-1].strip()
                elif '/* Format' in sentence:
                    thisCompu.format = sentence.split('*/')[-1].strip()
                elif '/* Record Layout' in sentence:
                    thisCompu.deposit = sentence.split('*/')[-1].strip()
                elif '/* Coefficients' in sentence:
                    thisCompu.deposit = sentence.split('*/')[-1].strip()


        else:
            position_param_block = ' '.join(position_param_list)
            position_param_block = ' '.join(position_param_block.split())
            try:
                thisCompu.name = re.search(r'(?<=COMPU_METHOD )[\w._]+', position_param_block).group().strip()
                description = re.search(r'(?<=%s )(\".*?\")' % thisCompu.name, position_param_block)
                thisCompu.long_identifier = description.group().strip()
                start_index = description.span()[1]
                thisCompu.conversion_type = re.search(r'(?<= )(\w+ )',
                                                      position_param_block[start_index:]).group().strip()
            except:
                print("compu method parse error, : %s" % position_param_list[0:3])
            if keyword_param_list:
                for line in keyword_param_list:
                    line = line.strip()
                    if re.match("^COEFFS .*", line):
                        coeffs = re.split(r'[ .]', line.split("COEFFS ")[1])
                        thisCompu.coeffs = coeffs
                    elif re.match("^COEFFS_LINEAR .*", line):
                        coeffs_linear = re.split(r'[ .]', line.split("COEFFS_LINEAR ")[1])
                        thisCompu.coeffs_linear = coeffs_linear
                    elif re.match("^COMPU_TAB_REF.*", line):
                        compu_tab_ref = line.split("COMPU_TAB_REF ")[1]
                        thisCompu.compu_tab_ref = compu_tab_ref
        if 'Q' in thisCompu.long_identifier and \
                '=' in thisCompu.long_identifier and \
                'V' in thisCompu.long_identifier:
            thisCompu.function = thisCompu.long_identifier
        elif thisCompu.coeffs:
            thisCompu.function = str("Q = (" + coeffs[0] + "*" + "V*V +" +
                                     coeffs[1] + "*" + "V +" + coeffs[2] + ")/" +
                                     "(" + coeffs[3] + "*" + "V*V +" +
                                     coeffs[4] + "*" + "V +" + coeffs[5] + ")"
                                     )
        self.compuMethods[thisCompu.name] = thisCompu

    def parseAxis(self, stanza):

        lineNum = 0
        thisAxis = Axis()

        for line in stanza.split("\n"):
            line = line.strip()
            if lineNum == 0:
                thisAxis.name = line.split(" ")[2]
            elif lineNum == 2:
                thisAxis.ecu_address = line
            elif lineNum == 6:
                thisAxis.function = line

            lineNum += 1

        self.axesDefs[thisAxis.name] = thisAxis

    def parseXCPonCAN(self, block):
        self.XCPonCAN = XCPProtocol()
        for line in block:
            if re.search(CAN_ID_MASTER_PATTERN_WHOLE, line):
                res = re.search(CAN_ID_MASTER_PATTERN_WHOLE, line).group()
                val = re.search(CAN_ID_MASTER_PATTERN, res).group().strip()
                if val.find('0x') >= 0:
                    val = int(val, 16)
                else:
                    val = int(val)
                val = self.open_brs_val(val)
                self.XCPonCAN.CAN_ID_MASTER = val
                logger.info(f'CAN ID MASTER : {val}')
            if re.search(CAN_ID_SLAVE_PATTERN_WHOLE, line):
                res = re.search(CAN_ID_SLAVE_PATTERN_WHOLE, line).group()
                val = re.search(CAN_ID_SLAVE_PATTERN, res).group().strip()
                if val.find('0x') >= 0:
                    val = int(val, 16)
                else:
                    val = int(val)
                val = self.open_brs_val(val)
                self.XCPonCAN.CAN_ID_SLAVE = val
                logger.info(f'CAN ID SLAVE : {val}')
            if re.search(BAUDRATE_PATTERN_WHOLE, line):
                res = re.search(BAUDRATE_PATTERN_WHOLE, line).group()
                val = re.search(BAUDRATE_PATTERN, res).group().strip()
                if val.find('0x') >= 0:
                    val = int(val, 16)
                else:
                    val = int(val)
                self.XCPonCAN.BAUDRATE = val
            if re.search(SAMPLE_POINT_PATTERN_WHOLE, line):
                res = re.search(SAMPLE_POINT_PATTERN_WHOLE, line).group()
                val = re.search(SAMPLE_POINT_PATTERN, res).group().strip()
                if val.find('0x') >= 0:
                    val = int(val, 16)
                else:
                    val = int(val)
                self.XCPonCAN.SAMPLE_POINT = val

    def open_brs_val(self, val, ecu_type='XCU'):
        try:
            if ecu_type == 'EMS' or 'BCM' in ecu_type:
                if val < 0x40000000:
                    val = val + 0x40000000
                return val
            else:
                return val
        except Exception as e:
            logger.error(traceback.format_exc())
            return val

    def getXCPonEth(self, inputFile):
        ip = False
        port = False
        if 1:
            temp = []
            endStanza = True

            for line in inputFile:
                if self._vendor == '':
                    if 'XCPonUDP' in line:
                        self._vendor = 'INCA'
                    elif 'CANAPE' in line:
                        self._vendor = 'CANAPE'
                if re.match("\n", line.strip()):
                    print("Blank line")
                    continue
                elif re.match(r"^\/begin XCP_ON_UDP_IP.*", line.strip()):
                    endStanza = False
                elif re.match(r"^/end XCP_ON_UDP_IP.*", line.strip()) or re.match(r"^\/begin +\s.+", line.strip()):
                    # endStanza = True
                    break
                if endStanza is False:
                    temp.append(line.strip())

        for line in temp:
            if '/* PORT */' in line:
                port = line.split(' ')[-1]
            if 'ADDRESS ' in line:
                match = re.search(r'"(.*?)"', line)
                if match:
                    ip = match.group(1)
        if ip and port:
            return port, ip
        else:
            logger.error('A2l中未找到正确的以太网配置（ip与端口）')
            return '50000', '172.31.10.31'

    def parseMAP(self, stanza):
        lineNum = 0

        thisMap = Map3D()

        for line in stanza.split("\n"):
            line = line.strip()
            if lineNum == 0:
                thisMap.name = line.split(" ")[2]
            elif lineNum == 1:
                thisMap.description == line
            elif lineNum == 3:
                thisMap.ecu_address = line
            elif lineNum == 6:
                thisMap.function = compuMethods[line].function
            elif lineNum == 10:
                thisMap.displayFormat = line.split(" ")[1]
            elif lineNum == 13:
                thisMap.xAxisLabel = line
            elif lineNum == 14:
                thisMap.xAxisFunction = compuMethods[line].function
            elif lineNum == 19:
                thisMap.xAxisAddress = axesDefs[line.split(' ')[1]].ecu_address
            elif lineNum == 23:
                thisMap.yAxisLabel = line
            elif lineNum == 24:
                thisMap.yAxisFunction = compuMethods[line].function
            elif lineNum == 29:
                thisMap.yAxisAddress = axesDefs[line.split(' ')[1]].ecu_address

            lineNum += 1

        self.mapDefs[thisMap.name] = thisMap
        # print(vars(thisMap))

    def getXCPonCAN(self, inputFile):
        temp = []
        endStanza = True

        for line in inputFile:
            if self._vendor == '':
                if 'LIXIANG_AUTOSAR' in line:
                    self._vendor = 'INCA'
                elif 'CANAPE' in line:
                    self._vendor = 'CANAPE'
            if re.match("\n", line.strip()):
                print("Blank line")
                continue
            elif re.match(r"^\/begin XCP_ON_CAN.*", line.strip()):
                endStanza = False
            elif re.match(r"^/end XCP_ON_CAN.*", line.strip()) or re.match(r"^\/begin +\s.+", line.strip()):
                endStanza = True
                break
            if endStanza is False:
                temp.append(line)
        if temp != "":
            self.parseXCPonCAN(temp)  ##TODO
            temp = []

    def getMeasurements(self, inputFile):
        stanza = ""
        endStanza = True

        for line in inputFile:
            if self._vendor == '':
                if 'LIXIANG_AUTOSAR' in line:
                    self._vendor = 'INCA'
                elif 'CANAPE' in line:
                    self._vendor = 'CANAPE'
            if not self.asap2_version:
                if "ASAP2_VERSION" in line:
                    temp_1 = line.replace('ASAP2_VERSION', '').strip()
                    temp_2 = temp_1.split(' ')
                    self.asap2_version = '.'.join(temp_2)
                elif "/begin" in line:
                    self.asap2_version = '1.60'

            if re.match("\n", line.strip()):
                print("Blank line")
                continue
            elif re.match(r"^\/begin MEASUREMENT.*", line.strip()):
                endStanza = False
            elif re.match(r"^/end MEASUREMENT.*", line.strip()):
                endStanza = True
                stanza += line

            if endStanza is False:
                stanza += line

            else:
                if stanza != "":
                    block = self.stanza_split(stanza, MEASUREMENT_OPTIONAL_PARAMETERS)
                    self.parseMeasurement(block)
                    stanza = ""

    def getCharacteristics(self, inputFile):
        stanza = ""
        endStanza = True

        for line in inputFile:
            if re.match(r"\n", line.strip()):
                print("Blank line")
                continue
            elif re.match(r"^\/begin CHARACTERISTIC.*", line.strip()):
                endStanza = False
            elif re.match(r"^/end CHARACTERISTIC.*", line.strip()):
                endStanza = True
                stanza += line

            if endStanza is False:
                stanza += line

            else:
                if stanza != "":
                    block = self.stanza_split(stanza, CHARACTERISTIC_OPTIONAL_PARAMETERS)
                    self.parseCharacteristic(block)
                    stanza = ""

    def getRecordLayouts(self, inputFile):
        stanza = ""
        endStanza = True

        for line in inputFile:
            if re.match("\n", line.strip()):
                print("Blank line")
                continue
            elif re.match(r"^\/begin RECORD_LAYOUT.*", line.strip()):
                endStanza = False
            elif re.match(r"^/end +RECORD_LAYOUT.*", line.strip()):
                endStanza = True
                stanza += line

            if endStanza is False:
                stanza += line

            else:
                if stanza != "":
                    block = self.stanza_split(stanza, RECORD_LAYOUT_OPTIONAL_PARAMETERS)
                    self.parseRecordLayout(block)
                    stanza = ""

    def getCompuMethods(self, inputFile):
        stanza = ""
        endStanza = True
        index = 0
        for line in inputFile:
            # index = index +1
            # if index == 673028:
            #     a = 1
            if re.match("\n", line.strip()):
                print("Blank line")
                continue
            elif re.match(r"^\/begin +COMPU_METHOD.*", line.strip()):
                endStanza = False
            elif re.match(r"^/end COMPU_METHOD.*", line.strip()):
                endStanza = True
                stanza += line

            if endStanza is False:
                stanza += line

            else:
                if stanza != "":
                    block = self.stanza_split(stanza, COMPU_METHOD_OPTIONAL_PARAMETERS)
                    try:
                        self.parseCompuMethod(block)
                        stanza = ""
                    except Exception as e:
                        # print(traceback.format_exc())
                        print(f'error stanza : {stanza}')
                        stanza = ""

    def getCompuTab(self, inputFile):
        stanza = ""
        endStanza = True
        for line in inputFile:
            if re.match("\n", line.strip()):
                print("Blank line")
                continue
            elif re.match(r"^\/begin COMPU_TAB.*", line.strip()):
                endStanza = False
            elif re.match(r"^/end COMPU_TAB.*", line.strip()):
                endStanza = True
                stanza += line

            if endStanza is False:
                stanza += line

            else:
                if stanza != "":
                    block = self.stanza_split(stanza, COMPU_TAB_OPTIONAL_PARAMETERS)
                    self.parseCompuTab(block)  ## TODO
                    stanza = ""

    def getDescriptor(self, inputFile, descriptors: list):
        stanza = ""
        endStanza = True
        startStanza = False
        pattern = '|'.join(descriptors)
        for line in inputFile:
            if re.match("\n", line.strip()):
                print("Blank line")
                continue
            # elif re.search("^/begin (%s)"%pattern, line.strip()):
            elif re.search("^/begin( )+(%s)" % pattern, line.strip()):
                endStanza = False
                startStanza = True
                descriptor = re.search("^/begin( )+(%s)" % pattern, line.strip()).group().split()[1]
            elif re.match("^/end( )+(%s)" % pattern, line.strip()):
                endStanza = True
                startStanza = False
                stanza += line

            if endStanza is False:
                stanza += line

            else:
                if stanza != "":
                    if descriptor == 'COMPU_TAB':
                        block = self.stanza_split(stanza, COMPU_TAB_OPTIONAL_PARAMETERS)
                        self.parseCompuTab(block)  ## TODO
                    elif descriptor == 'COMPU_METHOD':
                        block = self.stanza_split(stanza, COMPU_METHOD_OPTIONAL_PARAMETERS)
                        self.parseCompuMethod(block)
                    elif descriptor == 'COMPU_VTAB':
                        block = self.stanza_split(stanza, COMPU_VTAB_OPTIONAL_PARAMETERS)
                        self.parseCompuVtab(block)  ##TODO
                    elif descriptor == 'MEASUREMENT':
                        block = self.stanza_split(stanza, MEASUREMENT_OPTIONAL_PARAMETERS)
                        self.parseMeasurement(block)
                    elif descriptor == 'CHARACTERISTIC':
                        block = self.stanza_split(stanza, CHARACTERISTIC_OPTIONAL_PARAMETERS)
                        self.parseCharacteristic(block)
                    elif descriptor == 'RECORD_LAYOUT':
                        block = self.stanza_split(stanza, RECORD_LAYOUT_OPTIONAL_PARAMETERS)
                        self.parseRecordLayout(block)
                stanza = ""

    def getAxisDefinitions(self, inputFile):
        stanza = ""
        endStanza = True

        for line in inputFile:
            if re.match("\n", line.strip()):
                print("Blank line")
                continue
            elif re.match(r"^\/begin AXIS_PTS .*", line.strip()):
                endStanza = False
            elif re.match("^/end AXIS_PTS.*", line.strip()):
                endStanza = True
                stanza += line

            if endStanza is False:
                stanza += line

            else:
                if stanza != "":
                    self.parseAxis(stanza)
                    stanza = ""

    def getMapDefinitions(self, inputFile):
        stanza = ""
        endStanza = True

        for line in inputFile:
            if re.match("\n", line.strip()):
                print("Blank line")
                continue
            elif re.match(r"^\/begin CHARACTERISTIC.*", line.strip()):
                endStanza = False
            elif re.match(r"^/end CHARACTERISTIC.*", line.strip()):
                endStanza = True
                stanza += line

            if endStanza is False:
                stanza += line

            else:
                if stanza != "":
                    self.parseMAP(stanza)
                    stanza = ""

    def get_protocol_layer(self, inputFile):
        temp = []
        timeout_list = []
        endStanza = True
        for line in inputFile:
            if re.match("\n", line.strip()):
                print("Blank line")
                continue
            elif re.match(r"^/begin PROTOCOL_LAYER.*", line.strip()):
                endStanza = False
            elif re.match(r"^/end PROTOCOL_LAYER", line.strip()) or re.match(r"^\/end +\s.+", line.strip()):
                endStanza = True
                break
            if endStanza is False:
                temp.append(line)
        if temp != "":
            if len(temp) > 9:
                for i in range(2, 9):
                    match = re.search(r'0[xX][0-9a-fA-F]+|\d+', temp[i])
                    if match:
                        number_str = match.group()
                        if number_str.startswith(('0x', '0X')):
                            number = int(number_str, 16)  # 转换十六进制数为整数
                        else:
                            number = int(number_str)  # 转换十进制数为整数
                        timeout_list.append(number)
                    else:
                        timeout_list.append(0)
                        logger.error("XCP超时时间解析失败")
        self.timeout_list = timeout_list
        temp = []

    # biaojixcp
    def parse_a2l(self, a2l_path):
        with open(a2l_path, 'r', encoding="iso-8859-1") as inputFile:
            self.get_protocol_layer(inputFile)
        with open(a2l_path, 'r', encoding="iso-8859-1") as inputFile:
            self.getMeasurements(inputFile)
        with open(a2l_path, 'r', encoding="iso-8859-1") as inputFile:
            self.getCharacteristics(inputFile)
        with open(a2l_path, 'r', encoding="iso-8859-1") as inputFile:
            self.getCompuMethods(inputFile)
        with open(a2l_path, 'r', encoding="iso-8859-1") as inputFile:
            self.getRecordLayouts(inputFile)
        with open(a2l_path, 'r', encoding="iso-8859-1") as inputFile:
            self.getXCPonCAN(inputFile)


class CalOnEth:
    def __init__(self, a2l_path: str):
        self.record_layouts = None
        self.compu_method = None
        self.calibrate_values = None
        self.measurements = None
        self.parsed_a2l = None
        self.is_xcp_connected = False
        self.ip = None
        self.port = None
        self.is_a2l_loaded = False
        self.a2l = a2l_path
        self.pyxcp_config_file = os.path.join(work_dir, 'data', 'conf', 'conf_eth.toml')
        self.config = {
            "TRANSPORT": "ETH",
            "HOST": '',
            "PORT": int(0),
            "PROTOCOL": "UDP",
            "IPV6": False,
            "CREATE_DAQ_TIMESTAMPS": False,
            'DISABLE_ERROR_HANDLING': True,
            'TIMEOUT': 0.15
        }
        # super().__init__(transportName, config)
        self.master = None
        self.reg_signals()
        # print(self.master.config)

    def reg_signals(self):
        """
        用户搜索时下拉补全，仅提示用
        """
        Variable('cal_').Value = ''
        Variable('cal_write_').Value = ''
        Variable('cal_read').Value = ''

    def load_a2l(self):
        """
        依据输入的A2l文件地址进行解析，获得观测量、标定量、计算方法、数据记录、总线配置等参数
        :param a2l_path:
        :return:
        """
        try:
            filename = self.a2l
            a2lparsed = A2LParser()
            with open(filename, 'r', encoding="iso-8859-1") as inputFile:
                self.port, self.ip = a2lparsed.getXCPonEth(inputFile)
            with open(filename, 'r', encoding="iso-8859-1") as inputFile:
                a2lparsed.getMeasurements(inputFile)
            with open(filename, 'r', encoding="iso-8859-1") as inputFile:
                a2lparsed.getCharacteristics(inputFile)
            with open(filename, 'r', encoding="iso-8859-1") as inputFile:
                a2lparsed.getCompuMethods(inputFile)
            with open(filename, 'r', encoding="iso-8859-1") as inputFile:
                a2lparsed.getRecordLayouts(inputFile)

            self.config['HOST'] = self.ip
            self.config['PORT'] = int(self.port)
            self.parsed_a2l = a2lparsed
            self.measurements = self.parsed_a2l.measurements
            self.calibrate_values = self.parsed_a2l.characteristics
            self.record_layouts = self.parsed_a2l.record_layouts
            self.compu_method = self.parsed_a2l.compuMethods
            # self.master = Master('eth', self.config)
            original_argv = sys.argv.copy()
            # pyxcp_config = os.path.join(ENV.working_directory,'utilities','configs','conf_eth.toml')
            sys.argv = [original_argv[0], "-c", self.pyxcp_config_file]
            self.master = ArgumentParser(description='polling').run(policy=None)
            sys.argv = original_argv
            self.is_a2l_loaded = True
            # 添加标定量:
            # for c, v in self.calibrate_values.items():
            #     Variable(f'cal_{c}').Value = 0
            #     Variable(f'cal_write_{c}').Value = 0
            # 添加观测量
            # Variable('cal_read').Value = 0
            # for m, v in self.measurements.items():
            #     Variable(f'cal_{m}').Value = 0
        except:
            logger.error(f'A2L解析失败，master启动失败')
            logger.error(traceback.format_exc())
        else:
            logger.info(f'A2L解析完成，标定目标地址: {self.ip}, 端口: {self.port}')

    def bytes_to_data(self, datatype, data):
        # logger.info(f'debug------输入的数据类型为{datatype},字节串内容为{data}')
        try:
            if datatype == 'UBYTE':
                bytes = struct.pack('B', data[0])
                result = struct.unpack('<B', bytes)[0]
                return result
            if datatype == 'SBYTE':
                bytes = struct.pack('B', data[0])
                result = struct.unpack('<b', bytes)[0]
                return result
            if datatype == 'UWORD':
                bytes = struct.pack('2B', data[0], data[1])
                result = struct.unpack('<H', bytes)[0]
                return result
            if datatype == 'SWORD':
                bytes = struct.pack('2B', data[0], data[1])
                result = struct.unpack('<h', bytes)[0]
                return result
            if datatype == 'ULONG':
                bytes = struct.pack('4B', data[0], data[1], data[2], data[3])
                result = struct.unpack('<L', bytes)[0]
                return result
            if datatype == 'SLONG':
                bytes = struct.pack('4B', data[0], data[1], data[2], data[3])
                result = struct.unpack('<l', bytes)[0]
                return result
            if datatype == 'A_UINT64':
                bytes = struct.pack('8B', data[0], data[1], data[2], data[3],
                                    data[4], data[5], data[6], data[7])
                result = struct.unpack('<Q', bytes)[0]
                return result
            if datatype == 'A_INT64':
                bytes = struct.pack('8B', data[0], data[1], data[2], data[3],
                                    data[4], data[5], data[6], data[7])
                result = struct.unpack('<q', bytes)[0]
                return result
            if datatype == 'FLOAT32_IEEE':
                bytes = struct.pack('4B', data[0], data[1], data[2], data[3])
                result = struct.unpack('<f', bytes)[0]
                return result
            if datatype == 'FLOAT64_IEEE':
                bytes = struct.pack('8B', data[0], data[1], data[2], data[3],
                                    data[4], data[5], data[6], data[7])
                result = struct.unpack('<d', bytes)[0]
                return result
        except Exception as e:
            logger.info(f'read variable error in byte converting')
            logger.info(f'byte data {data}, datatype {datatype}')
            logger.info(f'error: {e}')
            logger.error(traceback.format_exc())
            return None

    def data_to_bytes(self, datatype, data):
        # print(datatype)
        if datatype == 'UBYTE':
            x = struct.pack('<B', data)
            bytes = struct.unpack('B', x)
            return bytearray(bytes)
        if datatype == 'SBYTE':
            x = struct.pack('<b', data)
            bytes = struct.unpack('B', x)
            return bytearray(bytes)
        if datatype == 'UWORD':
            x = struct.pack('<H', data)
            bytes = struct.unpack('2B', x)
            return bytearray(bytes)
        if datatype == 'SWORD':
            x = struct.pack('<h', data)
            bytes = struct.unpack('2B', x)
            return bytearray(bytes)
        if datatype == 'ULONG':
            x = struct.pack('<L', data)
            bytes = struct.unpack('4B', x)
            return bytearray(bytes)
        if datatype == 'SLONG':
            x = struct.pack('<l', data)
            bytes = struct.unpack('4B', x)
            return bytes
        if datatype == 'A_UINT64':
            x = struct.pack('<Q', data)
            bytes = struct.unpack('8B', x)
            return bytearray(bytes)
        if datatype == 'A_INT64':
            x = struct.pack('<q', data)
            bytes = struct.unpack('8B', x)
            return bytearray(bytes)
        if datatype == 'FLOAT32_IEEE':
            x = struct.pack('<f', data)
            bytes = struct.unpack('4B', x)
            return bytearray(bytes)
        if datatype == 'FLOAT64_IEEE':
            x = struct.pack('<d', data)
            bytes = struct.unpack('8B', x)
            return bytearray(bytes)

    def solve(self, eq, var='V'):
        """
        用于对数据进行解析,用于解析虚数方程
        :param eq:
        :param var:
        :return:
        """
        eq1 = eq.replace('=', '-(') + ")"
        c = eval(eq1, {var: 1j})
        return -c.real / c.imag

    def get_variable_info_from_tmp(self, var_name, var_info):
        """
        get the variable information from the tmp
        :param var_name: name of the variable
        :param var_info:
        :return:
        """
        signal_matched = False
        variable_type = 'measurement'
        if variable_type == 'measurement':
            for signal_group, signal_group_info in var_info['McoreSignalInfo'].items():
                for signal_name, signal_info in signal_group_info.items():
                    if signal_name == var_name:
                        signal_matched = True
                        break
                if signal_matched:
                    break
            if not signal_matched:
                logger.error(f"The signal of {var_name} is none.")
                return False, None
            if not signal_info['ecuAddress']:
                logger.error(f"The ecu address of {var_name} is none.")
                return False, None
            address = int(signal_info['ecuAddress'], 16)
            if 'ecuAddressExtension' not in signal_info:
                ecu_address_extension = c_ubyte(0x00)
            else:
                ecu_address_extension = c_ubyte(int(signal_info['ecuAddressExtension'], 16))
            datatype = signal_info['datatype']
            if 'matrix_dim' in signal_info:
                matrix_dim = signal_info['matrix_dim']
            else:
                matrix_dim = '1 1 1'

            dataSize = DataSize[datatype]
            conversion = signal_info['conversion']

            if conversion == 'NO_COMPU_METHOD':
                compu_method_Q = None
            else:
                compu_method_Q = var_info['ASAP2Info']['compu_methods'][conversion]['function']

            if not compu_method_Q:
                compu_method_Q = "Q=V"
            if compu_method_Q:
                try:
                    compu_method_Q = compu_method_Q.encode('unicode-escape').decode('string_escape')
                except:
                    pass
                compu_method_Q = compu_method_Q.replace('"', '')
                compu_method_V = compu_method_Q[compu_method_Q.find('Q') + 1:]
        self.ecu_address_extension = ecu_address_extension
        self.address = address
        self.dataSize = dataSize
        self.datatype = datatype
        self.compu_method_Q = compu_method_Q
        self.compu_method_V = compu_method_V
        self.variable_type = variable_type
        self.matrix_dim = matrix_dim
        return True, None

    def get_variable_info(self, var_name):
        """
        通过从用例中读取的xcp变量名确定其具体属性（读写性质、raw_data计算方法）
        :param var_name: 变量名称
        :return: bool, 表示是否解析成功
        """
        if var_name not in self.measurements and var_name not in self.calibrate_values:
            var_name = self.parsed_a2l.display_id_map[var_name]

        if var_name in self.measurements:
            # TODO Measurement
            measurement = self.measurements[var_name]
            if not measurement.ecu_address:
                print(f"The ecu address of {var_name} is none.")
                return False, None
            address = measurement.ecu_address
            if not measurement.ecu_address_extension:
                ecu_address_extension = 0x00
            else:
                ecu_address_extension = int(measurement.ecu_address_extension, 16)
            datatype = measurement.datatype
            matrix_dim = measurement.matrix_dim
            dataSize = DataSize[datatype]

            # XL 20171224 FOR MCU A2L modification
            conversion = measurement.conversion
            # logger.info(conversion)
            if conversion == 'NO_COMPU_METHOD':
                compu_method_Q = None
            else:
                compu_method_Q = self.compu_method[conversion].function
                # print 'type', type(compu_method.Name), compu_method.Name
                # print 'type', type(compu_method.LongIdentifier), compu_method.LongIdentifier
            if not compu_method_Q:
                compu_method_Q = "Q=V"
            if compu_method_Q:
                try:
                    compu_method_Q = compu_method_Q.encode('unicode-escape').decode('string_escape')
                except:
                    pass
                compu_method_Q = compu_method_Q.replace('"', '')
                compu_method_V = compu_method_Q[compu_method_Q.find('Q') + 1:]
            variable_type = 'measurement'

        elif var_name in self.calibrate_values:
            # TODO Characteristic
            characteristic = self.calibrate_values[var_name]
            # XL 20171224 FOR MCU A2L modification
            conversion = characteristic.conversion
            matrix_dim = characteristic.matrix_dim
            if conversion == 'NO_COMPU_METHOD':
                compu_method_Q = None
            else:
                compu_method_Q = self.compu_method[conversion].function
            if not compu_method_Q:
                compu_method_Q = "Q=V"
            if compu_method_Q:
                try:
                    compu_method_Q = compu_method_Q.encode('unicode-escape').decode('string_escape')
                except:
                    pass
                compu_method_Q = compu_method_Q.replace('"', '')
                compu_method_V = compu_method_Q[compu_method_Q.find('Q') + 1:]

            # XL 20171224 FOR MCU A2L modification
            if not characteristic.ecu_address:
                print(f"The ecu address of {var_name} is none.")
                return False, None
            address = characteristic.ecu_address
            if not characteristic.ecu_address_extension:
                ecu_address_extension = 0x00
            else:
                ecu_address_extension = int(characteristic.ecu_address_extension, 16)
            if not characteristic.deposit:  ## TODO
                print(f"The data type of {var_name} is none.")
                return False, None
            record_layout = characteristic.deposit
            datatype = self.record_layouts[record_layout].fnc_values.datatype
            dataSize = DataSize[datatype]
            variable_type = 'characteristic'
        else:
            return False, None
        self.ecu_address_extension = ecu_address_extension
        self.address = int(address, 16)
        self.dataSize = dataSize
        self.datatype = datatype
        self.compu_method_Q = compu_method_Q
        self.compu_method_V = compu_method_V
        self.variable_type = variable_type
        self.matrix_dim = matrix_dim
        return True, None

    def xcpSafeUnlock(self):
        try:
            data = (c_ubyte * 6)(0, 170, 85, 0, 0, 0)
            res = self.master.userCmd(int(255), data)
        except Exception as e:
            logger.error(f'calibration key open failed')
            logger.error(traceback.format_exc())

    def connect(self):
        if not self.is_xcp_connected:
            try:
                self.master.connect()
                self.xcpSafeUnlock()
            except Exception as e:
                try:
                    self.master.disconnect()
                except types.XcpTimeoutError:
                    self.is_xcp_connected = False
                else:
                    try:
                        self.master.connect()
                        self.xcpSafeUnlock()
                    except Exception:
                        self.is_xcp_connected = False
                    else:
                        self.is_xcp_connected = True
            else:
                self.is_xcp_connected = True

    def disconnect(self):
        if self.is_xcp_connected:
            try:
                self.master.disconnect()
            except Exception as e:
                logger.error(f'disconnect 错误出现 {e}')
            else:
                self.is_xcp_connected = False

    def close(self):
        self.master.close()
        self.master = None

    def get_value_by_name(self, var_name, var_info_from_tmp=None):
        """
        通过变量名称获得其在从机中的值
        :param var_name: xcp变量名
        :param var_info_from_tmp:
        :return:
        """
        self.connect()
        if not self.is_xcp_connected:
            logger.error(f"XCP 连接失败，请检查{self.ip}:{self.port}配置.")
            return False
        try:
            # XL 20171224 FOR MCU A2L modification
            if var_info_from_tmp:
                self.get_variable_info_from_tmp(var_name, var_info_from_tmp)
            else:
                self.get_variable_info(var_name)
            # print('初始化后的xcp状态{}, 读取的信号内容{}'.format(self.is_xcp_connected, var_name))
            matrix_dim = self.matrix_dim
            matrix_dim_list = matrix_dim.split(' ')
            if matrix_dim_list[0] == '':
                matrix_dim_list = [1]
            var_value = []
            # logger.info(f"matrix_dim_list:{matrix_dim_list}")
            for index in range(int(matrix_dim_list[0])):
                # logger.info(f"reading variable index:{index}")
                address = self.address + index * self.dataSize
                res = self.get_value_by_address(address)
                logger.info(f"读取观测量: {var_name} = {res}, index: {index}")
                var_value.append(res)

            if len(var_value) == 1:
                Variable(f'cal_{var_name}').Value = var_value[0]
                # 这一步特别的重要！！！
                # 自动化测试需要根据条件表达式比较值，遇到 v[1] = 2的情况需要特殊处理，将v变量赋值
                m = re.fullmatch(r'([a-zA-Z_][\w\.]*)\[(\d+)\]', var_name)
                if m:
                    n, idx = m.group(1), int(m.group(2))
                    v_name = f'cal_{n}'
                    if not Variable.check_existence(v_name):
                        Variable(v_name).Value = {}
                    v = Variable(v_name).Value
                    v[idx] = var_value[0]
                    Variable(v_name).Value = v
            else:
                Variable(f'cal_{var_name}').Value = var_value
        finally:
            self.disconnect()

    def get_value_by_address(self, address):
        if self.variable_type == 'characteristic':  # 对标定量的观测方式
            try:
                self.master.setMta(address)
            except Exception as e:
                logger.error("XCP SetMemoryTransferAddress Error.", '{}'.format(e))
            # Retrieves a block of data starting at the current MTA0.
            try:
                res = self.master.upload(self.dataSize)
            except Exception as e:
                logger.error("XCP upload Error.", '{}'.format(e))
        else:  # 对观测量的观测方式
            try:
                res = self.master.shortUpload(self.dataSize, address)
                # logger.info(f"self.dataSize, {self.dataSize} ---self.address:{self.address}, res {res}")
            except Exception as e:
                logger.error("XCP shortupload Error.")
                logger.error(traceback.format_exc())
                # logger.info(f"self.dataSize, {self.dataSize}, type:{type(self.dataSize)}---self.address:{self.address}, type:{type(self.address)}")
                return ''

        # XL 20171224 FOR MCU A2L modification
        if self.compu_method_Q is not None:
            Q = self.bytes_to_data(self.datatype, res)
            # exec("QQQ= self.solve('"+str(Q)+ compu_method_V +"','V')")
            if Q is not None:
                QQQ = self.solve('%f' % Q + self.compu_method_V, 'V')
            else:
                return ''
        else:
            QQQ = self.bytes_to_data(self.datatype, res)
            if QQQ is None:
                return ''
        return QQQ

    def calibrate_value_by_name(self, var_name, calibrate_value):
        self.connect()
        if not self.is_xcp_connected:
            logger.error(f"XCP 连接失败，请检查{self.ip}:{self.port}配置.")
            return False
        try:
            if var_name in self.calibrate_values:  # 如果变量是可标定的
                characteristic = self.calibrate_values[var_name]
                # XL 20171224 FOR MCU A2L modification
                conversion = characteristic.conversion
                if conversion == 'NO_COMPU_METHOD':
                    compu_method = None
                else:
                    compu_method = self.compu_method[conversion].function
                # logger.info(compu_method)
                if compu_method:
                    try:
                        # compu_method = compu_method.encode('unicode-escape').decode('string_escape')
                        compu_method = compu_method.replace('"', '')
                        compu_method_left = compu_method[:compu_method.find('V')]
                        compu_method_right = compu_method[compu_method.find('V') + 1:]
                        v = calibrate_value
                        # exec ("QQQ= self.master.solve('" + compu_method_left + str(V) + compu_method_right + "','Q')")
                        QQQ = self.solve(compu_method_left + '%f' % v + compu_method_right, 'Q')
                        calibrate_value = QQQ if QQQ != -0.0 else 0
                    except:
                        logger.error(traceback.format_exc())
                else:
                    pass

                # XL 20171224 FOR MCU A2L modificati
                if not characteristic.ecu_address:
                    logger.warning(f"The ecu address of {var_name} is none.")
                    return False
                # 提取被写入数据的格属性
                record_layout = characteristic.deposit
                datatype = self.record_layouts[record_layout].fnc_values.datatype
                if datatype != 'FLOAT32_IEEE' and datatype != 'FLOAT64_IEEE':
                    calibrate_value = int(calibrate_value)
                data = self.data_to_bytes(datatype, calibrate_value)
                try:
                    # 标定前指定标定页
                    self.master.setCalPage(3, 0, 1)
                except Exception as e:
                    logger.error(f"XCP SetMemoryTransferAddress Error：{e}")
                    return False

                try:
                    self.master.setMta(int(characteristic.ecu_address, 16))
                    self.master.download(data)
                    logger.info(f'写入标定量: {var_name} = {calibrate_value}')
                except Exception as e:
                    logger.error(f"XCP Download Error.{e} ")
                    return False
                else:
                    # logger.info(f'{var_name}标定为{calibrate_value}完成')
                    return True
            else:
                logger.warning(f'变量 {var_name}不是标定量，请仔细检查')
        finally:
            self.disconnect()

    def send_msg(self, signal: Variable):
        # 读观测量
        if signal.name == 'cal_read':
            self.get_value_by_name(signal.Value)

        # 写标定量
        elif signal.name.startswith('cal_write_'):
            self.calibrate_value_by_name(signal.name[10:], signal.Value)


class XCPConnector(threading.Thread, CalOnEth):
    def __init__(self, *args, **kwargs):
        threading.Thread.__init__(self)
        CalOnEth.__init__(self, *args, **kwargs)
        self.exit_event = threading.Event()

    def run(self):
        while not self.exit_event.is_set():
            time.sleep(2)
        self.close()
        logger.info('XCP Connector线程退出')

    def stop(self):
        self.exit_event.set()


if __name__ == '__main__':
    import time
    t = time.perf_counter()
    cal = XCPConnector(r"D:\likun3\Downloads\XCU_M_XAP3.3.4-release-SW05EB-ID0000-CAL00-BSW180701.20250417-1028_ETH.a2l")
    cal.start()
    cal.load_a2l()
    print(time.perf_counter() - t)
    # cal.get_value_by_name('VeCFG_ErrorCfgDTC_enum')
    # cal.calibrate_value_by_name('VeCFG_ErrorCfgDTC_enum', 2)
    signal = Variable('cal_read')
    signal.Value = 'CalSignalData.calibSignals.KeVCS_DrvMdOvrdValue_enum'
    cal.send_msg(signal)

    signal = Variable('cal_write_CalSignalData.calibSignals.KeVCS_DrvMdOvrdValue_enum')
    signal.Value = 0
    cal.send_msg(signal)

    signal = Variable('cal_read')
    cal.send_msg(signal)
    cal.stop()
