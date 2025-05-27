# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2025/3/10 10:49
# @File    : database.py

import traceback
import yaml
import threading
import inspect
import ast
import json
from datetime import datetime, date, time
from decimal import Decimal
import mysql.connector
from mysql.connector import errorcode, Error
from contextlib import contextmanager
from typing import List, Dict, Any, Optional, Tuple, Union
from settings import env
from runner.variable import Variable
from runner.log import logger

#
# import traceback
# import yaml
# import threading
# import inspect
# import ast
# import json
# from datetime import datetime, date, time
# from decimal import Decimal
# import pymysql
# from pymysql import Error, MySQLError
# from pymysql.constants import ER
# from pymysql import cursors
# from contextlib import contextmanager
# from typing import List, Dict, Any, Optional, Tuple, Union
# from settings import env
# from runner.variable import Variable
# from runner.log import logger


# class MySQLDB:
#     def __init__(self, config: Dict[str, Any]):
#         """
#         初始化MySQL数据库连接（PyMySQL版本）
#         配置参数示例：
#         {
#             "host": "localhost",
#             "user": "root",
#             "password": "123456",
#             "database": "test_db",  # 内部会转为 'db'
#             "port": 3306,
#             "charset": "utf8mb4",
#             "autocommit": False
#         }
#         """
#         self.config = self._validate_config(config)
#         self.conn = None
#         self.transaction_active = False
#         self._lock = threading.Lock()
#         self._connect()
#
#     def _validate_config(self, config: Dict) -> Dict:
#         """验证并标准化配置参数（适配PyMySQL）"""
#         required_keys = ['host', 'user', 'password', 'database']
#         for key in required_keys:
#             if key not in config:
#                 raise ValueError(f"Missing required config key: {key}")
#
#         # 转换 'database' 为 PyMySQL 的 'db' 参数
#         config['db'] = config.pop('database')
#         config['port'] = int(config.get('port', 3306))
#         config['autocommit'] = config.get('autocommit', False)
#         config.pop('auth_plugin', None)  # PyMySQL 不需要此参数
#
#         # 字符集处理
#         if 'charset' not in config:
#             config['charset'] = 'utf8mb4'
#
#         return config
#
#     def _connect(self):
#         """建立数据库连接（PyMySQL实现）"""
#         try:
#             self.conn = pymysql.connect(**self.config)
#         except Error as e:
#             logger.error(f"Connection failed: {str(e)}")
#             raise ConnectionError(f"Database connection error: {str(e)}") from e
#
#     def _ensure_connection(self):
#         """确保连接有效"""
#         if self.conn and self.conn.open:
#             try:
#                 with self._lock, self.conn.cursor() as cursor:
#                     cursor.execute("SELECT 1")
#                 return
#             except Error:
#                 pass
#         self._connect()
#
#     @contextmanager
#     def transaction(self):
#         """事务上下文管理器（适配PyMySQL隐式事务）"""
#         self._ensure_connection()
#         original_autocommit = self.conn.autocommit()
#         try:
#             if original_autocommit:
#                 self.conn.autocommit(False)
#             self.transaction_active = True
#             yield
#             self.conn.commit()
#         except Exception as e:
#             self.conn.rollback()
#             raise
#         finally:
#             if original_autocommit:
#                 self.conn.autocommit(original_autocommit)
#             self.transaction_active = False
#
#     def execute(self, sql: str, params: Optional[Tuple] = None) -> int:
#         """执行非查询SQL"""
#         with self._lock:
#             self._ensure_connection()
#             try:
#                 with self.conn.cursor() as cursor:
#                     cursor.execute(sql, params)
#                     if not self.transaction_active:
#                         self.conn.commit()
#                     return cursor.rowcount
#             except Error as e:
#                 self._handle_error(e, sql, params)
#
#     def query(self, sql: str, params: Optional[Tuple] = None, auto_convert: bool = True) -> List[Dict]:
#         """执行查询（使用DictCursor）"""
#         with self._lock:
#             self._ensure_connection()
#             try:
#                 with self.conn.cursor(cursors.DictCursor) as cursor:
#                     cursor.execute(sql, params)
#                     raw_results = cursor.fetchall()
#                     return [self._convert_row(row) for row in raw_results] if auto_convert else raw_results
#             except Error as e:
#                 self._handle_error(e, sql, params)
#
#     def _convert_row(self, row: Dict) -> Dict:
#         """转换单行数据类型（增强版）"""
#         converted = {}
#         for key, value in row.items():
#             if isinstance(value, Decimal):
#                 converted[key] = float(value)
#             elif isinstance(value, datetime):
#                 converted[key] = value.strftime("%Y-%m-%d %H:%M:%S")
#             elif isinstance(value, date):
#                 converted[key] = value.strftime("%Y-%m-%d")
#             elif isinstance(value, time):
#                 converted[key] = value.strftime("%H:%M:%S")
#             elif isinstance(value, bytes):
#                 converted[key] = value.hex() if value else None
#             else:
#                 converted[key] = value
#         return converted
#
#     def _handle_error(self, error: Error, sql: str, params: Tuple):
#         """错误处理（适配PyMySQL错误码）"""
#         error_info = {
#             "errno": error.args[0],
#             "message": str(error),
#             "query": sql,
#             "params": params
#         }
#         logger.error(f"Database error: {error_info}")
#
#         # 处理连接类错误（2003, 2006, 2013）
#         if error.args[0] in (2003, 2006, 2013):
#             logger.warning("Reconnecting...")
#             self._connect()
#
#         raise DatabaseError(error_info) from error
#
#     # CRUD/增删改查快捷方法 --------------------------------------------------------
#     def insert(self, table: str, data: Dict) -> int:
#         """插入单条数据"""
#         columns = ', '.join([f'`{k}`' for k in data.keys()])
#         placeholders = ', '.join(['%s'] * len(data))
#         sql = f"INSERT INTO `{table}` ({columns}) VALUES ({placeholders})"
#         return self.execute(sql, tuple(data.values()))
#
#     def insert_many(self, table: str, columns: List[str], data: List[Tuple]) -> int:
#         """批量插入数据（优化版）"""
#         if not data:
#             return 0
#         cursor = None
#         try:
#             self._ensure_connection()
#             with self._lock, self.conn.cursor() as cursor:
#                 placeholders = ', '.join(['%s'] * len(columns))
#                 sql = f"INSERT INTO `{table}` ({', '.join(columns)}) VALUES ({placeholders})"
#
#                 cursor.executemany(sql, data)
#                 rowcount = cursor.rowcount
#
#                 if not self.transaction_active:
#                     self.conn.commit()
#
#                 return rowcount
#         except Error as e:
#             self._handle_error(e, sql, None)
#
#     def update(self, table: str, data: Dict, where: Dict) -> int:
#         """更新数据"""
#         set_clause = ', '.join([f'`{k}` = %s' for k in data.keys()])
#         where_clause = ' AND '.join([f'`{k}` = %s' for k in where.keys()])
#         sql = f"UPDATE `{table}` SET {set_clause} WHERE {where_clause}"
#         params = tuple(data.values()) + tuple(where.values())
#         return self.execute(sql, params)
#
#     def delete(self, table: str, where: Dict) -> int:
#         """增强版删除方法，支持运算符和列表值"""
#         where_clause = []
#         params = []
#
#         for key, value in where.items():
#             operator = '='
#             field = key
#
#             if '__' in key:
#                 field, operator = key.split('__', 1)
#
#             operator_map = {
#                 'gt': '>', 'lt': '<',
#                 'gte': '>=', 'lte': '<=',
#                 'ne': '!=', 'in': 'IN',
#                 'like': 'LIKE', 'is': 'IS'
#             }
#             op = operator_map.get(operator.lower(), '=')
#
#             if op.upper() == 'IN':
#                 if not isinstance(value, (list, tuple)):
#                     raise ValueError(f"IN operator requires iterable value, got {type(value)}")
#                 placeholders = ', '.join(['%s'] * len(value))
#                 where_clause.append(f"`{field}` IN ({placeholders})")
#                 params.extend(value)
#             elif op.upper() == 'LIKE':
#                 where_clause.append(f"`{field}` LIKE %s")
#                 params.append(value)
#             else:
#                 where_clause.append(f"`{field}` {op} %s")
#                 params.append(value)
#
#         sql = f"DELETE FROM `{table}`"
#         if where_clause:
#             sql += f" WHERE {' AND '.join(where_clause)}"
#
#         return self.execute(sql, tuple(params))
#
#     def get_table_columns(self, table: str) -> List[str]:
#         """获取表字段列表"""
#         sql = f"DESCRIBE `{table}`"
#         result = self.query(sql, auto_convert=False)
#         return [row['Field'] for row in result]
#
#     def close(self):
#         """关闭连接"""
#         if self.conn and self.conn.is_connected():
#             self.conn.close()
#             # logger.info("Database connection closed")
#
#     def __enter__(self):
#         return self
#
#     def __exit__(self, exc_type, exc_val, exc_tb):
#         self.close()


class MySQLDB:
    def __init__(self, config: Dict[str, Any]):
        """
        初始化MySQL数据库连接（非连接池版本）
        配置参数示例：
        {
            "host": "localhost",
            "user": "root",
            "password": "123456",
            "database": "test_db",
            "port": 3306,
            "charset": "utf8mb4",
            "autocommit": False
        }
        """
        self.config = self._validate_config(config)
        self.conn = None
        self.transaction_active = False
        self._lock = threading.Lock()  # 线程安全锁
        self._connect()

    def _validate_config(self, config: Dict) -> Dict:
        """验证并标准化配置参数"""
        required_keys = ['host', 'user', 'password', 'database']
        for key in required_keys:
            if key not in config:
                raise ValueError(f"Missing required config key: {key}")

        # 类型转换
        config['port'] = int(config.get('port', 3306))
        config['autocommit'] = config.get('autocommit', False)
        config['auth_plugin'] = config.get('auth_plugin', 'mysql_native_password')

        # 强制移除连接池参数
        config.pop('pool_size', None)
        config.pop('pool_name', None)

        # 字符集处理
        if 'charset' not in config:
            config['charset'] = 'utf8mb4'

        return config

    def _connect(self):
        """建立数据库连接（强制直连模式）"""
        try:
            self.conn = mysql.connector.connect(
                use_pure=True,  # 强制使用纯Python驱动，关键参数！！！
                **self.config
            )
            # logger.info(f"Connected to {self.config['host']}:{self.config['port']}")
        except Error as e:
            logger.error(f"Connection failed: {str(e)}")
            raise ConnectionError(f"Database connection error: {str(e)}") from e

    def _ensure_connection(self):
        """确保连接有效（增加心跳检测）"""
        if self.conn and self.conn.is_connected():
            try:
                with self._lock:
                    cursor = self.conn.cursor()
                    cursor.execute("SELECT 1")  # 心跳查询
                    cursor.close()
                return
            except Error:
                pass

        # logger.warning("Connection lost, reconnecting...")
        self._connect()

    @contextmanager
    def transaction(self):
        """
        事务上下文管理器
        使用示例：
        with db.transaction():
            db.execute(...)
            db.insert(...)
        """
        self._ensure_connection()
        try:
            self.conn.start_transaction()
            self.transaction_active = True
            yield
            self.conn.commit()
            logger.debug("Transaction committed")
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Transaction rolled back: {str(e)}")
            raise
        finally:
            self.transaction_active = False

    def execute(self, sql: str, params: Optional[Tuple] = None) -> int:
        """
        执行非查询SQL语句
        :return: 受影响的行数
        """
        cursor = None
        try:
            self._ensure_connection()
            cursor = self.conn.cursor()
            cursor.execute(sql, params or ())

            if not self.transaction_active:
                self.conn.commit()

            return cursor.rowcount
        except Error as e:
            self._handle_error(e, sql, params)
        finally:
            if cursor:
                cursor.close()

    def query(self, sql: str, params: Optional[Tuple] = None, auto_convert: bool = True) -> List[Dict]:
        """
        执行查询语句
        :param sql: 查询语句
        :param params: 查询语句参数
        :param auto_convert: 是否自动转换数据类型
        :return: 包含字典的列表，字典键为字段名

        """
        cursor = None
        try:
            self._ensure_connection()
            cursor = self.conn.cursor(dictionary=True)
            cursor.execute(sql, params or ())
            raw_results = cursor.fetchall()

            return [self._convert_row(row) for row in raw_results] if auto_convert else raw_results
        except Error as e:
            self._handle_error(e, sql, params)
        finally:
            if cursor:
                cursor.close()

    def _convert_row(self, row: Dict) -> Dict:
        """转换单行数据类型（增强版）"""
        converted = {}
        for key, value in row.items():
            if isinstance(value, Decimal):
                converted[key] = float(value)
            elif isinstance(value, datetime):
                converted[key] = value.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(value, date):
                converted[key] = value.strftime("%Y-%m-%d")
            elif isinstance(value, time):
                converted[key] = value.strftime("%H:%M:%S")
            elif isinstance(value, bytes):
                converted[key] = value.hex() if value else None
            else:
                converted[key] = value
        return converted

    def _handle_error(self, error: Error, sql: str, params: Tuple):
        """统一错误处理"""
        error_info = {
            "errno": error.errno,
            "sqlstate": error.sqlstate,
            "message": error.msg,
            "query": sql,
            "params": params
        }
        logger.error(f"Database error occurred: {error_info}")

        # 连接相关错误自动重连
        if error.errno in (errorcode.CR_SERVER_LOST, errorcode.CR_CONN_HOST_ERROR):
            logger.warning("Attempting to reconnect...")
            self._connect()

        raise DatabaseError(error_info) from error

    # CRUD/增删改查快捷方法 --------------------------------------------------------
    def insert(self, table: str, data: Dict) -> int:
        """插入单条数据"""
        columns = ', '.join([f'`{k}`' for k in data.keys()])
        placeholders = ', '.join(['%s'] * len(data))
        sql = f"INSERT INTO `{table}` ({columns}) VALUES ({placeholders})"
        return self.execute(sql, tuple(data.values()))

    def insert_many(self, table: str, columns: List[str], data: List[Tuple]) -> int:
        """批量插入数据（优化版）"""
        if not data:
            return 0
        cursor = None
        try:
            self._ensure_connection()
            with self._lock, self.conn.cursor() as cursor:
                placeholders = ', '.join(['%s'] * len(columns))
                sql = f"INSERT INTO `{table}` ({', '.join(columns)}) VALUES ({placeholders})"

                cursor.executemany(sql, data)
                rowcount = cursor.rowcount

                if not self.transaction_active:
                    self.conn.commit()

                return rowcount
        except Error as e:
            self._handle_error(e, sql, None)

    def update(self, table: str, data: Dict, where: Dict) -> int:
        """更新数据"""
        set_clause = ', '.join([f'`{k}` = %s' for k in data.keys()])
        where_clause = ' AND '.join([f'`{k}` = %s' for k in where.keys()])
        sql = f"UPDATE `{table}` SET {set_clause} WHERE {where_clause}"
        params = tuple(data.values()) + tuple(where.values())
        return self.execute(sql, params)

    def delete(self, table: str, where: Dict) -> int:
        """增强版删除方法，支持运算符和列表值"""
        where_clause = []
        params = []

        for key, value in where.items():
            operator = '='
            field = key

            if '__' in key:
                field, operator = key.split('__', 1)

            operator_map = {
                'gt': '>', 'lt': '<',
                'gte': '>=', 'lte': '<=',
                'ne': '!=', 'in': 'IN',
                'like': 'LIKE', 'is': 'IS'
            }
            op = operator_map.get(operator.lower(), '=')

            if op.upper() == 'IN':
                if not isinstance(value, (list, tuple)):
                    raise ValueError(f"IN operator requires iterable value, got {type(value)}")
                placeholders = ', '.join(['%s'] * len(value))
                where_clause.append(f"`{field}` IN ({placeholders})")
                params.extend(value)
            elif op.upper() == 'LIKE':
                where_clause.append(f"`{field}` LIKE %s")
                params.append(value)
            else:
                where_clause.append(f"`{field}` {op} %s")
                params.append(value)

        sql = f"DELETE FROM `{table}`"
        if where_clause:
            sql += f" WHERE {' AND '.join(where_clause)}"

        return self.execute(sql, tuple(params))

    def get_table_columns(self, table: str) -> List[str]:
        """获取表字段列表"""
        sql = f"DESCRIBE `{table}`"
        result = self.query(sql, auto_convert=False)
        return [row['Field'] for row in result]

    def close(self):
        """关闭连接"""
        if self.conn and self.conn.is_connected():
            self.conn.close()
            # logger.info("Database connection closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class DatabaseError(Exception):
    """自定义数据库异常"""

    def __init__(self, error_info: Dict):
        self.error_info = error_info
        super().__init__(str(error_info))


class MySQLDBExecutor:
    # 允许调用的安全方法白名单
    ALLOWED_METHODS = {
        'execute', 'query', 'insert',
        'insert_many', 'update', 'delete',
        'get_table_columns'
    }

    def __init__(self, db: MySQLDB):
        self.db = db

    def execute_from_config(self, config: Union[str, Dict]) -> Any:
        """
        根据配置执行数据库操作
        配置格式示例：
        1. 字符串格式："method_name:param1:param2"
        2. 字典格式：
           {
               "method": "update",
               "args": ["users", {"name": "John"}],
               "kwargs": {"where": {"id": 1}}
           }
        """
        if isinstance(config, str):
            return self._execute_str(config)
        elif isinstance(config, dict):
            return self._execute_dict(config)
        else:
            raise TypeError("配置必须是字符串或字典类型")

    def _safe_parse_args(self, args_str: str):
        """安全参数解析（仅允许基本JSON类型）"""
        try:
            return json.loads(args_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {str(e)}") from e

    def _validate_config(self, config: dict):
        # 必须包含method字段
        if 'method' not in config:
            raise KeyError("配置必须包含'method'字段")

        # 如果存在args则必须是列表
        if 'args' in config and not isinstance(config['args'], (list, tuple)):
            raise TypeError("'args'必须是列表或元组")

        # 如果存在kwargs则必须是字典
        if 'kwargs' in config and not isinstance(config['kwargs'], dict):
            raise TypeError("'kwargs'必须是字典")

    def _execute_str(self, config_str: str) -> Any:
        """处理字符串格式配置（增强版）"""
        parts = config_str.split('|', 1)
        method_name = parts[0].strip()

        if len(parts) == 1:
            return self._call_method(method_name, [], {})

        try:
            args_section = json.loads(parts[1].strip())

            if isinstance(args_section, dict):
                args = args_section.get('args', [])
                kwargs = args_section.get('kwargs', {})
            elif isinstance(args_section, list):
                args = args_section
                kwargs = {}
            else:
                raise ValueError("Invalid arguments format")

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in arguments: {str(e)}") from e

        return self._call_method(method_name, args, kwargs)

    def _execute_dict(self, config_dict: Dict) -> Any:
        """处理字典格式配置"""
        # 新增验证步骤
        self._validate_config(config_dict)
        method_name = config_dict.get('method')
        args = config_dict.get('args', [])
        kwargs = config_dict.get('kwargs', {})
        return self._call_method(method_name, args, kwargs)

    def _call_method(self, method_name: str, args: List, kwargs: Dict) -> Any:
        """安全执行方法"""
        # 安全检查
        if method_name not in self.ALLOWED_METHODS:
            raise ValueError(f"禁止调用方法：{method_name}")

        method = getattr(self.db, method_name, None)
        if not callable(method):
            raise AttributeError(f"方法不存在或不可调用：{method_name}")

        # 参数验证
        sig = inspect.signature(method)
        try:
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
        except TypeError as e:
            raise ValueError(f"参数错误：{str(e)}")

        # 执行方法
        return method(*args, **kwargs)

    def close(self):
        self.db.close()


class DBConnector:
    def __init__(self, config_dict=None):
        """
        数据库管理器
        :param config_path: YAML配置文件路径
        """
        self._dbs = {}
        if not config_dict and env.__getattr__('mysql'):
            self.config_dict = env.configs['mysql']
        else:
            self.config_dict = config_dict
        self.load_config(self.config_dict)

    def load_config(self, config_dict: dict):
        """加载并初始化数据库配置"""

        if not config_dict:
            logger.warning(f'配置文件中缺少mysql字段或配置为空')
            return
        for db_name, db_config in config_dict.items():
            # 自动添加默认端口
            if 'port' not in db_config:
                db_config['port'] = 3306
            # 创建数据库实例
            db_obj = MySQLDB(db_config)
            db_executor = MySQLDBExecutor(db_obj)
            self._dbs[db_name] = db_executor
            # 动态添加实例属性
            setattr(self, db_name, self._dbs[db_name])
            # 添加全局变量
            logger.info(f'初始化DBConnector, db_name: {db_name}')
            Variable(db_name).Value = ''
            Variable(f'{db_name}_output').Value = ''

    def get_all_instances(self) -> dict:
        """获取所有数据库实例"""
        return self._dbs

    def close_all(self):
        """关闭所有数据库连接"""
        for db in self._dbs.values():
            db.close()

    def execute(self, signal: Variable):
        try:
            db_name = signal.name
            executor = getattr(self, db_name)
            logger.info(f'发送DBConnector消息: {db_name} = {signal.Value}')
            res = executor.execute_from_config(signal.Value)
            db_output_signal_name = f'{db_name}_output'
            Variable(db_output_signal_name).Value = res
            logger.info(f'接收DBConnector消息: {db_output_signal_name} = {res}')
        except:
            logger.error(traceback.format_exc())


# 使用示例
if __name__ == "__main__":
    # config = {
    #     "mysql": {
    #         "db_bsp_dcl": {
    #             "host": "ob-public01-test-40110.inner.chj.cloud",
    #             "user": "bsp_dcl_rw@public#ob_public01_test_40110",
    #             "password": "%BhE4L@6KAu3B!3Vi+L",
    #             "database": "bsp_dcl",
    #             "port": 13307,
    #             "charset": "utf8mb4",
    #             "pool_size": 5
    #         }
    #     }
    # }

    # logger.info(config['mysql']['db_bsp_dcl'])
    # db = MySQLDB(config['mysql']['db_bsp_dcl'])
    # try:
    #     # 创建测试表
    #     # db.execute("""
    #     #     CREATE TABLE IF NOT EXISTS users (
    #     #         id INT AUTO_INCREMENT PRIMARY KEY,
    #     #         name VARCHAR(255) NOT NULL,
    #     #         email VARCHAR(255) UNIQUE NOT NULL,
    #     #         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    #     #     )
    #     # """)
    #
    #     # 插入数据
    #     # user_id = db.insert("users", {
    #     #     "name": "Alice",
    #     #     "email": "alice@example.com"
    #     # })
    #
    #     # 批量插入
    #     # db.insert_many("users", ["name", "email"], [
    #     #     ("Bob", "bob@example.com"),
    #     #     ("Charlie", "charlie@example.com")
    #     # ])
    #     # 查询数据
    #     result = db.query("SELECT * FROM gis_slip_position_point_info WHERE id=1")
    #     print("Query results:", result)
    #     # 更新数据
    #     # db.update("users", {"name": "Alice Smith"}, {"email": "alice@example.com"})
    #
    #     # 事务处理
    #     # with db.transaction():
    #     #     db.delete("users", {"email": "bob@example.com"})
    #     #     db.update("users", {"name": "Charlie Brown"}, {"email": "charlie@example.com"})
    #     #
    #     # # 验证事务
    #     # print("After transaction:", db.query("SELECT * FROM users"))
    # finally:
    #     db.close()

    # 测试 DBConnector
    db_connector = DBConnector()

    try:
        signal = Variable('db_bsp_dcl')
        # 简单查询示例
        signal.Value = 'query|["select * from gis_slip_position_point_info where id=%s",[1]]'
        db_connector.execute(signal)

        # 简单删除示例
        signal.Value = {
            "method": "delete",
            "args": ["gis_slip_position_point_info"],
            "kwargs": {
                "where": {"id": 12}
            }
        }
        db_connector.execute(signal)

        # 多条件删除语句
        signal.Value = {
            "method": "delete",
            "args": ["gis_slip_position_point_info"],
            "kwargs": {
                "where": {
                    "gps_lat__gte": 0,  # lat >= 1
                    "gps_lat__lte": 30,  # lat <= 2
                    "gps_lon__gte": 0,  # lon >= 1
                    "gps_lon__lte": 107  # lon <= 2
                }
            }
        }
        db_connector.execute(signal)

        # 条件更新语句
        signal.Value = {
            "method": "update",
            "args": ["gis_slip_position_point_info"],
            "kwargs": {
                "data": {"nums": 2},
                "where": {
                    "gps_lat": 39.23858500,
                    "gps_lon": 117.65125800,
                }  # id:18
            }
        }
        db_connector.execute(signal)
    finally:
        db_connector.close_all()

    s = Variable('db_bsp_dcl_output')
    print(type(s.Value))
    # print(s.Value[0]['life_cycle'])
    # print(s.Value[0]['life_cycle'] == 0)
    # print(s.Value[0]['adhesive_using_rate'])
    # print(s.Value[0]['adhesive_using_rate'] == Decimal('0.5325'))
    # print(s.Value[0]['gps_lon'])
    # print(s.Value[0]['gps_lon'] == Decimal('117.38664200'))
