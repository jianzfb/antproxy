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
  def get(self):
    user = self.get_current_user()
    if user is None:
      self.log.error('no user existed')
      self.set_status(500)
      self.write(json.dumps({'TIP': 'must login'}))
      self.finish()
      return

    if not user.is_admin:
      self.log.error('must admin user')
      self.set_status(500)
      self.write(json.dumps({'TIP': 'must be administrator'}))
      self.finish()
      return

    query_ports = self.get_argument('query_ports', '')
    try:
      query_ports = json.loads(query_ports)
      query_ports_open = []
      for p in query_ports:
        if self.is_open(self.host_ip, p):
          query_ports_open.append(True)
        else:
          query_ports_open.append(False)

      self.write(json.dumps({'RES': query_ports_open}))
      self.finish()
    except:
      self.set_status(500)
      self.write(json.dumps({'TIP': 'parameter error'}))
      self.finish()

  def post(self):
    user = self.get_current_user()
    if user is None:
      self.log.error('no user existed')
      self.set_status(500)
      self.write(json.dumps({'TIP': 'must login'}))
      self.finish()
      return

    if not user.is_authorized:
      self.log.error('user %s is not authorized'%user.name)
      self.set_status(500)
      self.write(json.dumps({'TIP': 'no priority'}))
      self.finish()
      return

    instance_num = self.db.query(orm.InnerNetProxy).filter(orm.InnerNetProxy.user_id == user.id).count()
    if user.max_instances > 0:
      if user.max_instances <= instance_num:
        self.log.error('beyond max instances for user %s'%user.name)
        self.set_status(500)
        self.write(json.dumps({'TIP': 'has arrived max instances'}))
        self.finish()
        return

    if user.expire_time > 0:
      if user.expire_time < datetime.now().timestamp():
        self.log.error('user has been expired')
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

    # server name
    server_name = self.get_argument('server_name', None)
    if server_name is None:
      self.log.error('must set server name')
      self.set_status(500)
      self.finish()
      return

    proxy_instance = self.db.query(orm.InnerNetProxy).filter(orm.InnerNetProxy.server_name == server_name).one_or_none()
    if proxy_instance is not None:
      inner_port = proxy_instance.inner_port
      outer_port = proxy_instance.output_port

      # check inner port is alive and it is assigned server_name
      if not self.is_open(self.host_ip, outer_port):
        # bind inner port and outer port
        self.master_proxy.add_proxy_server((self.host_ip, outer_port),
                                           (self.host_ip, inner_port))

        # return
        self.write(json.dumps({'RES': 'success',
                               'outer_port': outer_port,
                               'inner_port': inner_port}))
        self.finish()

      return
    else:
      odd_num = -1
      check_count = 20
      is_ok = False
      while check_count:
        odd_num = random.randint(0, self.port_range[1] - self.port_range[0])
        if odd_num % 2 == 0:
          odd_num = odd_num + 1

        odd_num = self.port_range[0] + odd_num
        if not self.is_open(self.host_ip, odd_num):
          is_occupied = self.db.query(orm.InnerNetProxy).filter(orm.InnerNetProxy.inner_port==odd_num+1).one_or_none()
          if is_occupied is None:
            is_ok = True
            break

        check_count = check_count - 1

      if not is_ok:
        self.log.error('proxy resource exhausted')
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
                                         task_description=task_description,
                                         server_name=server_name)
      self.db.add(proxy_instance)
      self.db.commit()

      proxy_instance.user = user.orm_user
      self.db.commit()

      # bind inner port and outer port
      self.master_proxy.add_proxy_server((self.host_ip, outer_port),
                                         (self.host_ip, inner_port))

      # return
      self.write(json.dumps({'RES': 'success',
                             'outer_port': outer_port,
                             'inner_port': inner_port}))
      self.finish()

  def delete(self):
    user = self.get_current_user()
    if user is None:
      self.log.error('no user existed')
      self.set_status(500)
      self.write(json.dumps({'TIP': 'must login'}))
      self.finish()
      return

    server_name = self.get_argument('server_name',None)
    if server_name is None:
      self.log.error('must define server name')
      self.set_status(500)
      self.write(json.dumps({'TIP': 'must instance outer port'}))
      self.finish()
      return

    proxy_instance = self.db.query(orm.InnerNetProxy).filter(and_(orm.InnerNetProxy.user==user.orm_user,
                                                                  orm.InnerNetProxy.server_name == server_name)).one_or_none()
    if proxy_instance is None:
      self.log.error('(user(%s): server(%s)) dont have proxy instance'%(user.orm_user.name, server_name))
      self.set_status(500)
      self.write(json.dumps({'TIP': 'couldnt find proxy instance'}))
      self.finish()
      return

    customer_listen_addr = (self.host_ip, proxy_instance.output_port)
    communicate_listen_addr = (self.host_ip, proxy_instance.output_port+1)
    self.master_proxy.delete_proxy_server(customer_listen_addr, communicate_listen_addr)

    # force listening thread stop, dont care
    self.is_open(self.host_ip, proxy_instance.output_port)
    self.is_open(self.host_ip, proxy_instance.output_port+1)

    # delete db record
    self.db.delete(proxy_instance)
    self.db.commit()

    self.write(json.dumps({'RES': 'success'}))
    self.finish()