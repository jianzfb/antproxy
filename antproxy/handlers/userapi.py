# -*- coding: UTF-8 -*-
# @Time : 06/03/2018
# @File : userapi.py
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


class UserRegisterAPIHandler(BaseHanlder):
  @gen.coroutine
  def post(self):
    user = self.get_current_user()
    if not user.orm_user.is_admin:
      self.set_status(500)
      self.finish()
      return

    user_name = self.get_argument('username', '')
    # check user name unique
    user = self.db.query(orm.User).filter(orm.User.name==user_name).one_or_none()
    if user is not None:
      self.set_status(401)
      self.write(json.dumps({'TIP': 'user name not unique'}))
      self.finish()
      return

    user_token = self.get_argument('token', None)
    if user_token is None:
      self.set_status(401)
      self.write(json.dumps({'TIP': 'must set user token'}))
      self.finish()
      return

    user = orm.User(name=user_name, is_authorized=True)
    self.db.add(user)
    self.db.commit()

    user.new_api_token(token=user_token)
    self.db.commit()

    self.write(json.dumps({'RES': 'success'}))
    self.finish()