# SOA Test Kit

<author>李琨</author>

## 项目描述
SOA(面向服务架构)测试框架,适配汽车（新能源）车机系统域间通信（包括DDS、SSH、TCP、DoIP、XCP、HTTP等协议类型）和功能测试

## 环境依赖
Python 3.11.7 (tags/v3.11.7:fa7a6f2, Dec  4 2023, 19:24:49) [MSC v.1937 64 bit (AMD64)] on win32

## 软件架构
![Alt text]()

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
- DBO 矩阵文件
    ```
    固定路径: .\data\matrix\dbc_lin_dbis_matrix.dbo
    ```
- DDS idl文件
    ```
    固定路径: .\data\matrix\rti_xap.xml
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
    # 常规信号
    SRV_        : (输入/输出信号) DDS消息，Topic下的DDS信号格式，大多为要发布的信号（也可用来订阅）
    MSG_        : (输入/输出信号) DDS消息，Topic下的DDS信号格式，大多为要订阅的信号（也可用来发布）
    A2M_        : (输出信号) sil服务通过TCP协议send的消息，测试环境recv
    A2A_        : (输入信号) 测试环境通过TCP协议send的消息，sil服务recv
    M2A_        : (输入信号) 测试环境通过TCP协议send的消息，sil服务recv
    
    # 进程数据库操作信号，服务名当前支持: vcs、rule; dataType支持: i:int,d:double,s:string类型·
    sql3_       : (输出信号) 格式为sql3_{serviceName}_{dataType}_{signalName}，进程数据库的信号，如：sql3_vcs_s_configword，用于PassConditons校验
    sql3_switch : (输入信号) 格式为sql3_swtich_{serviceName}_{dataType}，触发一次查询数据库操作，如: sql3_switch_vcs_i=1
    sql3_write_ : (输入信号) 格式为sql3_write_{service}_{dataType}_{signalName}，触发一次修改数据库操作
    
    # 特殊信号
    Sw_HandWakeup       : 当前测试环境不检查连接 无实际意义
    SIL_Client_CnnctSt  : 当前测试环境不检查连接 无实际意义
    SIL_VMS_            :（输出信号）后接ECU名称，模拟ECU仿真车辆模式切换的响应结果 0 表示成功；1 表示失败
    
    # ssh信号（命令）
    ssh_exec_cmd          :（输入信号）执行ssh终端命令，如 ssh_exec_cmd = "date"
    ssh_exec_output       :（输出信号）ssh终端命令的输出
    ssh_interactive_cmd   :（输入信号）执行ssh交互式命令；如果信号值为0，则表示停止执行
    ssh_interactive_output:（输出信号）ssh交互式命令的输出，比如lilogcat日志
    ssh_sftp_put          : (输入信号) ssh本地文件上传到远端，值为dict类型，{"remote": "远端文件路径"， "local": "本地文件路径"}
    ssh_sftp_get          : (输入信号) ssh远端文件下载到本地，值为dict类型，同上
    
    # vss交互信号
    vssSet_             :（输入信号）vss信号的输出值，下划线后面跟信号路径，信号值类型分int和string/json
    vss_get             :（输入信号) 信号值为vss信号路径名称，表示获取一次当前信号最新的值
    vss_                :（输出信号）vss信号的输出值，下划线后面跟信号路径
    vssTS_              :（输出信号）vss信号的更新时间戳，下划线后面跟信号路径
    vssMask_            :（输出信号）vss信号输出值掩码，下划线后面跟信号路径，-9999则表示信号值无变化，非有效值；正常情况跟vss_值一致
    
    # doipclient信号
    * doip_req   表示单次诊断请求
    * doip_proc_ 表示完整的诊断流程
    
    doip_req                   : (输入信号) 单次诊断请求，hex_str格式，值为DoIP-payload中的： 目标逻辑地址 + 诊断数据, 如 0c01190201，0c0122f1a1
    doip_proc_write_did        : (输入信号) hex_str格式，值为did+data，如 f1a10150110634fbff6bfc1c3fff01e3e20fff
    doip_proc_read_did         : (输入信号) hex_int格式，值为did，如 0xf1a1
    doip_proc_read_dtc         : (输入信号) hex_int格式，值为sid，如 0x0201
    doip_proc_ecu_reset        : (输入信号) hex_int格式，值为重启类型，如 0x01、0x02 ...
    doip_proc_security_access  : (输入信号) hex_int格式，值为安全等级，如 0x01、0x02
    doip_resp                  : (输出信号) hex_str格式，值为uds响应报文
    
    
    # xcp信号
    cal_read                  : (输入信号) 在值中填写观测量信号名，表示读取信号值，例如，信号：cal_read，值：VeCFG_CfgAcore_data[0]。
    cal_write_                : (输入信号) cal_write_ 后加上需要写入标定量的信号名，并在值中填写要写入的值，读取该信号的值，例如，信号：cal_write_KuVtmTmsd_IODID4EXV1PosThdUp_enum, 值：100。
    cal_                      : (输出信号) cal_后加上需要读取的观测量信号名，读取该信号的值，前缀cal_代表来自xcp的信号。例如，信号：cal_KuVtmTmsd_IODID4EXV1PosThdUp_enum
    
    
    # ccp信号
    can_cal_read                  : (输入信号) 在值中填写观测量信号名，表示读取信号值，例如，信号：can_cal_read，值：VeCFG_CfgAcore_data[0]。
    can_cal_write_                : (输入信号) can_cal_write_ 后加上需要写入标定量的信号名，并在值中填写要写入的值，读取该信号的值，例如，信号：can_cal_write_KuVtmTmsd_IODID4EXV1PosThdUp_enum, 值：100。
    can_cal_                      : (输出信号) can_cal_后加上需要读取的观测量信号名，读取该信号的值，前缀can_cal_代表来自ccp的信号。例如，信号：can_cal_KuVtmTmsd_IODID4EXV1PosThdUp_enum
    
    
    # db信号
    db_bsp_dcl                : (输入信号) 可以根据yaml配置文件yaml的mysql字段去配置数据库,值为数据库操作关系语句，语法如下：
                                1.条件查询： 
                                  query|["select * from gis_slip_position_point_info where id=%s",[1]]
                                2.简单删除：
                                  {
                                    "method": "delete",
                                    "args": ["gis_slip_position_point_info"],
                                    "kwargs": {
                                        "where": {"id": 12}
                                    }
                                  }
                                 3.多条件删除:
                                  {
                                    "method": "delete",
                                    "args": ["gis_slip_position_point_info"],
                                    "kwargs": {
                                        "where": {
                                            "gps_lat__gte": 0,
                                            "gps_lat__lte": 30,
                                            "gps_lon__gte": 0,
                                            "gps_lon__lte": 107
                                        }
                                    }
                                  }
                                  4.条件更新：
                                  {
                                    "method": "update",
                                    "args": ["gis_slip_position_point_info"],
                                    "kwargs": {
                                        "data": {"nums": 2},
                                        "where": {
                                            "gps_lat": 39.23858500,
                                            "gps_lon": 117.65125800
                                        }
                                    }
                                  }
    db_bsp_dcl_output               : (输出信号) 可以查看sql语句执行结果
    
    
    # 打滑预控信号
    httpReq_SlipControl             : (输入信号) http请求，1:表示请求打滑预控车端上报数据; 2:表示请求打滑预控云端指令下发数据
    httpResp_SlipControl_UploadData : (输出信号) http响应，打滑预控车端上报数据记录
    httpResp_SlipControl_JobData    : (输出信号) http响应，打滑预控云端指令下发记录
    bsp_SPID_AB_Inner               : (输出信号) http响应，打滑预控打滑ID
    bsp_SPLat_AB_Inner              : (输出信号) http响应，打滑预控车端上报打滑点经度
    bsp_SPLon_AB_Inner              : (输出信号) http响应，打滑预控车端上报打滑点纬度
    bsp_SPSta_AB_Inner              : (输出信号) http响应，打滑预控车端上报打滑状态
    bsp_SPAdh_AB_Inner              : (输出信号) http响应，打滑预控车端上报打滑附着利用率
    bsp_VehSlipTime_AB_Inner        : (输出信号) http响应，打滑预控车端上报打滑时长
    bsp_SlipPreCtrlSta_AB_Inner     : (输出信号) http响应，打滑预控车端上报打滑预控状态
    bsp_SlipPoints                  : (输出信号) http响应，打滑点信息
    bsp_SlipJobData_createTime      : (输出信号) http响应，打滑预控云端指令下发记录
    bsp_SlipUploadData_createTime   : (输出信号) http响应，打滑预控车端上报数据记录时间
    bsp_SlipPointsNum               : (输出信号) http响应，附近打滑点数
    
    # 诊断专家信号
    eid_fid_                        : (输入信号) 下划线后面跟信号名，模拟eid fid故障信号
    httpReq_DiagExpert_warnInfo     : (输入信号) http请求，1：表示请求roadsise_breakdown最新告警信息；2：表示请求flow_control告警信息
    httpReq_DiagExpert_treeInfo     : (输入信号) http请求，1：表示请求roadsize_breakdown故障树信息；2：表示请求flow_control故障树信息，
    httpResp_DiagExpert_warnInfo    : (输出信号) http响应，故障告警信息
    httpResp_DiagExpert_treeInfo    : (输出信号) http响应，故障树信息
    bsp_DiagExpert_warnId           : (输出信号) 最新故障告警id
    bsp_DiagExpert_treeName         : (输出信号) 最新故障树名称
    bsp_DiagExpert_treeNodeNames    : (输出信号) list类型，最新故障树子节点名称
    bsp_DiagExpert_treeNodeSignals  : (输出信号) dict类型，最新故障树子节点信号名、信号值
    bsp_DiagExpert_treeNodeSignal_  : (输出信号) 后跟故障树子节点信号名，如 bsp_DiagExpert_treeNodeSignal_XCUVehMd

    ```
2. 用例语法
   | SourceID | Object Type | Object Heading | Preconditions | Actions                                          | Wait Conditions | Pass Conditions | 
   | ---- | ---- | ---- | ---- |--------------------------------------------------| ---- | ---- | 
   | 1 | TestCase | SRD.Topic_WiperWshrStatus.002前雨刮电机驱动状态-- | |                                                  | |
   | | config | Sil Configuration | testCase=1|                                                  | | |
   | | Link | Init | |                                                  | | |
   | | Test step | | | Sw_HandWakeup = 1;                               | 1 | SIL_Client_CnnctSt==1 |
   | | Test step | | | M2A_ElWiperMotSpdFbk=1;  M2A_ElWiperMotSpdFbk=2; | 0.5 |  MSG_FrtWiperMotDrvSts==1 && MSG_FrtWiperMotDrvSts==1 |
   | | Test step | | | M2A_ElWiperMotSpdFbk=2;                          | 0.5 |  MSG_FrtWiperMotDrvSts==1 |
   | | Test step | | | M2A_ElWiperMotSpdFbk=3;                          | 0.5 |  MSG_FrtWiperMotDrvSts==1 |
   | | Test step | | | M2A_ElWiperMotSpdFbk=4;                          | 0.5 |  MSG_FrtWiperMotDrvSts==1 |
   
    ```
    # Actions字段中信号定义:
    一行代表一个测试步骤，支持写多个（;后接换行）。代表用户触发的动作、事件。书写格式为：
    信号名1=信号值1
    信号名2=信号值2
    
    SRV_, MSG_, M2A_    : 均表示给被测对象发送消息
    A2M_                : 表示将当前测试环境中 A2M信号变量重新赋值（通常用于比较信号是否变化的前置条件）
    sql3_switch         : 用于一次查询vcs数据库的操作，值为任意（默认为 1）
    sql3_write_         : 用于一次修改vcs数据库的操作
    ssh_exec_cmd        : 执行一次ssh终端命令 后面不可接';'字符
    ssh_interactive_cmd : 执行一次ssh交互式命令 默认超时时间为10秒
    ....  详情见信号规范
    
    # PassContions字段中信号定义:
    一行代表一个测试步骤，支持写多个（换行后接&&）。代表用户对结果的比较、判断意图
    
    SRV_, MSG_, A2M_: 均表示接收被测对象发来的消息
    sql3_: 用于比较vcs数据库中存储的信号，要获取当前最新的信号值则需要在Actions中通过 sql3_switch动作触发
    ...  详情见信号规范
    
    # PassConditions运算符
    当前支持python所有条件运算符，如：==、!=、>,还支持变量取值与索引符号，如 variable[1]["key"] == 
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
