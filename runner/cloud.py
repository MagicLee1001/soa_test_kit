# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2024/10/23 10:09
# @File    : cloud.py

import asyncio
import aiohttp
import os.path
import requests
import json
import traceback
import requests
from datetime import datetime, timedelta
from urllib.parse import urljoin
from runner.variable import Variable
from settings import env, work_dir
from runner.log import logger


class Cloud:
    @classmethod
    async def async_request(cls, session, method, url, **kwargs):
        """Common async request handler."""
        try:
            async with session.request(method, url, **kwargs) as response:
                response.raise_for_status()
                return cls._parse_response(await response.text(), response.headers.get('Content-Type', ''))
        except Exception as e:
            logger.error(traceback.format_exc())
            return None

    @classmethod
    def sync_request(cls, method, url, **kwargs):
        """Common sync request handler."""
        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return cls._parse_response(response.text, response.headers.get('Content-Type', ''))
        except requests.RequestException as e:
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def _parse_response(response_text, content_type):
        """Parse response based on content type."""
        if 'application/json' in content_type:
            return json.loads(response_text)
        elif 'text/plain' in content_type:
            return response_text
        else:
            raise ValueError(f"Unsupported content type: {content_type}")


class SlipControl(Cloud):
    def __init__(self):
        self.host = 'https://bsp-dcl-service-test.chehejia.com'
        self.headers = {
            'Content-Type': 'application/json'
        }
        # 1:车端信号上报查询; 2: job下发查询
        Variable('httpReq_SlipControl').Value = 0

        # 车端上报数据
        Variable('httpResp_SlipControl_UploadData').Value = {}
        Variable('bsp_SPID_AB_Inner').Value = ''
        Variable('bsp_SPLat_AB_Inner').Value = ''
        Variable('bsp_SPLon_AB_Inner').Value = ''
        Variable('bsp_SPSta_AB_Inner').Value = ''
        Variable('bsp_SPAdh_AB_Inner').Value = ''
        Variable('bsp_VehSlipTime_AB_Inner').Value = ''
        Variable('bsp_SlipPreCtrlSta_AB_Inner').Value = ''
        Variable('bsp_SlipUploadData_createTime').Value = ''

        # 云端指令下发
        Variable('httpResp_SlipControl_JobData').Value = {}
        Variable('bsp_SlipJobData_createTime').Value = ''
        Variable('bsp_SlipPoints').Value = {}
        Variable('bsp_SlipPointsNum').Value = 0

    async def get_upload_data(self, page_num, page_size, vin):
        url, json_data = self._prepare_request_data(page_num, page_size, vin, topic="Topic_SlipPointUpload")
        async with aiohttp.ClientSession() as session:
            resp_json = await self.async_request(session, 'POST', url, headers=self.headers, json=json_data)
            self._handle_upload_data_response(resp_json)

    def sync_get_upload_data(self, page_num, page_size, vin):
        url, json_data = self._prepare_request_data(page_num, page_size, vin, topic="Topic_SlipPointUpload")
        resp_json = self.sync_request('POST', url, headers=self.headers, json=json_data)
        self._handle_upload_data_response(resp_json)

    async def get_job_data(self, page_num, page_size, vin):
        url, json_data = self._prepare_request_data(page_num, page_size, vin, cmd_key="dcl_joblist_slip_point_request")
        async with aiohttp.ClientSession() as session:
            resp_json = await self.async_request(session, 'POST', url, headers=self.headers, json=json_data)
            await self._handle_job_data_response(session, resp_json)  # 使用 await 而非 asyncio.run

    def sync_get_job_data(self, page_num, page_size, vin):
        url, json_data = self._prepare_request_data(page_num, page_size, vin,
                                                    cmd_key="dcl_joblist_slip_point_request")
        resp_json = self.sync_request('POST', url, headers=self.headers, json=json_data)
        self._handle_job_data_response_sync(resp_json)

    def _prepare_request_data(self, page_num, page_size, vin, topic=None, cmd_key=None):
        """Prepare URL and JSON data for request."""
        if topic:
            url = urljoin(self.host, '/api/v1/vehicle/upload-data/page')
            json_data = {
                "pageNo": page_num,
                "pageSize": page_size,
                "param": {"vin": vin, "topic": topic}
            }
        elif cmd_key:
            url = urljoin(self.host, '/api/v1/cloud/send-cmd/page')
            json_data = {
                "pageNo": page_num,
                "pageSize": page_size,
                "param": {"vin": vin, "cmdKey": cmd_key}
            }
        else:
            raise ValueError("Either topic or cmd_key must be provided")
        return url, json_data

    @classmethod
    def _handle_upload_data_response(cls, resp_json):
        """Process upload data response."""
        logger.info(f'打滑预控车端上报数据记录:\n{resp_json}')
        if resp_json:
            Variable('httpResp_SlipControl_UploadData').Value = resp_json
            records = resp_json.get('data').get('records')
            if records:
                record = resp_json.get('data').get('records')[0]
                Variable('bsp_SlipUploadData_createTime').Value = record.get('createTime')
                signals = json.loads(record.get('signals'))
                for signal in signals:
                    signal_name = 'bsp_' + signal.get('name')
                    Variable(signal_name).Value = signal.get('value')

    async def _handle_job_data_response(self, session, resp_json):
        """Process job data response because additional decoding is required."""
        async def decode_base64(data):
            """Send another async request to decode base64 data."""
            url = urljoin(self.host, '/api/v1/cloud/send-cmd/base64/decode')
            headers = {'Content-Type': 'text/plain'}
            decoded_data = await self.async_request(session, 'POST', url, headers=headers, data=data)
            return decoded_data

        if resp_json:
            Variable('httpResp_SlipControl_JobData').Value = resp_json
            record = resp_json.get('data').get('records')[0]
            logger.info(f'打滑预控云端指令下发记录: \n{record}')
            Variable('bsp_SlipJobData_createTime').Value = record.get('createTime')
            slip_points_code = json.loads(record.get('cmdData')).get('result').get('cmdData').get('Topic_SlipPreControl.message')

            # Decode slip points data asynchronously
            slip_points = await decode_base64(slip_points_code)  # 使用 await 调用协程
            logger.info(f'打滑预控云端指令下发记录解析: {slip_points}')
            Variable('bsp_SlipPoints').Value = slip_points
            Variable('bsp_SlipPointsNum').Value = len(json.loads(slip_points).get('slipPoints', []))

    def _handle_job_data_response_sync(self, resp_json):
        """Process job data response synchronously."""
        def decode_base64_sync(data):
            """Send another sync request to decode base64 data."""
            url = urljoin(self.host, '/api/v1/cloud/send-cmd/base64/decode')
            headers = {'Content-Type': 'text/plain'}
            return self.sync_request('POST', url, headers=headers, data=data)

        if resp_json:
            Variable('httpResp_SlipControl_JobData').Value = resp_json
            record = resp_json.get('data').get('records')[0]
            logger.info(f'打滑预控云端指令下发记录: \n{record}')
            Variable('bsp_SlipJobData_createTime').Value = record.get('createTime')
            slip_points_code = json.loads(record.get('cmdData')).get('result').get('cmdData').get('Topic_SlipPreControl.message')

            # Decode slip points data
            slip_points = decode_base64_sync(slip_points_code)
            logger.info(f'打滑预控云端指令下发记录解析: {slip_points}')
            Variable('bsp_SlipPoints').Value = slip_points
            Variable('bsp_SlipPointsNum').Value = len(json.loads(slip_points).get('slipPoints', []))


class DiagnosticExpert(Cloud):
    def __init__(self):
        self.host = "https://bsp-diag-expert-service.test.k8s.chehejia.com"
        # self.vin = env.vin
        # 1: roadside_breakdown; 2: flow_control
        Variable('httpReq_DiagExpert_warnInfo').Value = 0
        Variable('httpReq_DiagExpert_treeInfo').Value = 0
        # 告警信息
        Variable('httpResp_DiagExpert_warnInfo').Value = ''    # 故障告警信息
        Variable('bsp_DiagExpert_warnId').Value = ''           # 故障告警ID
        Variable('bsp_DiagExpert_treeName').Value = ''         # 故障树名称
        # 故障树信息
        Variable('httpResp_DiagExpert_treeInfo').Value = ''    # 故障告警信息
        Variable('bsp_DiagExpert_treeNodeNames').Value = ''    # 子节点名称
        Variable('bsp_DiagExpert_treeNodeSignals').Value = ''  # 告警信号; bsp_DiagExpert_treeNodeSignal_[信号名] = 值

    @classmethod
    def get_auth(cls):
        auth_filepath = os.path.normpath(os.path.join(work_dir, 'runner', 'auth'))
        with open(auth_filepath, 'r', encoding='utf-8') as f:
            auth = f.read()
        return auth

    async def get_warn_info(self, vin, project_type=1, start_time='', end_time=''):
        url = self._prepare_warn_info_url(vin, project_type, start_time, end_time)
        async with aiohttp.ClientSession() as session:
            resp_json = await self.async_request(session, 'POST', url)
            self._handle_warn_info_response(resp_json)

    def sync_get_warn_info(self, vin, project_type=1, start_time='', end_time=''):
        url = self._prepare_warn_info_url(vin, project_type, start_time, end_time)
        resp_json = self.sync_request('POST', url)
        self._handle_warn_info_response(resp_json)

    async def get_tree_info(self, warn_id, project_type=1):
        url = self._prepare_tree_info_url(warn_id, project_type)
        async with aiohttp.ClientSession() as session:
            resp_json = await self.async_request(session, 'GET', url)
            self._handle_tree_info_response(resp_json)

    def sync_get_tree_info(self, warn_id, project_type=1):
        url = self._prepare_tree_info_url(warn_id, project_type)
        resp_json = self.sync_request('GET', url)
        self._handle_tree_info_response(resp_json)

    def _prepare_warn_info_url(self, vin, project_type, start_time, end_time):
        """Prepare the URL for warn info request based on project type."""
        if project_type == 1:
            return urljoin(self.host, f'/v1/diag/expert/project/warn?size=1&current=1&vin={vin}&startTime={start_time}&endTime={end_time}')
        elif project_type == 2:
            return urljoin(self.host, f'/v1/diag/expert/flow/warn?size=1&current=1&vin={vin}&startTime={start_time}&endTime={end_time}')
        else:
            raise ValueError('不支持此项目类型')

    def _prepare_tree_info_url(self, warn_id, project_type):
        """Prepare the URL for tree info request based on project type."""
        if project_type == 1:
            return urljoin(self.host, f'/v1/diag/expert/project/result?id={warn_id}')
        elif project_type == 2:
            return urljoin(self.host, f'/v1/api/flow/result?id={warn_id}')
        else:
            raise ValueError('不支持此项目类型')

    @classmethod
    def _handle_warn_info_response(cls, resp_json):
        """Process the warn info response JSON."""
        if resp_json:
            logger.info(f'诊断专家云端告警信息: {resp_json}')
            Variable('httpResp_DiagExpert_warnInfo').Value = resp_json
            records = resp_json.get('data', {}).get('records', [])
            if records:
                record = records[0]
                Variable('bsp_DiagExpert_treeName').Value = record.get('treeName')
                Variable('bsp_DiagExpert_warnId').Value = record.get('id')

    @classmethod
    def _handle_tree_info_response(cls, resp_json):
        """Process the tree info response JSON."""
        if resp_json:
            logger.info(f'诊断专家云端故障树信息: {resp_json}')
            Variable('httpResp_DiagExpert_treeInfo').Value = resp_json
            data = resp_json.get('data', [])
            if data:
                tree_info = data[0]
                tree_data = json.loads(tree_info.get('data'))
                nodes = tree_data.get('nodes')
                signals = tree_data.get('signals', [])
                event_tree_nodes = nodes.get('eventTreeNode', {}).get('eventTreeNodes', [])
                if event_tree_nodes:
                    node_names = []
                    variable_labels = []
                    for event_tree_node in event_tree_nodes:
                        node_names.append(event_tree_node.get('name', ''))
                        parameters = event_tree_node.get('parameters', [])
                        for p in parameters:
                            variable_labels.append(p['variableLabel'])
                    Variable('bsp_DiagExpert_treeNodeNames').Value = node_names
                    Variable('bsp_DiagExpert_treeVariableLabels').Value = variable_labels

                Variable('bsp_DiagExpert_treeNodeSignals').Value = signals
                for signal_name, signal_value in signals.items():
                    Variable(f'bsp_DiagExpert_treeNodeSignal_{signal_name}').Value = signal_value


class CloudConnector:
    """
    支持所有httpReq信号类的触发方式
    """

    def __init__(self):
        self.slip_control = SlipControl()
        self.diag_expert = DiagnosticExpert()

    @classmethod
    def get_time_range(cls, hours: int) -> tuple[str, str]:
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        fmt = "%Y-%m-%d %H:%M:%S"
        return start_time.strftime(fmt), end_time.strftime(fmt)

    def fetch(self, signal_name, signal_value, async_mode=True):
        if signal_name == 'httpReq_SlipControl' and signal_value == 1:
            logger.info('请求打滑预控车端上报数据')
            if async_mode:
                asyncio.run(self.slip_control.get_upload_data(1, 1, env.vin))
            else:
                self.slip_control.sync_get_upload_data(1, 1, env.vin)
        elif signal_name == 'httpReq_SlipControl' and signal_value == 2:
            logger.info('请求打滑预控云端指令下发数据')
            if async_mode:
                asyncio.run(self.slip_control.get_job_data(1, 1, env.vin))
            else:
                self.slip_control.sync_get_job_data(1, 1, env.vin)
        elif signal_name == 'httpReq_DiagExpert_warnInfo':
            logger.info(f'请求诊断专家告警信息, 项目类型: {signal_value}')
            st, et = self.get_time_range(hours=1)
            if async_mode:
                asyncio.run(self.diag_expert.get_warn_info(env.vin, project_type=signal_value, start_time=st, end_time=et))
            else:
                self.diag_expert.sync_get_warn_info(env.vin, project_type=signal_value, start_time=st, end_time=et)
        elif signal_name == 'httpReq_DiagExpert_treeInfo':
            logger.info(f'请求诊断专家故障树信息, 项目类型: {signal_value}')
            if async_mode:
                asyncio.run(self.diag_expert.get_tree_info(Variable('bsp_DiagExpert_warnId').Value, project_type=signal_value))
            else:
                self.diag_expert.sync_get_tree_info(Variable('bsp_DiagExpert_warnId').Value, project_type=signal_value)


if __name__ == '__main__':

    # 打滑预控使用示例
    # env.vin = 'LW433B125N1000073'
    # # 异步调用
    # CloudConnector.fetch('httpReq_SlipControl', 1, async_mode=True)
    # # 异步调用
    # CloudConnector.fetch('httpReq_SlipControl', 2, async_mode=True)

    # # 同步调用
    # CloudConnector.fetch('httpReq_SlipControl', 1, async_mode=False)
    # # 同步调用
    # CloudConnector.fetch('httpReq_SlipControl', 2, async_mode=False)

    # 诊断专家使用示例
    env.vin = 'HLX14B177P9900006'
    cloud_connector = CloudConnector()
    # cloud_connector.fetch('httpReq_DiagExpert_warnInfo', 1, async_mode=True)
    # cloud_connector.fetch('httpReq_DiagExpert_treeInfo', 1, async_mode=True)

    cloud_connector.fetch('httpReq_DiagExpert_warnInfo', 1, async_mode=False)
    cloud_connector.fetch('httpReq_DiagExpert_treeInfo', 1, async_mode=False)
