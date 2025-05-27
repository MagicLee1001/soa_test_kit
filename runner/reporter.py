def generate_test_result_html(test_infos):
    html_content = """
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {
                font-family: Arial, sans-serif;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 20px;
            }
            th, td {
                border: 1px solid black;
                padding: 8px;
                text-align: left;
            }
            .pass {
                background-color: #ddffdd;
            }
            .fail {
                background-color: #ffdddd;
            }
            .test-title {
                cursor: pointer;
                padding: 10px;
                margin: 10px 0;
                border-radius: 5px;
                background-color: #aed581;
                border: 1px solid #8bc34a;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .test-title:hover {
                background-color: #8bc34a;
            }
            .test-content {
                display: none;
                margin-top: 10px;
                border-radius: 5px;
                border: 1px solid #8bc34a;
                padding: 10px;
                background-color: #f5f5f5;
            }
            .test-case.fail .test-title {
                background-color: #ff9999;
                border-color: #ff3333;
            }
            .test-case.fail .test-title:hover {
                background-color: #ff6666;
            }
            .test-case.fail .test-content {
                border-color: #ff3333;
            }
        </style>
        <script>
            function toggleDisplay(id) {
                var content = document.getElementById(id);
                if (content.style.display === "none" || !content.style.display) {
                    content.style.display = "block";
                } else {
                    content.style.display = "none";
                }
            }
        </script>
    </head>
    <body>
    """

    for index, test_info in enumerate(test_infos):
        result_class = "fail" if not test_info.tc_ret else "pass"
        html_content += f"""
        <div class="test-case {result_class}">
            <div class="test-title" onclick="toggleDisplay('tc_{index}')">
                <span>{test_info.tc_name} - {test_info.tc_title}</span>
                <span>{test_info.test_time}</span>
            </div>
            <div id="tc_{index}" class="test-content">
                <p>测试时间: {test_info.test_time}</p>
                <table>
                    <tr>
                        <th>Step</th>
                        <th>Time</th>
                        <th>Heading</th>
                        <th>Actions</th>
                        <th>Wait Condition</th>
                        <th>Pass Condition</th>
                        <th>Evaluation Condition</th>
                        <th>Status</th>
                    </tr>
        """

        for step in test_info.tc_steps:
            result_class = "pass" if step.step_ret else "fail"
            actions_str = "<br>".join(step.actions)
            pass_conditions_str = "<br>".join(step.pass_condition)
            # evaluation_condition_str = "<br>".join(step.evaluation_condition)
            # 修改开始：添加长度截断逻辑
            evaluation_condition_str = "<br>".join(
                [f"{elem[:100]}..." if len(elem) > 100 else elem
                 for elem in step.evaluation_condition]
            )
            html_content += f"""
            <tr class="{result_class}">
                <td>{step.row_number}</td>
                <td>{step.test_time}</td>
                <td>{step.heading if step.heading  else ''}</td>
                <td>{actions_str}</td>
                <td>{step.wait_condition}</td>
                <td>{pass_conditions_str}</td>
                <td>{evaluation_condition_str}</td>
                <td>{"Pass" if step.step_ret else "Fail"}</td>
            </tr>
            """

        html_content += """
                </table>
            </div>
        </div>
        """

    html_content += """
    </body>
    </html>
    """

    return html_content


if __name__ == '__main__':
    # 示例数据
    from runner.tester import TestStep, TestInfo
    test_step1 = TestStep(
        pre_condition="LowVolPwrMd=1",
        actions=["MDL_UnlockButton = 1"],
        wait_condition="1.0",
        pass_condition=["LowVolPwrMd=1.0", "LowVolPwrMdFlag=0"],
        hold_condition="",
        row_number=1,
        heading="低压电源模式ACC"
    )
    test_step1.evaluation_condition = ["LowVolPwrMd=1.0", "LowVolPwrMdFlag=0"]
    test_step1.test_time = "1.0"
    test_step1.step_ret = True

    test_step2 = TestStep(
        pre_condition="",
        actions=["MDL_UnlockButton = 0"],
        wait_condition="0.1",
        pass_condition=["MSG_LRvrwMirFoldSts=0", "MSG_LMirFoldMotFt=0"],
        hold_condition="",
        row_number=2,
        heading=""
    )
    test_step2.evaluation_condition = ["MSG_LRvrwMirFoldSts=0", "MSG_LMirFoldMotFt=0"]
    test_step2.test_time = "1.5"
    test_step2.step_ret = False

    test_info1 = TestInfo("TC1", [test_step1, test_step2], False, "测试用例1")

    test_step3 = TestStep(
        pre_condition="",
        actions=["MDL_UnlockButton = 1", "MDL_UnlockButton = 0"],
        wait_condition="0.5",
        pass_condition=["MSG_LRvrwMirFoldSts=0"],
        hold_condition="MSG_LRvrwMirFoldSts",
        row_number=3,
        heading="正常情况下"
    )
    test_step3.evaluation_condition = ["MSG_LRvrwMirFoldSts=0"]
    test_step3.test_time = "2.0"
    test_step3.step_ret = True

    test_info2 = TestInfo("TC2", [test_step3], True, "测试用例2")

    # 生成 HTML
    html_result = generate_test_result_html([test_info1, test_info2])
    print(html_result)
    with open('reporter.html', 'w', encoding='utf-8') as f:
        f.write(html_result)
