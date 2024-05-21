# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Email   : likun19941001.com
# @Time    : 2023/10/25 15:05
# @File    : ssh.py

import os
import stat
import json
import sys
import time
import re
import paramiko
from paramiko.ssh_exception import SSHException
from functools import wraps
from runner.log import logger
from settings import env
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


def check_connections(func):
    """ssh重连装饰器"""
    @wraps(func)
    def deco(self, *args, **kwargs):
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
        # 重连后再次尝试执行函数
        return func(self, *args, **kwargs)

    return deco


class SSHClient:
    ''' 远程连接Linux类 '''
    def __init__(self, hostname, username, password, port=22, connection_timeout=5, retry_times=3, p_key=None):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.port = port
        # 连接超时时间 单位秒 如果是端口错误不计入连接超时
        self.connection_timeout = connection_timeout
        self.retry_times = retry_times
        self.invoke_exit = False
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
        '''
        关闭ssh连接
        _client关闭后也会直接关闭_transport的应用
        因此_transport不需要再关闭了
        '''
        try:
            self._client.close()
        except:
            pass
        logger.info('SSH Client 连接通道已关闭')

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
        """这个方法每次使用都是一个独立的channel，不适合连续作业"""
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
                # timeout阻塞时，这个条件走不到
                elif self.invoke_exit:
                    logger.info('Receive invoke exit flag and close channel')
                    self._channel.close()
                    return output_buffer
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
        Variable('sql3_switch').Value = 0
        self.vin_filepath = '/app_data/common/vin.json'
        self.cfg_wd_filepath = '/app_data/common/cfgwd.json'
        self.vcs_ip_config_filepath = '/apps/x01/etc/vcs/ip_config.json'
        self.update_dbo_file()
        self.get_xcu_info()
        self.add_channel_cmd_signals()
        # self.put_sil_server()  # 放到PreCondition运行

    def add_channel_cmd_signals(self):
        """
        将终端命令行操作设置成信号
        Returns:
        """
        Variable('ssh_exec_cmd').Value = ''
        Variable('ssh_interactive_cmd').Value = ''
        Variable('ssh_exec_output').Value = ''

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
        env.xcu_info = {'vin': self.get_vin(), 'config_word': self.get_cfg_wd(), 'baseline_version': '',
                        'acore_version': '', 'apps_version': '', 'bsp_version': '', 'ecu_sub_system': ''}
        if hasattr(env, 'platform_version') and env.platform_version == 2.5:
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

    def modify_config_word_file(self, data):
        try:
            cwd_now = self.get_cfg_wd()
            if data and cwd_now == data:
                logger.info('当前配置字与待修改配置字相同,无需操作')
                return True
            self.execute_cmd(f"""sed -i 's/"{cwd_now}"/"{data}"/g' {self.cfg_wd_filepath}""")
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
            logger.info(f'>>> 当前sdc服务已启动 进程id: {output}, 开始禁用sdc服务')
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

    def put_sil_server(self):
        self.open_permission()
        need_reboot = False
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

    def get_vsc_db_signals(self):
        """
        测试前需要运行
        """
        signals = {}
        cmd = f'sqlite3 -csv {env.vcs_db_path}{env.vcs_db_name} "select * from {env.vcs_signal_table_name}"'
        res = self.execute_cmd(cmd)
        for row in res.split('\n'):
            if row:
                row_array = row.split(',')
                signal_name = 'sql3_' + row_array[0]
                signal_value = int(row_array[1])
                Variable(signal_name).Value = signal_value
                signals[signal_name] = signal_value
                action_signal_name = 'sql3_write_' + row_array[0]
                action_signal_value = 0
                Variable(action_signal_name).Value = action_signal_value
        return signals

    def set_vsc_db_signal(self, signal_name, signal_value):
        cmd = f'''sqlite3 {env.vcs_db_path}{env.vcs_db_name} "update {env.vcs_signal_table_name} \
        set value = {signal_value} where key_name = '{signal_name}'"'''
        logger.info(f'设置VCS-DB信号：{signal_name} = {signal_value}')
        self.execute_cmd(cmd)
        Variable('sql3_write_' + signal_name).Value = signal_value

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


if __name__ == '__main__':
    ssh_connector = SSHConnector(hostname='172.31.30.32', username='root', password='')

    # ssh_connector.put_sil_server()
    # print(ssh_connector.get_vin())

    # signals = ssh_connector.get_vsc_db_signals()
    # print(signals)

    # ssh_connector.set_vsc_db_signal(signal_name='ActuEgyMd_out_Inner', signal_value=2)
    # signals = ssh_connector.get_vsc_db_signals()
    # print(signals)
