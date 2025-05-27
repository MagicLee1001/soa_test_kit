# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Email   : likun19941001@163.com
# @Time    : 2023/10/25 15:05
# @File    : ssh.py

import os
import stat
import json
import sys
import time
import re
import tempfile
import traceback
import yaml
import paramiko
import threading
import select
from decorator import decorator
from paramiko.ssh_exception import SSHException
from functools import wraps
from runner.log import logger
from pathlib import Path
from settings import work_dir, env
from runner.variable import Variable


class SSHConnectTimeout(Exception):
    def __init__(self, err='远程连接超时'):
        Exception.__init__(self, err)


class SSHAuthFailed(Exception):
    def __init__(self, err='用户名或密码验证失败'):
        Exception.__init__(self, err)


class TimeLimitExceeded(Exception):
    def __init__(self, err='SFTP下载超时'):
        Exception.__init__(self, err)


def time_exceeded_callback(start_time, time_limit=5):
    """回调函数 文件下载时长限制"""
    elapsed_time = time.time() - start_time
    if elapsed_time > time_limit:
        raise TimeLimitExceeded


# def check_connections(func):
#     """ssh重连装饰器"""
#     @wraps(func)
#     def deco(self, *args, **kwargs):
#         try:
#             # 尝试执行函数，如果连接正常则直接返回结果
#             if self._client and self._client.get_transport().is_active():
#                 return func(self, *args, **kwargs)
#             else:
#                 # 连接不正常，尝试重新连接
#                 logger.warning('ssh client transport inactive or lost.')
#                 self._connect()
#         except (SSHException, OSError) as e:
#             # 捕获到SSH连接异常，记录日志并尝试重连
#             logger.warning(f'SSH connection error during function execution: {e}')
#             self._connect()
#         # 重连后再次尝试执行函数
#         return func(self, *args, **kwargs)
#
#     return deco


@decorator
def check_connections(func, self, *args, **kwargs):
    try:
        # 尝试执行函数，如果连接正常则直接返回结果
        if self._client and self._client.get_transport().is_active():
            return func(self, *args, **kwargs)
        else:
            # 连接不正常，尝试重新连接
            logger.warning('ssh client transport inactive or lost.')
            self._connect()
    except (SSHException, OSError) as e:
        # 捕获到SSH连接异常，记录日志并尝试重连
        logger.warning(f'SSH connection error during function execution: {e}')
        self._connect()
    return func(self, *args, **kwargs)


class SSHClient:
    ''' 远程连接Linux类 '''
    def __init__(self, hostname, username, password, port=22, connection_timeout=15, retry_times=3, p_key=None):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.port = port
        # 连接超时时间 单位秒 如果是端口错误不计入连接超时
        self.connection_timeout = connection_timeout
        self.retry_times = retry_times
        self._client = None
        self._transport = None
        self._channel = None
        self._sftp = None
        # 防止 paramiko.ssh.SSHException: Error reading SSH protocol banner
        self.banner_timeout = 60
        # 防止 paramiko.ssh_exception.SSH exception:Server connection dropped
        self.__sftp_windows_size = 1073741824
        self.__sftp_max_package_size = 1073741824
        # 7-bit C1 ANSI sequences
        self._ansi_escape = re.compile(r'''
                \x1B  # ESC
                (?:   # 7-bit C1 Fe (except CSI)
                [@-Z\\-_]
                |     # or [ for CSI, followed by a control sequence
                \[
                [0-?]*  # Parameter bytes
                [ -/]*  # Intermediate bytes
                [@-~]   # Final byte
            )
        ''', re.VERBOSE)
        self.need_private_auth = False
        self.private = paramiko.RSAKey.from_private_key_file(env.ssh_key_filepath) if not p_key else p_key
        self._connect()

    def __del__(self):
        """
        关闭ssh连接, _client关闭后也会直接关闭_transport的应用, 因此_transport不需要再关闭了
        """
        try:
            self._client.close()
        except:
            pass
        logger.info('SSHClient 连接通道已关闭')

    def close(self):
        self.__del__()

    def _match(self, out_str: str, end_str: list) -> (bool, str):
        result = self._ansi_escape.sub('', out_str)
        for i in end_str:
            if result.endswith(i):
                return True, result
        return False, result

    def _connect(self):
        try:
            # ************** SSH Connection  ************** #
            self._client = paramiko.SSHClient()
            # 允许连接不在know_hosts文件中的主机
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            for i in range(self.retry_times+1):
                try:
                    if self.need_private_auth:
                        self._client.connect(hostname=self.hostname, username=self.username, password=self.password,
                                             port=self.port, pkey=self.private, timeout=self.connection_timeout)
                    else:
                        self._client.connect(hostname=self.hostname, username=self.username, password=self.password,
                                             port=self.port, timeout=self.connection_timeout)
                except paramiko.ssh_exception.BadAuthenticationType:
                    if self.need_private_auth:
                        self._client.connect(hostname=self.hostname, username=self.username, password=self.password,
                                             port=self.port, timeout=self.connection_timeout)
                        self.need_private_auth = False
                    else:
                        self._client.connect(hostname=self.hostname, username=self.username, password=self.password,
                                             port=self.port, pkey=self.private, timeout=self.connection_timeout)
                        self.need_private_auth = True

                except paramiko.ssh_exception.AuthenticationException as e:
                    try:
                        self._client.get_transport().auth_none('root')
                    except:
                        raise SSHAuthFailed

                except Exception as e:
                    logger.error(f'{self.hostname} connect fail: {str(e)}, retry {i} times, total retry {self.retry_times}')
                    time.sleep(self.connection_timeout)
                    if i >= self.retry_times:
                        self._client = None
                        raise SSHConnectTimeout
                else:
                    break
        except Exception as e:
            logger.error(e)
            raise e

    def create_transport(self):
        """sftp will be created when create transport"""
        if not self._transport or not self._transport.is_active():
            if self._transport:
                self._transport.close()
            self._transport = self._client.get_transport()
        if not self._sftp or not not self._transport.is_active():
            self._sftp = paramiko.SFTPClient.from_transport(self._transport,
                                                            self.__sftp_windows_size,
                                                            self.__sftp_max_package_size)

    def create_channel(self, timeout, term='xterm'):
        self._channel = self._client.invoke_shell(term=term)
        self._channel.settimeout(timeout)
        time.sleep(0.2)

    def create_continuous_channel(self, timeout, is_bash=False):
        self._channel = self._client.invoke_shell()
        self._channel.settimeout(timeout)
        while not self._channel.recv_ready():
            time.sleep(0.1)
        stdout = self._channel.recv(4096)
        if is_bash:
            self._channel.send(b'bash\n')
            while not self._channel.recv_ready():
                time.sleep(0.5)
            stdout += self._channel.recv(1024)
        stdout = stdout.decode('utf-8')
        return stdout

    def get_remote_files(self, remote_dir):
        self.create_transport()
        # 防止拼接时多个/后缀
        remote_dir = remote_dir.rstrip('/')
        files_attr = self._sftp.listdir_attr(remote_dir)
        try:
            for file_attr in files_attr:
                if stat.S_ISDIR(file_attr.st_mode):
                    son_remote_dir = remote_dir + '/' + file_attr.filename
                    yield from self.get_remote_files(son_remote_dir)
                else:
                    yield remote_dir + '/' + file_attr.filename
        except Exception as e:
            logger.error(f'Get remote files: {e}')

    @check_connections
    def mkdir(self, remote_temp_dir):
        self.create_transport()
        self._sftp.mkdir(remote_temp_dir)

    @check_connections
    def sftp_download_files(self, remote_dir, local_dir):
        """此方法优化，对等远端同级目录，不再把所有文件归在同一目录下"""
        if os.path.exists(local_dir):
            pass
        else:
            os.mkdir(local_dir)
        files = self.get_remote_files(remote_dir)
        for remote_file in files:
            local_filepath = os.path.join(local_dir, os.path.normpath(remote_file.replace(remote_dir, '').lstrip('/')))
            local_file_dir = os.path.dirname(local_filepath)
            os.makedirs(local_file_dir, exist_ok=True)
            self.sftp_get(remote_file, local_filepath)

    @check_connections
    def sftp_get(self, remote_file, local_file):
        # 避免路径出现/r/n字符
        local_file = local_file.replace('\r\n','')
        self.create_transport()
        try:
            start_time = time.time()
            self._sftp.get(remote_file, local_file, time_exceeded_callback(start_time))
        except TimeLimitExceeded:
            logger.error(f'SFTP GET Timeout')
        except FileNotFoundError:
            logger.error(f'File not found: {remote_file}')
        except Exception as e:
            logger.error(f'SFTP GET Error: {e}')
            raise e
        else:
            return True

    @check_connections
    def sftp_put(self, local_file, remote_file):
        self.create_transport()
        try:
            self._sftp.put(local_file, remote_file)
        except Exception as e:
            logger.error(f'SFTP PUT Error: {e}')
            raise e
        else:
            return True

    @check_connections
    def execute_cmd(self, cmd, read_buffer=4096, env=None, console=False):
        stdin, stdout, stderr = self._client.exec_command(cmd, environment=env)
        stdout = stdout.read(read_buffer).decode("utf-8")
        if len(stdout) > 0:
            if console:
                logger.info(stdout)
            return stdout
        stderr = stderr.read(read_buffer).decode("utf-8")
        if len(stderr) > 0:
            if console:
                logger.info(stdout)
            return stderr

    @check_connections
    def execute_interact_cmd(self, cmd, timeout=10, tail='# ', exit_condition=None, buffer_size=1024, console=False):
        """
        只执行一次交互式指令，调用此方法，每次只开启一次管道，一次交互，不适合在管道内连续作业
        注意避免线程资源竞争，不在多线程中同时执行此方法
        Args:
            cmd: 交互式指令
            timeout: 管道超时时间
            tail: 管道结束符指令符
            exit_condition: 管道退出条件
            buffer_size: 一次接收最大字节数
            console: 日志打印开关

        Returns:

        """
        output_buffer = ''
        pwd_info = 'password: '
        ask = '(yes/no)? '
        num_tail_cursor = 0
        self.create_channel(timeout)
        # 不能直接发送命令, 连接终端延迟会造成命令失效
        while True:
            try:
                # 这个地方，如果一直接收不到的话，会形成阻塞，只会走timeout条件
                output = self._ansi_escape.sub('', self._channel.recv(buffer_size).decode('utf-8'))
            except OSError as e:
                logger.error(f'Connection OS Error info: {e} ')
                self._channel.close()
                return output_buffer
            except UnicodeDecodeError as e:
                logger.error(f'UnicodeDecode Error info : {e} ')
            else:
                if console and output:
                    logger.info(output)
                output_buffer += output
                # ssh命令要输入密码确认
                if output_buffer.endswith(pwd_info):
                    self._channel.send(self.password + '\n')
                elif output_buffer.endswith(tail) and num_tail_cursor == 0:
                    self._channel.send(cmd + '\n')
                    num_tail_cursor += 1
                # 在当前所在会话框
                elif output_buffer.endswith(tail) and num_tail_cursor != 0:
                    self._channel.close()
                    return output_buffer
                # 有询问密钥认证之类的对话框
                elif output_buffer.endswith(ask):
                    self._channel.send('yes' + '\n')
                elif exit_condition and exit_condition in output:
                    self._channel.send('\x03')  # 发送 Ctrl-C
                    self._channel.close()
                    return output_buffer
                else:
                    pass
            time.sleep(0.1)


class SSHConnector(SSHClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.vin = ''
        self.vin_filepath = '/app_data/common/vin.json'
        self.cfg_wd_filepath = '/app_data/common/cfgwd.json'
        self.vcs_ip_config_filepath = '/apps/x01/etc/vcs/ip_config.json'
        self.vss_cli_filepath = '/apps/x01/bin/vss-cli'
        self.eid_fid_cli_remote_filepath = '/apps/x01/bin/eid_fid_cli'
        self.service_manager_sdf_path = '/apps/framework/sdf/service_manager.yaml'
        self.db_path = {
            'vcs': '/app_data/vcs/vcs_v1.db',
            'rule': '/app_data/rule/iot/rmeta_topic/db/rule.db'
        }
        self.table_name = {
            'd': 'config_store_double',
            'i': 'config_store_int',
            's': 'config_store_string'
        }
        # 初始化时要做的事情
        self.initialize()

    def initialize(self, callback=None):
        if callback:
            callback.emit(f'ssh连接器 部署sil仿真节点到被测端 ...')
        logger.info('>>> ssh连接器 sil仿真节点部署 ...')
        # 对比远端dbo文件并更新
        self.update_dbo_file()
        # 获取xcu软件信息
        if callback:
            callback.emit(f'ssh连接器 获取被测软件信息 ...')
        self.get_xcu_info()
        # 添加sshconnector下的所以相关信号变量
        self.add_channel_cmd_signals()
        # 放置vss-cli
        if callback:
            callback.emit(f'ssh连接器 上传vss_cli ...')
        self.put_vss_cli()
        # 故障注入文件放置
        if callback:
            callback.emit(f'ssh连接器 上传eid_fid_cli ...')
        self.put_eid_fid_cli_file()
        # sdf总控文件先配置好
        if env.platform_name == 'XDP':
            self.add_sdf_to_service_manager_file()
        # 放置sil文件
        if callback:
            callback.emit(f'ssh连接器 上传sil ...')
        self.put_sil_server()  # 放到PreCondition运行
        if callback:
            callback.emit(f'ssh连接器 vcsDB信号初始化 ...')
        logger.info('>>> ssh连接器 vcsDB信号初始化 ...')
        self.get_db_signals(db_name='vcs', table_type='i')
        self.get_db_signals(db_name='vcs', table_type='d')
        self.get_db_signals(db_name='vcs', table_type='s')
        logger.info('>>> ssh连接器 ruleDB信号初始化 ...')
        self.get_db_signals(db_name='rule', table_type='i')
        self.get_db_signals(db_name='rule', table_type='d')
        self.get_db_signals(db_name='rule', table_type='s')
        time.sleep(1)

    def uninitialize(self):
        self.close()

    def add_channel_cmd_signals(self):
        """
        将终端命令行操作设置成信号
        Returns:
        """
        # 读数据库的事件
        Variable('sql3_switch_vcs_i').Value = 0
        Variable('sql3_switch_vcs_d').Value = 0
        Variable('sql3_switch_vcs_s').Value = 0
        Variable('sql3_switch_rule_i').Value = 0
        Variable('sql3_switch_rule_d').Value = 0
        Variable('sql3_switch_vcs_s').Value = 0
        # ssh交互动作
        Variable('ssh_exec_cmd').Value = ''
        Variable('ssh_exec_output').Value = ''
        Variable('ssh_sftp_get').Value = ''
        Variable('ssh_sftp_put').Value = ''
        # vss交互动作
        Variable('vss_').Value = ''
        Variable('vss_get').Value = ''
        Variable('vssSet_').Value = ''
        Variable('vssTS_').Value = ''
        Variable('vssMask_').Value = ''

    def open_permission(self):
        self.execute_cmd('mount -o remount rw /')
        self.execute_cmd('mount -o remount rw /apps')

    def check_process(self, proc_name, timeout=30):
        ct = time.time()
        ret = 0
        while time.time() - ct <= timeout:
            ret = self.execute_cmd(f'pidof {proc_name}')
            if ret:
                logger.success(f'{proc_name}进程已启动 进程号: {ret}')
                break
            time.sleep(2)
        if not ret:
            logger.error(f'>>> {proc_name}进程未启动')
        return ret

    def recover_sil_environment(self, recover_vcs=True, recover_sdc=True):
        """
        还原测试环境, 恢复到测试之前
        """
        self.open_permission()
        if recover_vcs:
            # 还原vcs配置
            self.setup_vcs_ip_config(0)
        # 移除sil仿真相关程序与配置
        self.execute_cmd(f'rm {env.sil_remote_filepath}')
        self.execute_cmd(f'rm {env.sil_sdf_remote_filepath}')
        # 还原service_manager.sdf
        if env.platform_name == 'XDP' and 'No such file' not in self.execute_cmd(f'ls {self.service_manager_sdf_path}.cp'):
            self.execute_cmd(f'mv {self.service_manager_sdf_path}.cp {self.service_manager_sdf_path}')

        if recover_sdc:
            self.execute_cmd('mv /apps/x01/bin/sdc1 /apps/x01/bin/sdc')
        self.execute_cmd('sync')
        time.sleep(1)
        self.execute_cmd('reboot')
        logger.info('>>> 重启被测设备以恢复原有服务 等待20秒')
        time.sleep(20)
        if recover_sdc:
            self.check_process('sdc', timeout=30)

    def get_xcu_info(self):
        env.xcu_info = {
            'vin': self.get_vin(),
            'config_word': self.get_cfg_wd(),
            'baseline_version': '',
            'acore_version': '',
            'apps_version': '',
            'bsp_version': '',
            'ecu_sub_system': ''
        }
        env.vin = self.vin = env.xcu_info['vin']
        if env.platform_version == 3.0:
            res = self.execute_interact_cmd('liware.tool.dumpsys', console=False)
            res_list = res.split('\r\n')
            for i in range(len(res_list)):
                if 'ro.build.version.baseline' in res_list[i]:
                    env.xcu_info['baseline_version'] = res_list[i].split(' ')[-1].replace('[', '').replace(']', '')
                elif 'ro.build.version.bsp' in res_list[i]:
                    env.xcu_info['bsp_version'] = res_list[i].split(' ')[-1].replace('[', '').replace(']', '')
                elif 'ro.build.version.package' in res_list[i]:
                    env.xcu_info['acore_version'] = res_list[i].split(' ')[-1].replace('[', '').replace(']', '')
                elif 'ro.build.version.livc' in res_list[i]:
                    env.xcu_info['apps_version'] = res_list[i].split(' ')[-1].replace('[', '').replace(']', '')
        else:
            res = self.execute_interact_cmd('dumpsys', console=False)
            res_list = res.split('\r\n')
            for i in range(len(res_list)):
                if 'XCU Show Version' in res_list[i]:
                    env.xcu_info['baseline_version'] = res_list[i + 1]
                    env.xcu_info['acore_version'] = res_list[i + 2]
                elif 'BSP Version' in res_list[i]:
                    env.xcu_info['bsp_version'] = res_list[i + 1]
                elif 'APPS Version' in res_list[i]:
                    env.xcu_info['apps_version'] = res_list[i + 1]
                else:
                    pass
        logger.info(f'获取XCU版本信息: {env.xcu_info}')
        return env.xcu_info

    def get_vin(self):
        try:
            output = self.execute_cmd(f'cat {self.vin_filepath}')
            return json.loads(output)['vin']
        except:
            return '0'*17

    def get_cfg_wd(self):
        try:
            output = self.execute_cmd(f'cat {self.cfg_wd_filepath}').strip()
            cwd_now = json.loads(output)['vehicleConfigWord']
        except Exception as e:
            logger.error(e)
            return ''
        else:
            return cwd_now

    def add_sdf_to_service_manager_file(self):
        # 备份
        self.execute_cmd(
            f'cp {self.service_manager_sdf_path} {self.service_manager_sdf_path}.cp'
        )
        self.process_remote_yaml(
            self.service_manager_sdf_path,
        )

    def process_remote_yaml(
            self,
            remote_yaml_path: str,
            temp_dir: str = None
    ) -> None:
        """
        完整的SFTP YAML处理流程

        :param remote_yaml_path: 远端YAML路径 (e.g. "/config/app.yaml")
        :param temp_dir: 临时目录路径（可选）
        """
        sil_sdf_data = {
            "Name": "sil",
            "Path": "/apps/x01/sdf/sil.sdf",
            "Priority": "high",
            "Type": "apps",
            "StartDelay": 1500,
            "ResourceLimit": [
                {
                    "Mode": ["normal", "factory", "logistic", "exhibition", "ota1", "ota2", "repair"],
                    "CpuLimit": 10,
                    "MemLimit": "160M"
                }
            ]
        }

        with tempfile.TemporaryDirectory(dir=temp_dir, prefix="sftp_yaml_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            try:
                # 下载原始文件
                local_yaml = tmp_path / "service_manager.yaml"
                logger.info(f"Downloading {remote_yaml_path} to {local_yaml}")
                self.sftp_get(remote_yaml_path, str(local_yaml))

                # 读取并合并数据
                existing_data = {}
                if local_yaml.exists() and local_yaml.stat().st_size > 0:
                    with open(local_yaml, 'r') as f:
                        existing_data = yaml.safe_load(f) or []

                names = [i['Name'] for i in existing_data['ServiceManifest']]
                # 追加新数据
                if 'sil' not in names:
                    existing_data['ServiceManifest'].append(sil_sdf_data)

                # 写入更新文件
                updated_yaml = tmp_path / "updated.yaml"
                with open(updated_yaml, 'w') as f:
                    yaml.dump(
                        existing_data,
                        f,
                        default_flow_style=False,
                        sort_keys=False,
                        indent=2
                    )

                # 上传更新文件
                logger.info(f"Uploading {updated_yaml} to {remote_yaml_path}")
                self.put_file(str(updated_yaml), remote_yaml_path)

            except Exception as e:
                logger.error(f"Processing failed: {str(e)}")
                raise e
            finally:
                # 确保清理临时文件
                if 'local_yaml' in locals() and local_yaml.exists():
                    local_yaml.unlink()
                if 'updated_yaml' in locals() and updated_yaml.exists():
                    updated_yaml.unlink()

    def modify_config_word_file(self, data):
        try:
            cfgwd_json = '{"crc":"00000000","vehicleConfigWord":"%s"}' % data
            self.execute_cmd(f"""echo '{cfgwd_json}' > {self.cfg_wd_filepath}""")
            self.execute_cmd('sync')
            logger.info('配置字已修改, 正在重启')
            self.execute_cmd('reboot')
            # 重启后触发重连机制
            time.sleep(10)
            output = self.execute_cmd(f'cat {self.cfg_wd_filepath}').strip()
            logger.info(f'当前配置字文件内容: {output}')
            if json.loads(output)['vehicleConfigWord'] == data:
                logger.success('A核配置字修改成功')
                return True
            else:
                logger.warning('A核配置字修改失败,请排查原因')
                return False

        except Exception as e:
            logger.error(e)

    def update_dbo_file(self):
        logger.info('>>> 检测当前dbo矩阵配置是否与目标系统一致')
        output = self.execute_cmd(f'cat {env.dbo_remote_filepath}')
        if os.path.exists(env.dbo_filepath):
            with open(env.dbo_filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            if content != output:
                logger.info('>>> 当前dbo矩阵与目标系统不一致 自动更新到本地')
                self.sftp_get(
                    remote_file=env.dbo_remote_filepath,
                    local_file=env.dbo_filepath
                )
            else:
                logger.info('>>> 当前dbo矩阵与目标一致 无需更新')
        else:
            logger.info('>>> 当前项目中无dbo文件 自动下载到本地')
            self.sftp_get(
                remote_file=env.dbo_remote_filepath,
                local_file=env.dbo_filepath
            )

    def disable_sdc_service(self):
        self.open_permission()
        output = self.execute_cmd(f'pidof sdc')
        if output:
            logger.info(f'>>> 当前sdc服务已启动 进程id: {output.strip()}, 开始禁用sdc服务')
            self.execute_cmd('mv /apps/x01/bin/sdc /apps/x01/bin/sdc1')
            self.execute_cmd('sync')
            self.execute_cmd('killall -9 sdc')
        else:
            logger.info('>>> 当前sdc服务未启动 无需禁用')

    def enable_sdc_service(self):
        self.open_permission()
        output = self.execute_cmd(f'pidof sdc')
        if not output:
            logger.info('>>> 当前sdc服务未启动 开始启动')
            self.execute_cmd('mv /apps/x01/bin/sdc1 /apps/x01/bin/sdc')
            self.execute_cmd('sync')
            time.sleep(1)
            self.execute_cmd('reboot')
            logger.info('>>> 重启被测设备以自动激活soa服务 等待20秒')
            time.sleep(20)
            self.check_process('sdc', timeout=20)

    def put_file(self, src_filepath, target_filepath):
        self.open_permission()
        self.sftp_put(src_filepath, target_filepath)
        self.execute_cmd(f'chmod 777 {target_filepath}')
        self.execute_cmd('sync')

    def put_vss_cli(self):
        logger.info('>>> 开始传输vss-cli到被测设备')
        self.put_file(env.vss_cli_local_filepath, self.vss_cli_filepath)

    def put_eid_fid_cli_file(self):
        if not self.execute_cmd(f'pidof eid_fid_cli'):
            logger.info('>>> 开始传输eid_fid_cli到被测设备')
            self.put_file(env.eid_fid_cli_local_filepath, self.eid_fid_cli_remote_filepath)
            local_so_filepath = os.path.join(work_dir, 'data', 'key', 'librule_proto.so')
            remote_so_filepath = '/apps/x01/lib/librule_proto.so'
            self.put_file(local_so_filepath, remote_so_filepath)

    def put_sil_server(self):
        need_reboot = False
        if env.deploy_sil:
            self.open_permission()
            pid = self.execute_cmd(f'pidof sil')
            output = self.execute_cmd(f'ls {env.sil_remote_filepath}')
            if 'No such file' in output or not pid:
                need_reboot = True
                logger.info('>>> 当前目标无sil服务, 开始部署sil仿真程序到被测设备')
                logger.info(f'本地: {env.sil_local_filepath} --> 远端: {env.sil_remote_filepath}')
                self.sftp_put(
                    local_file=env.sil_local_filepath,
                    remote_file=env.sil_remote_filepath
                )
                self.execute_cmd(f'chmod 777 {env.sil_remote_filepath}')
            else:
                logger.info(f'>>> sil服务已启动 {pid}')

            output = self.execute_cmd(f'ls {env.sil_sdf_remote_filepath}')
            if 'No such file' in output:
                need_reboot = True
                logger.info('>>> 当前目标无sil sdf文件, 开始上传文件到被测设备')
                logger.info(f'本地: {env.sil_sdf_local_filepath} --> 远端: {env.sil_sdf_remote_filepath}')
                self.sftp_put(
                    local_file=env.sil_sdf_local_filepath,
                    remote_file=env.sil_sdf_remote_filepath
                )
                self.execute_cmd(f'chmod 777 {env.sil_sdf_remote_filepath}')
            else:
                logger.info('>>> 当前目标存在sil sdf文件')

        if env.disable_sdc:
            self.disable_sdc_service()

        if need_reboot:
            self.execute_cmd('sync')
            time.sleep(1)
            self.execute_cmd('reboot')
            logger.info('>>> 重启被测设备以自动激活sil服务 等待20秒')
            time.sleep(20)
            ret = self.check_process('sil', timeout=30)
            if not ret:
                logger.error('>>> 执行环境异常 sil服务未启动 开始回滚')
                self.recover_sil_environment()
                raise Exception('sil simulator process not exist')
        else:
            logger.info(f'>>> 目标环境ready 无需重启')

    def get_db_signals(self, db_name='vcs', table_type='i'):
        """
        测试前需要运行
        """
        if 'No such file' not in self.execute_cmd(f'ls {self.db_path[db_name]}'):
            signals = {}
            cmd = f'sqlite3 -separator ";;" {self.db_path[db_name]} "select * from {self.table_name[table_type]}"'
            res = self.execute_cmd(cmd)
            if res and 'no such table' not in res:
                for row in res.split('\n'):
                    if row:
                        row_array = row.split(';;')
                        signal_name = f'sql3_{db_name}_{table_type}_' + row_array[0]
                        if table_type == 'i':
                            signal_value = int(row_array[1])
                        elif table_type == 'd':
                            signal_value = float(row_array[1])
                        else:
                            signal_value = row_array[1]
                        Variable(signal_name).Value = signal_value
                        signals[signal_name] = signal_value
                        action_signal_name = f'sql3_write_{db_name}_{table_type}_' + row_array[0]
                        Variable(action_signal_name).Value = 0
                return signals

    def set_db_signal(self, signal_name, signal_value, db_name='vcs', table_type='i'):
        if table_type == 's':
            value_format = "'%s'" % signal_value
        else:
            value_format = signal_value
        cmd = f'''sqlite3 {self.db_path[db_name]} "update {self.table_name[table_type]} \
        set value = {value_format} where key_name = '{signal_name}'"'''
        logger.info(f'设置VCS-DB信号：{signal_name} = {signal_value}')
        output = self.execute_cmd(cmd)
        Variable(f'sql3_write_{db_name}_{table_type}_' + signal_name).Value = signal_value

    def setup_vcs_ip_config(self, status: int):
        """
        status:
            0: DoIP仿真环境关闭
            1: DoIP仿真环境打开
        """
        self.open_permission()
        match status:
            case 0:
                if not hasattr(self, 'default_ip_config'):
                    logger.info('vcs ip配置为默认状态，无需还原')
                else:
                    # 修改当前配置文件为默认配置
                    res = self.execute_cmd(f'cat {self.vcs_ip_config_filepath}')
                    logger.info(f'当前vcs ip配置为：{res}')
                    self.execute_cmd(f"""echo '{json.dumps(self.default_ip_config, indent=4)}' > {self.vcs_ip_config_filepath}""")
                    res = self.execute_cmd(f'cat {self.vcs_ip_config_filepath}')
                    logger.info(f'还原后的vcs ip配置为：{res}')
            case 1:
                if not hasattr(self, 'default_ip_config'):
                    self.default_ip_config = json.loads(self.execute_cmd(f'cat {self.vcs_ip_config_filepath}'))
                    logger.info(f'获取当前vcs ip默认配置：{self.default_ip_config}')
                target_ip = env.local_net_segment
                modified_ip_config = {key: target_ip for key, val in self.default_ip_config.items()}
                self.execute_cmd(f"""echo '{json.dumps(modified_ip_config, indent=4)}' > {self.vcs_ip_config_filepath}""")
                res = self.execute_cmd(f'cat {self.vcs_ip_config_filepath}')
                logger.info(f'修改后的vcs ip配置为：{res}')

    def get_vss_signal(self, signal_name):
        cmd = rf'export DEBUG="" && export PATH=$PATH:/apps/x01/bin && {self.vss_cli_filepath} config --proxy_host localhost --proxy_port 52600 --domain xcu --device_id {self.vin} get -p {signal_name}'
        output = self.execute_interact_cmd(
            cmd,
            timeout=10
        )
        for i in output.split('\r\n'):
            if 'get success:' in i:
                res = json.loads(i.split('get success: ')[-1])
                if res:
                    signal_value = res[0].get('dp', {}).get('value')
                    timestamp = res[0].get('dp', {}).get('ts')
                    # 这里要做一个值变化的比较，如果这次值与时间戳没有进行更新，则赋一个标志变量记录
                    last_signal_val = Variable(f'vss_{signal_name}').Value
                    last_ts = Variable(f'vssTS_{signal_name}').Value
                    if signal_value == last_signal_val and timestamp == last_ts:
                        Variable(f'vssMask_{signal_name}').Value = -9999
                    else:
                        Variable(f'vssMask_{signal_name}').Value = signal_value
                    Variable(f'vss_{signal_name}').Value = signal_value
                    Variable(f'vssTS_{signal_name}').Value = timestamp
                    logger.info(f'接收VSS消息: {signal_name} = {signal_value} | {type(signal_value)} | timestamp: {timestamp}')
                    break
            elif 'get failed:' in i:
                Variable(f'vss_{signal_name}').Value = i.split('get failed:')[-1]
                break

    def set_vss_signal(self, signal_name, signal_value):
        if isinstance(signal_value, str):
            arg = '-s'
        elif isinstance(signal_value, int) or isinstance(signal_value, float):
            arg = '-d'
        else:
            raise Exception('vss signal value type error')
        output = self.execute_interact_cmd(
            rf'export DEBUG="" && export PATH=$PATH:/apps/x01/bin &&  {self.vss_cli_filepath} config --proxy_host localhost --proxy_port 52600 --domain xcu --device_id {self.vin} set -p {signal_name} -v {signal_value} {arg}',
            timeout=10
        )
        for i in output.split('\r\n'):
            if 'set result:' in i:
                res = json.loads(i.split('set result:')[-1])
                if res:
                    error_msg = res[0].get('error')
                    if error_msg:
                        logger.error(res[0].get('error'))
                    else:
                        Variable(f'vssSet_{signal_name}').Value = signal_value
                        logger.info(f'发送VSS消息: {signal_name} = {signal_value} | {type(signal_value)}')

    @check_connections
    def fault_inject(self, signal: Variable, timeout=3):
        def wait_for_response(channel, timeout=5):
            """
            等待通道返回完整响应，直到出现提示符或超时。
            :param channel: SSH Channel 对象
            :param timeout: 超时时间（秒）
            :return: 完整输出（字符串）
            """
            time.sleep(0.1)
            output = []
            end_time = time.time() + timeout
            while time.time() < end_time:
                # 使用 select 检测通道是否可读（非阻塞）
                rlist, _, _ = select.select([channel], [], [], 0.1)
                if channel in rlist:
                    data = channel.recv(1024).decode('utf-8')
                    if data:
                        output.append(data)
                        # 检查是否出现提示符
                        if ':\r\n' in output[-1] or '# ' in output[-1]:
                            break
                else:
                    # 无数据时短暂休眠，减少 CPU 占用
                    time.sleep(0.1)
            return ''.join(output)

        if not signal.name.startswith('eid_fid_'):
            logger.warning(f'信号不属于eid_fid故障注入信号，请仔细检查格式')
            return False

        channel = self._client.invoke_shell(term='xterm')
        channel.settimeout(timeout)
        time.sleep(0.2)
        try:
            logger.info(f'发送EID-FID消息： {signal.name} = {signal.Value}')
            channel.send('export LD_LIBRARY_PATH=:/apps/x01/lib/:/framework/lib/:/usr/lib:/lib/:/lib:/apps/x01/mesh/iot/lib:/apps/x01/res/lua_lib/:/apps/x01/mesh_services/iot/lib/:/apps/ota/lib/\n')
            # ================== 发送要执行的命令 ==================
            channel.send("/apps/x01/bin/eid_fid_cli\n")
            wait_for_response(channel)
            channel.send("1\n")
            wait_for_response(channel)
            # 发送信号
            channel.send(f"{signal.name[8:]} {signal.Value}\n")
            wait_for_response(channel)
            # 发送结束信号 ASCII 码 3 (Ctrl+C)
            channel.send(chr(3))
            wait_for_response(channel)
        except:
            logger.error(f'发送EID-FID消息失败')
            logger.error(traceback.format_exc())
        channel.close()


class SSHAsyncConnector(threading.Thread, SSHClient):
    def __init__(self, *args, **kwargs):
        # super().__init__(*args, **kwargs)  # 不能这样调用
        # 显式初始化所有父类（安全做法）
        threading.Thread.__init__(self)
        SSHClient.__init__(self, *args, **kwargs)
        Variable('ssh_interactive_cmd').Value = ''
        Variable('ssh_interactive_output').Value = ''
        self.close_event = threading.Event()
        self.interact_event = threading.Event()
        self.interact_lock = threading.Lock()
        self.interacting = False

    @check_connections
    def execute_interact_cmd(self, cmd, timeout=10, tail='# ', exit_condition=None, buffer_size=1024):
        """这个方法每次使用都是一个独立的channel，不适合连续作业"""
        if self.interacting:
            logger.warning('当前ssh_interactive_cmd 正在作业，请先发送 当前ssh_interactive_cmd=0 停止作业')
            return

        with self.interact_lock:
            self.interacting = True
            self.interact_event.clear()
            interaction_thread = threading.Thread(target=self.interaction_loop,
                                                  args=(cmd, timeout, tail, exit_condition, buffer_size))
            interaction_thread.daemon = True
            interaction_thread.start()

    def interaction_loop(self, cmd, timeout, tail, exit_condition, buffer_size):
        output_buffer = ''
        pwd_info = 'password: '
        ask = '(yes/no)? '
        num_tail_cursor = 0

        self.create_channel(timeout)

        while not self.interact_event.is_set():
            try:
                output = self._ansi_escape.sub('', self._channel.recv(buffer_size).decode('utf-8'))
            except OSError as e:
                logger.error(f'Connection OS Error info: {e}')
                self._channel.close()
                break
            except UnicodeDecodeError as e:
                logger.error(f'UnicodeDecode Error info : {e}')
            else:
                logger.info(output)
                output_buffer += output
                if output_buffer.endswith(pwd_info):
                    self._channel.send(self.password + '\n')
                elif output_buffer.endswith(tail) and num_tail_cursor == 0:
                    self._channel.send(cmd + '\n')
                    num_tail_cursor += 1
                elif output_buffer.endswith(tail) and num_tail_cursor != 0:
                    self._channel.close()
                    break
                elif output_buffer.endswith(ask):
                    self._channel.send('yes' + '\n')
                elif exit_condition and exit_condition in output:
                    self._channel.send('\x03')  # Ctrl-C
                    self._channel.close()
                    break

                time.sleep(0.1)

        self.interacting = False
        logger.info('SSHAsyncConnector interact_event 退出')
        Variable('ssh_interactive_output').Value = output_buffer

    def run(self):
        self.close_event.clear()
        while not self.close_event.is_set():
            time.sleep(1)
        logger.info('SSHAsyncConnector 异步线程关闭 资源释放')
        self.close()


if __name__ == '__main__':
    ssh_client = SSHClient(hostname='10.248.50.253', port=8888, username='root', password='')
    print(ssh_client.execute_cmd('ls /'))

    # ssh_connector = SSHConnector(hostname='172.31.30.32', port=22, username='root', password='root')
    # signal = Variable('eid_fid_EID_COMM_LOST_NOD_BMS')
    # signal.Value = 0
    # ssh_connector.fault_inject(signal)
    # signal.Value = 1
    # ssh_connector.fault_inject(signal)

    # ssh_connector.get_db_signals(db_name='rule', table_type='i')
    # ssh_connector.modify_config_word_file('0150110634FBFF6BFC1C3FFF01E3E20FFF')

    # ssh_connector.get_vss_signal('Vehicle.Charging.TrgtSOCReq')
    # ssh_connector.get_vss_signal('Vehicle.Charging.TrgtSOCReq')
    # ssh_connector.get_vss_signal('Vehicle.Charging.TrgtSOCReq')

    # ssh_connector.put_sil_server()
    # print(ssh_connector.get_vin())

    # signals = ssh_connector.get_db_signals()
    # print(signals)

    # ssh_connector.set_db_signal(signal_name='ActuEgyMd_out_Inner', signal_value=2)
    # signals = ssh_connector.get_db_signals()
    # print(signals)
    
    # ssh_connector = SSHAsyncConnector(hostname='172.31.30.32', username='root', password='root')
    # ssh_connector.start()
    #
    # ssh_connector.execute_interact_cmd('lilogcat | grep vcs')
    # time.sleep(5)
    # ssh_connector.interact_event.set()
    # with open(r"D:\likun3\Downloads\service_manager(2).yaml", 'r') as f:
    #     existing_data = yaml.safe_load(f) or []
    #     print(existing_data)
