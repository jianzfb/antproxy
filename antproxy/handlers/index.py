# -*- coding: UTF-8 -*-
# @Time : 07/03/2018
# @File : index.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
from antproxy.handlers.base import *
from datetime import datetime


class IndexHandler(BaseHanlder):
  def get(self):
    user = self.get_current_user()

    data = []
    is_admin = False
    log_status = False
    log_user = ''
    if user is not None and user.is_admin:
      all_proxies = self.db.query(orm.InnerNetProxy).all()

      data = []
      for index, p in enumerate(all_proxies):
        is_outputport_open = self.is_open('127.0.0.1', p.output_port)
        is_inputport_open = self.is_open('127.0.0.1', p.inner_port)

        is_health = True if is_outputport_open and is_inputport_open else False

        content = {}
        content['entry'] = '%s:%d'%(p.output_ip, p.output_port)
        content['start_time'] = datetime.fromtimestamp(p.start_time).strftime('%Y-%m-%d %H:%M:%S')
        content['duration_time'] = 0
        content['user'] = p.user.name if p.user is not None else '-'
        content['health'] = 'OK' if is_health else 'ERROR'
        content['location'] = ''
        content['ip'] = p.user_ip
        content['index'] = index
        content['id'] = p.id
        content['task'] = p.task_type

        data.append(content)

      user = self.get_current_user()
      log_status = False
      log_user = ''
      is_admin = False
      if user is not None:
        log_status = True
        log_user = user.name
        is_admin = user.is_admin
      else:
        log_status = False
        is_admin = False

    self.render('proxy.html',proxy_data=data, is_admin=is_admin, log_status=log_status, log_user=log_user)
