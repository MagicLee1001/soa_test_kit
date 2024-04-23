# soa_test_kit

<author>likun likun19941001@163.com</author>

## 项目描述
面向服务架构自动化测试框架, 软件

## 环境依赖
Python 3.11.7 (tags/v3.11.7:fa7a6f2, Dec  4 2023, 19:24:49) [MSC v.1937 64 bit (AMD64)] on win32

## 环境配置
- 进入项目根目录
    ```
    cd soa_test_kit
    ```
- 安装依赖库
    ```
    pip install -r .\requirements.txt
    ```
- 测试配置文件
    ```
    .\settings.py
    ```
- DDS 信号列表
    ```
    sub_topics、pub_topics
    ```
- DBO 测试矩阵
    ```
    固定路径: .\data\matrix\dbc_lin_matrix.dbo
    ```
- DDS SOA矩阵
    ```
    固定路径: .\data\matrix\rti_xxx.xml
    ```
- 测试用例路径
    ```
    默认路径: .\data\case
    ```
- 同信号不同Topic
    ```
   signals_one2many： 如果SOA idl矩阵中存在不同topic下信号名相同的情况，则将此类型的信号名放到yaml配置文件中进行维护
   自动/手动测试输入（输出）信号中，此信号名加topic的后缀，格式变更为 signal_name_[topic_name]_
   signals_one2many:
    - srv_control_source_
    - srv_request_id_
    - srv_time_
    - msg_rr_acblow_vol_fdbk_
    - msg_blwr_vol_fdbk_
    - msg_en_clnt_temp_
    ```
- 测试报告路径
    ```
    默认路径: .\data\result
    ```

## 用例说明
1. 信号规范
    ```
    常规信号
    Pub_        : DDS消息，Topic下的DDS信号格式，大多为要发布的信号（也可用来订阅）
    Sub_        : DDS消息，Topic下的DDS信号格式，大多为要订阅的信号（也可用来发布）
    Recv_        : sil服务通过TCP协议send的消息，测试环境recv
    Send_        : 测试环境通过TCP协议send的消息，sil服务recv
    sql3_       : vcs数据库的信号，用于PassConditons校验，后面跟vcs信号名
    sql3_switch : 当前步骤Actions中触发一次查询vcs数据库操作，如: sql3_switch=1
    sql3_write_ : 当前步骤Actions中触发一次修改vcs数据库操作，后面跟vcs信号名
    
    特殊信号
    Sw_HandWakeup      : 当前测试环境不检查连接 无实际意义
    SIL_Client_CnnctSt : 当前测试环境不检查连接 无实际意义
    
    ```
2. 用例语法
    ```
    Actions字段中信号定义:
    Pub_, Sub_, Send_: 均表示给被测对象发送消息
    Recv_: 表示将当前测试环境中 A2M信号变量重新赋值（通常用于比较信号是否变化的前置条件）
    sql3_switch: 用于一次查询vcs数据库的操作，值为任意（默认为 1）
    sql3_write_: 用于一次修改vcs数据库的操作
   
    PassContions字段中信号定义:
    Pub_, Sub_, Recv_: 均表示接收被测对象发来的消息
    sql3_: 用于比较vcs数据库中存储的信号，要获取当前最新的信号值则需要在Actions中通过 sql3_switch动作触发
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
        a. SignalNotFound            -- 信号名不对（未在矩阵中或vcsDB中找到）
        b. SignalsTopicNotSame       -- 这一组dds的信号不在同一topic下
        c. SignalValueConvertError   -- 信号值不对导致转换失败
        d. SignalFormatError         -- 用例中的信号格式没写对（见:用例说明-信号规范）
        e. PassConditionFormatError  -- passcondition条件语句语法错误
        f. {SignalName}=={RealValue} -- 这里给出实际与预期信号不匹配的值
   ```
