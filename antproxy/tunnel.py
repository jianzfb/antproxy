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


class IndexHandler(tornado.web.RequestHandler):
  @property
  def master_proxy(self):
    return self.settings['master_proxy']
  
  def get(self):
    self.write('welcome tcp tunnel')


class ProxyConnectingHandler(tornado.web.RequestHandler):
  @property
  def master_proxy(self):
    return self.settings['master_proxy']
    
  def post(self):
    communicate_addr = self.get_argument('communicate_addr', None)
    customer_addr = self.get_argument('customer_addr', None)
    if communicate_addr is None or customer_addr is None:
      self.send_error(500)
      return

    communicate_listen_addr = split_host(communicate_addr)
    customer_listen_addr = split_host(customer_addr)
    
    self.master_proxy.add_proxy_server(customer_listen_addr, communicate_listen_addr)
    self.write(json.dumps({'STATUS': 'SUCCESS'}))
  
  def delete(self):
    communicate_addr = self.get_argument('communicate_addr', None)
    customer_addr = self.get_argument('customer_addr', None)
    if communicate_addr is None or customer_addr is None:
      self.send_error(500)
      return

    communicate_listen_addr = split_host(communicate_addr)
    customer_listen_addr = split_host(customer_addr)

    self.master_proxy.delete_proxy_server(customer_listen_addr, communicate_listen_addr)
    self.write(json.dumps({'STATUS': 'SUCCESS'}))
  

def tunnel_server():
  # 1.step launch server
  master_proxy = launch_master_proxy()

  # 2.step launch http server
  settings = {'master_proxy': master_proxy}
  app = tornado.web.Application(handlers=[(r"/", IndexHandler),
                                          (r"/crowdsource/proxy/", ProxyConnectingHandler)], **settings)
  http_server = tornado.httpserver.HTTPServer(app)
  
  http_server.listen(options.port)
  tornado.ioloop.IOLoop.instance().start()


if __name__ == '__main__':
    parse = argparse.ArgumentParser(description="""A fast and reliable reverse TCP tunnel""")
    parse.add_argument("-p", "--port", default=9876, required=True, help="http serve")
    args = parse.parse_args()
    define('port', default=args.port, help="run on the given port", type=int)
    tunnel_server()
