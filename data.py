# coding: utf-8

import json
import os
import utils as u
from datetime import datetime
from zoneinfo import ZoneInfo
from jsonc_parser.parser import JsoncParser as jsonp


def initJson():
    try:
        jsonData = jsonp.parse_file('example.jsonc', encoding='utf-8')

        # 初始化时也要确保包含 'last_updated' 键
        if 'last_updated' not in jsonData['other']:
            jsonData['other']['last_updated'] = "00:00:00"
        
        with open('data.json', 'w+', encoding='utf-8') as file:
            json.dump(jsonData, file, indent=4, ensure_ascii=False)
    except:
        u.error('Create data.json failed')
        raise


class data:
    def __init__(self):
        if not os.path.exists('data.json'):
            u.warning('data.json not exist, creating')
            initJson()
        with open('data.json', 'r', encoding='utf-8') as file:
            self.data = json.load(file)
            
        # 初始化访问次数和日期
        if 'view_count' not in self.data['other']:
            self.data['other']['view_count'] = 0
        if 'last_visit_date' not in self.data['other']:
            self.data['other']['last_visit_date'] = self.get_current_date()

    def load(self):
        with open('data.json', 'r', encoding='utf-8') as file:
            self.data = json.load(file)

    def save(self):
        with open('data.json', 'w+', encoding='utf-8') as file:
            json.dump(self.data, file, indent=4, ensure_ascii=False)

    def dset(self, name, value):
        self.data[name] = value
        with open('data.json', 'w+', encoding='utf-8') as file:
            json.dump(self.data, file, indent=4, ensure_ascii=False)

    def dget(self, name):
        with open('data.json', 'r', encoding='utf-8') as file:
            self.data = json.load(file)
            try:
                gotdata = self.data[name]
            except:
                gotdata = None
            return gotdata

    def get_current_date(self):
        # 获取当前日期，格式为 "YYYY-MM-DD"
        return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")

    def reset_view_count_if_new_day(self):
        # 获取当前日期并与上次记录的日期对比，如果不同则重置访问次数
        current_date = self.get_current_date()
        if current_date != self.data['other']['last_visit_date']:
            self.data['other']['view_count'] = 0
            self.data['other']['last_visit_date'] = current_date
            self.save()
