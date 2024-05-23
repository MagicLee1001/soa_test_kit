# SOA Test Kit

<author>李琨</author>

## 项目描述
SOA-SiL测试框架,适配车机系统域间通信DDS、TCP测试

## 环境依赖
Python 3.11.7 (tags/v3.11.7:fa7a6f2, Dec  4 2023, 19:24:49) [MSC v.1937 64 bit (AMD64)] on win32

## 环境配置
- 进入项目根目录
    ```
    cd autoli-sil-xbp
    ```
- 安装依赖库
    ```
    pip install -r .\requirements.txt
    ```
- 测试配置文件
    ```
    .\settings.py
    ```
- DBO 矩阵文件
    ```
    固定路径: .\data\matrix\dbc_lin_dbis_matrix.dbo
    ```
- DDS idl文件
    ```
    固定路径: .\data\matrix\XBP.xml
    ```
- 测试用例路径
    ```
    默认路径: .\data\case
    ```
- 测试报告路径
    ```
    默认路径: .\data\result
    ```

## 用例说明
1. 信号规范
    ```
    常规信号
    SRV_        : DDS消息，Topic下的DDS信号格式，大多为要发布的信号（也可用来订阅）
    MSG_        : DDS消息，Topic下的DDS信号格式，大多为要订阅的信号（也可用来发布）
    A2M_        : sil服务通过TCP协议send的消息，测试环境recv
    M2A_        : 测试环境通过TCP协议send的消息，sil服务recv
    sql3_       : vcs数据库的信号，用于PassConditons校验，后面跟vcs信号名
    sql3_switch : 当前步骤Actions中触发一次查询vcs数据库操作，如: sql3_switch=1
    sql3_write_ : 当前步骤Actions中触发一次修改vcs数据库操作，后面跟vcs信号名
    
    特殊信号
    Sw_HandWakeup       : 当前测试环境不检查连接 无实际意义
    SIL_Client_CnnctSt  : 当前测试环境不检查连接 无实际意义
    SIL_VMS_            : 后接ECU名称，模拟ECU仿真车辆模式切换的响应结果 0 表示成功；1 表示失败
    ssh_exec_cmd        : 执行ssh终端命令
    ssh_interactive_cmd : 执行ssh交互式命令
    ssh_exec_output     : ssh终端命令的输出
    ```
2. 用例语法
    ```
    Actions字段中信号定义:
    SRV_, MSG_, M2A_    : 均表示给被测对象发送消息
    A2M_                : 表示将当前测试环境中 A2M信号变量重新赋值（通常用于比较信号是否变化的前置条件）
    sql3_switch         : 用于一次查询vcs数据库的操作，值为任意（默认为 1）
    sql3_write_         : 用于一次修改vcs数据库的操作
    ssh_exec_cmd        : 执行一次ssh终端命令 后面不可接';'字符
    ssh_interactive_cmd : 执行一次ssh交互式命令 默认超时时间为10秒
   
    PassContions字段中信号定义:
    SRV_, MSG_, A2M_: 均表示接收被测对象发来的消息
    sql3_: 用于比较vcs数据库中存储的信号，要获取当前最新的信号值则需要在Actions中通过 sql3_switch动作触发
    ```

## 测试执行
测试开始时程序会自动更新当前dbo矩阵配置，检测与自动部署sil服务到目标系统中，无需手动操作

1. 检查当前dds矩阵文件是否适配
    ```
    .\data\matrix\XBP.xml
    ```
2. 维护当前dds环境变量（不能漏写,可以多写）
    ```
    settings.py -> sub_topics、pub_topics 
    ```
3. 维护当前用例集路径（默认该文件夹下的所有用例）
    ```
    settings.py -> case_dir
    ```
4. 执行测试脚本（注意脚本是unittest框架）
    ```
    python ./test_sil_xbp.py
    ```

## 测试结果
1. 测试报告路径
    ```
    .\result\{YmdHMS}\TestReport_SOA_SIL_xx.html
    ```
2. 报告说明
    ```
   1. 一个报告表示一个整个测试集
   2. 报告中每一条表示一个测试用例表的运行结果
   3. 每个用例表任意TC执行失败则显示失败，点击失败可查看失败详情
   4. 失败详情中会给出失败原因,其中包括:
        a. SignalNotFound            -- 信号名格式正确但不存在当前环境中（未在SOA矩阵、vcsDB、车辆模式信号中找到）
        b. SignalFormatError         -- 信号名格式错误（见:用例说明-信号规范）; 2024-05-15版本以后已取消
        c. SignalsTopicNotSame       -- 用例中一组dds的信号不在同一topic下; 2024-05-15版本以后已取消
        d. SignalValueConvertError   -- 信号值不对导致转换失败
        e. PassConditionFormatError  -- passcondition条件语句语法错误
        f. {SignalName}=={RealValue} -- 这里给出实际与预期信号不匹配的值
   ```
