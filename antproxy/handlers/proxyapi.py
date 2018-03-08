# -*- coding: UTF-8 -*-
# @Time : 06/03/2018
# @File : proxyapi.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
from tornado import web, gen
from antproxy.handlers.base import *
from antproxy.user import *
import json
from datetime import datetime
import socket
import random
from sqlalchemy import and_


class ApplyProxyTaskHandler(BaseHanlder):
  def _is_open(self, check_ip, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
      s.connect((check_ip, int(port)))
      s.shutdown(2)
      return True
    except:
      return False

  def post(self):
    user = self.get_current_user()
    if user is None:
      self.set_status(500)
      self.write(json.dumps({'TIP': 'must login'}))
      self.finish()
      return

    if not user.is_authorized:
      self.set_status(500)
      self.write(json.dumps({'TIP': 'no priority'}))
      self.finish()
      return

    instance_num = self.db.query(orm.InnerNetProxy).filter(orm.InnerNetProxy.user_id == user.id).count()
    if user.max_instances > 0:
      if user.max_instances <= instance_num:
        self.set_status(500)
        self.write(json.dumps({'TIP': 'has arrived max instances'}))
        self.finish()
        return

    if user.expire_time > 0:
      if user.expire_time < datetime.now().timestamp():
        self.set_status(500)
        self.write(json.dumps({'TIP': 'expire time'}))
        self.finish()
        return

    # max connection time
    max_time = self.get_argument('max_time', -1)

    # current time
    start_time = datetime.now().timestamp()

    # user ip
    user_ip = self.get_argument('ip', '')
    # user location
    user_location = self.get_argument('location','')

    # output ip
    output_ip = self.get_argument('output_ip', '')
    # output domain
    output_domain = self.get_argument('output_domain', '')

    # task type
    task_type = self.get_argument('type', '')

    # task description
    task_description = self.get_argument('description', '')

    odd_num = -1
    check_count = 20
    is_ok = False
    while check_count:
      odd_num = random.randint(0, self.port_range[1] - self.port_range[0])
      if odd_num % 2 == 0:
        odd_num = odd_num + 1

      odd_num = self.port_range[0] + odd_num
      if not self._is_open('127.0.0.1', odd_num):
        is_ok = True
        break

      check_count = check_count - 1

    if not is_ok:
      self.set_status(500)
      self.write(json.dumps({'TIP': 'resource exhausted'}))
      self.finish()
      return

    outer_port = odd_num
    inner_port = odd_num + 1

    proxy_instance = orm.InnerNetProxy(inner_port=inner_port,
                                       output_port=outer_port,
                                       output_ip=output_ip,
                                       output_domain=output_domain,
                                       start_time=start_time,
                                       max_time=max_time,
                                       user_ip=user_ip,
                                       user_location=user_location,
                                       task_type=task_type,
                                       task_description=task_description)
    self.db.add(proxy_instance)
    self.db.commit()

    proxy_instance.user = user.orm_user
    self.db.commit()

    # bind inner port and outer port
    self.master_proxy.add_proxy_server(('127.0.0.1',outer_port),
                                       ('127.0.0.1',inner_port))

    # return
    self.write(json.dumps({'RES': 'success',
                           'outer_port': outer_port,
                           'inner_port': inner_port}))
    self.finish()


class StopProxyTaskHandler(BaseHanlder):
  def _is_open(self, check_ip, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
      s.connect((check_ip, int(port)))
      s.shutdown(2)
      return True
    except:
      return False

  def post(self):
    user = self.get_current_user()
    if user is None:
      self.set_status(500)
      self.write(json.dumps({'TIP': 'must login'}))
      self.finish()
      return

    outer_port = int(self.get_argument('outer_port', -1))
    if outer_port == -1:
      self.set_status(500)
      self.write(json.dumps({'TIP': 'must instance outer port'}))
      self.finish()
      return

    proxy_instance = self.db.query(orm.InnerNetProxy).filter(and_(orm.InnerNetProxy.user==user.orm_user,
                                                                  orm.InnerNetProxy.output_port==outer_port)).one_or_none()
    if proxy_instance is None:
      self.set_status(500)
      self.write(json.dumps({'TIP': 'couldnt find proxy instance'}))
      self.finish()
      return

    # closing port
    if self._is_open('127.0.0.1', outer_port) or self._is_open('127.0.0.1', outer_port+1):
      customer_listen_addr = ('127.0.0.1', outer_port)
      communicate_listen_addr = ('127.0.0.1', outer_port+1)
      self.master_proxy.delete_proxy_server(customer_listen_addr, communicate_listen_addr)

    # delete db record
    self.db.delete(proxy_instance)
    self.db.commit()

    self.write(json.dumps({'RES': 'success'}))
    self.finish()