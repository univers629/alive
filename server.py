#!/usr/bin/python3
# coding: utf-8
import utils as u
from data import data as data_init
from flask import Flask, render_template, request, url_for, redirect, flash, make_response
from markupsafe import escape
from zoneinfo import ZoneInfo
from datetime import datetime


d = data_init()
app = Flask(__name__)

# ---


def reterr(code, message):
    ret = {
        'success': False,
        'code': code,
        'message': message
    }
    u.error(f'{code} - {message}')
    return u.format_dict(ret)


def showip(req, msg):
    ip1 = req.remote_addr
    try:
        ip2 = req.headers['X-Forwarded-For']
        u.infon(f'- Request: {ip1} / {ip2} : {msg}')
    except:
        ip2 = None
        u.infon(f'- Request: {ip1} : {msg}')


@app.route('/')
def index():
    d.load()
    showip(request, '/')

    # 在访问每次页面时，检查日期是否变更，如果变更则重置访问次数
    d.reset_view_count_if_new_day()
    
    # 增加访问次数
    d.dset('view_count', d.dget('view_count') + 1)

    ot = d.data['other']
    try:
        stat = d.data['status_list'][d.data['status']]
        if(d.data['status'] == 0):
            app_name = d.data['app_name']
            stat['name'] = app_name
    except:
        stat = {
            'name': '未知',
            'desc': '未知的标识符，可能是配置问题。',
            'color': 'error'
        }

    last_updated = d.dget('last_updated')  # 获取上次更新时间
    view_count = d.dget('view_count')  # 获取今日已被观察次数
    
    return render_template(
        'index.html',
        user=ot['user'],
        learn_more=ot['learn_more'],
        repo=ot['repo'],
        status_name=stat['name'],
        status_desc=stat['desc'],
        status_color=stat['color'],
        more_text=ot['more_text'],
        last_updated=last_updated  # 传递 last_updated 变量
        view_count=view_count  # 传递访问次数
    )


@app.route('/style.css')
def style_css():
    response = make_response(render_template(
        'style.css',
        bg=d.data['other']['background'],
        alpha=d.data['other']['alpha']
    ))
    response.mimetype = 'text/css'
    return response


@app.route('/query')
def query():
    d.load()
    showip(request, '/query')
    st = d.data['status']
    # stlst = d.data['status_list']
    try:
        stinfo = d.data['status_list'][st]
        if(st == 0):
            stinfo['name'] = d.data['app_name']
    except:
        stinfo = {
            'status': st,
            'name': '未知'
        }
    ret = {
        'success': True,
        'status': st,
        'info': stinfo
    }
    return u.format_dict(ret)


@app.route('/get/status_list')
def get_status_list():
    showip(request, '/get/status_list')
    stlst = d.dget('status_list')
    return u.format_dict(stlst)


@app.route('/set')
def set_normal():
    showip(request, '/set')
    status = escape(request.args.get("status"))
    app_name = escape(request.args.get("app_name"))
    battery = escape(request.args.get("battery"))  # 获取电量值
    power = escape(request.args.get("power"))  # 获取充电状态 (打开或关闭)
    
    try:
        status = int(status)
    except:
        return reterr(
            code='bad request',
            message="argument 'status' must be a number"
        )
    secret = escape(request.args.get("secret"))
    u.info(f'status: {status}, name: {app_name}, secret: "{secret}"')
    secret_real = d.dget('secret')
    if secret == secret_real:
        d.dset('status', status)
        # 根据 power 值判断充电状态
        if power == '打开':
            power_status = '充电中'
        elif power == '关闭':
            power_status = '放电中'
        else:
            power_status = '未知状态'  # 如果 power 不是"打开"或"关闭"
        
        # 如果电量值存在，修改应用名称，显示电量和充电状态
        if battery:
            app_name += f"（电量:{battery}%/{power_status}）"
        d.dset('app_name', app_name)

        # 获取当前时间并转换为 UTC+8 时区
        current_time = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
        
        # 更新上次更新时间
        d.dset('last_updated', current_time)
        
        u.info('set success')
        ret = {
            'success': True,
            'code': 'OK',
            'set_to': status,
            'app_name':app_name,
            'last_updated': current_time  # 将更新时间传回
        }
        return u.format_dict(ret)
    else:
        return reterr(
            code='not authorized',
            message='invaild secret'
        )



if __name__ == '__main__':
    d.load()
    app.run(
        host=d.data['host'],
        port=d.data['port'],
        debug=d.data['debug']
    )
