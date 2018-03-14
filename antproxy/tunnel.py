# -*- coding: UTF-8 -*-
# @Time    : 18-1-17
# @File    : tunnel.py
# @Author  : 
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
from antproxy.master import *
import os
import json
from tornado.options import define, options
import argparse
from antproxy import orm
from datetime import datetime
from sqlalchemy.orm import scoped_session
from tornado import web, gen
from antproxy.handlers.base import *
from antproxy.user import *
from antproxy.handlers.index import *
from antproxy.handlers.proxyapi import *
from antproxy.handlers.userapi import *
import uuid
from antproxy.dict2xml import *


def scan_ports_func(db, master_proxy):
  # scan all proxy records
  all_proxies_records = db.query(orm.InnerNetProxy).all()

  def _is_open(check_ip, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
      s.connect((check_ip, int(port)))
      s.shutdown(2)
      return True
    except:
      return False

  for record in all_proxies_records:
    # outer browser port
    outer_port = record.output_port
    # inner communicate port
    inner_port = record.inner_port

    output_port_is_open = _is_open('127.0.0.1', outer_port)
    inner_port_is_open = _is_open('127.0.0.1', inner_port)

    if output_port_is_open and inner_port_is_open:
      # 1.step check whether > max time
      if record.max_time > 0.0:
        now_time = time.time()
        if (now_time - record.start_time) >= record.max_time:
          # 1.step close opening ports
          customer_listen_addr = ('127.0.0.1', outer_port)
          communicate_listen_addr = ('127.0.0.1', outer_port + 1)
          master_proxy.delete_proxy_server(customer_listen_addr, communicate_listen_addr)

          # 2.step delete record
          db.delete(record)

      continue
    else:
      # 1.step force close unhealth port ?
      # 2.step delete record
      db.delete(record)

  db.commit()


def init_tunnel_server():
  # 1.step initialize database
  db = scoped_session(orm.new_session_factory(url='sqlite:///antproxy.sqlite'))()

  # 2.step initialize users
  init_users(db)

  # 3.step initialize proxy port range
  xml_folder = '/'.join(os.path.dirname(__file__).split('/'))
  secret_xml = os.path.join(xml_folder, 'secret.xml')
  if os.path.exists(secret_xml):
    xml_content = read_xml(secret_xml)
  else:
    xml_content = {}

  port_range = [20000, 30000]
  if 'PortRange' in xml_content:
    port_r = xml_content['PortRange'][0][1].split(' ')
    port_range[0] = int(port_r[0])
    port_range[1] = int(port_r[1])

  settings = {'db': db, 'port_range': port_range}
  return settings


def init_users(db):
    # write to xml
    xml_folder = '/'.join(os.path.dirname(__file__).split('/'))
    secret_xml = os.path.join(xml_folder, 'secret.xml')
    if os.path.exists(secret_xml):
      xml_content = read_xml(secret_xml)
    else:
      xml_content = {}

    # initialize user db by secret xml
    if 'admin' in xml_content:
      admin_users_dict = {}
      for xml_user in xml_content['admin']:
        user_name = xml_user[1]

        user = db.query(orm.User).filter(orm.User.name == user_name).one_or_none()
        if user is None:
          pwd = '111111' if 'password' not in xml_user[2] else xml_user[2]['password']
          user = orm.User(name=user_name, is_admin=True, password=pwd)
          db.add(user)
          db.commit()

          token = user.new_api_token()
          db.commit()
          admin_users_dict[user_name] = token
          xml_user[2]['token'] = token

      if len(admin_users_dict) > 0:
        output_xml(dict_2_xml(xml_content, 'AntProxy'), secret_xml)

    if 'users' in xml_content:
      users_dict = {}
      for xml_user in xml_content['users']:
        user_name = xml_user[1]
        user = db.query(orm.User).filter(orm.User.name == user_name).one_or_none()
        if user is None:
          user = orm.User(name=user_name)
          db.add(user)
          db.commit()

          token = user.new_api_token()
          db.commit()
          users_dict[user_name] = token
          xml_user[2]['token'] = token

      if len(users_dict) > 0:
        output_xml(dict_2_xml(xml_content, 'AntProxy'), secret_xml)


def launch_tunnel_server():
  # 0.step initialize tunnel
  settings = init_tunnel_server()

  # 1.step launch proxy server
  master_proxy = launch_master_proxy()
  settings.update({'master_proxy': master_proxy})

  # 2.step launch http server
  static_folder = '/'.join(os.path.dirname(__file__).split('/'))
  settings.update({'template_path': os.path.join(static_folder, 'resource', 'templates'),
                   'static_path': os.path.join(static_folder, 'resource', 'static'),
                   'cookie_secret': str(uuid.uuid4()),
                   'cookie_max_age_days': 30})

  # 3.step parse all users
  users = UserDict(settings['db'], settings)
  settings.update({'users': users})

  # 4.step config httpserver
  app = tornado.web.Application(handlers=[(r"/", IndexHandler),
                                          (r"/apply/", ApplyProxyTaskHandler),
                                          (r"/stop/", ApplyProxyTaskHandler),
                                          (r"/isopen/", ApplyProxyTaskHandler),
                                          (r"/register/", UserRegisterAPIHandler)], **settings)
  http_server = tornado.httpserver.HTTPServer(app)
  http_server.listen(options.port)

  # 5.step config schedule periodically (iternal 1 hour)
  tornado.ioloop.PeriodicCallback(functools.partial(scan_ports_func, settings['db'], settings['master_proxy']), 60*60*1000).start()

  # 6.step start io loop
  tornado.ioloop.IOLoop.instance().start()


if __name__ == '__main__':
    parse = argparse.ArgumentParser(description="""A fast and reliable reverse TCP tunnel""")
    parse.add_argument("-p", "--port", default=9876, required=True, help="http server")
    args = parse.parse_args()

    # 1.step listening port
    listening_port = args.port
    define('port', default=args.port, help="run on the given port", type=int)

    # 2.step launch tunnel server
    launch_tunnel_server()
