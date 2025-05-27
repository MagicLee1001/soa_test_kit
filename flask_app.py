# -*- coding: utf-8 -*-
# @Author  : Li Kun
# @Time    : 2024/7/19 15:10
# @File    : flask_app.py

import traceback
from flask import Flask, request, jsonify
from settings import env
from runner.variable import Variable
from runner.log import logger

app = Flask(__name__)


def create_response(status=200, message="Success", data=None, errors=None):
    response = {
        "status": status,
        "message": message,
        "data": data,
        "errors": errors
    }
    return jsonify(response), status


@app.route('/soa/api/v1/env/load', methods=['POST'])
def load_env():
    filepath = request.values.get('filepath')
    try:
        env.load(filepath)
        return create_response(
            status=200,
            message='success',
            data={}
        )
    except Exception as e:
        return create_response(
            status=500,
            message="Internal Server Error",
            errors=[{"message": str(e)}]
        )


@app.route('/soa/api/v1/variable/get', methods=['GET'])
def get_signal_value():
    signal_names = request.get_json().get('signal_names')
    try:
        return create_response(
            status=200,
            message='success',
            data=[
                {
                    'signal_name': signal_name,
                    'signal_value': Variable(signal_name).Value
                } for signal_name in signal_names
            ]
        )
    except Exception as e:
        return create_response(
            status=500,
            message="Internal Server Error",
            errors=[{"message": str(e)}]
        )


@app.route('/soa/api/v1/variable/set', methods=['POST'])
def set_signal_value():
    signals = request.get_json()
    try:
        for signal in signals:
            Variable(signal['signal_name']).Value = signal['signal_value']
        return create_response(
            status=200,
            message='success',
            data={}
        )
    except Exception as e:
        return create_response(
            status=500,
            message="Internal Server Error",
            errors=[{"message": str(e)}]
        )


@app.route('/soa/api/v1/message/send', methods=['POST'])
def send_msg():
    signals = request.get_json().get('signals')
    try:
        for signal_dict in signals:
            signal = Variable(signal_dict['signal_name'])
            signal.Value = signal_dict['signal_value']
            env.tester.send_single_msg(signal)
        return create_response(
            status=200,
            message='success',
            data={}
        )
    except Exception as e:
        logger.error(traceback.format_exc())
        return create_response(
            status=500,
            message="Internal Server Error",
            errors=[{"message": str(e)}]
        )


@app.route('/soa/api/v1/message/multi-send', methods=['POST'])
def multi_send_msg():
    signal_info = request.get_json()
    try:
        topic_name = signal_info.get('topic_name')
        if topic_name:
            signals = []
            signal_list = signal_info.get('signals')
            for signal_dict in signal_list:
                signal = Variable(signal_dict['signal_name'])
                signal.Value = signal_dict['signal_value']
                signals.append(signal)
            env.tester.dds_connector.dds_multi_send(topic_name, signals)
        return create_response(
            status=200,
            message='success',
            data={}
        )
    except Exception as e:
        logger.error(traceback.format_exc())
        return create_response(
            status=500,
            message="Internal Server Error",
            errors=[{"message": str(e)}]
        )


if __name__ == '__main__':
    app.run(port=61007, threaded=True)
