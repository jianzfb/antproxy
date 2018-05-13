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
    applicant = self.get_current_user()
    if not applicant.is_admin:
      self.log.error('no admin user call')
      self.set_status(500)
      self.finish()
      return

    user_name = self.get_argument('username', '')
    # check user name unique
    user = self.db.query(orm.User).filter(orm.User.name==user_name).one_or_none()
    if user is not None:
      self.log.error('has existed user %s'%user_name)
      self.set_status(401)
      self.write(json.dumps({'TIP': 'user name not unique'}))
      self.finish()
      return

    user = orm.User(name=user_name, is_authorized=True)
    self.db.add(user)
    self.db.commit()

    user_token = self.get_argument('token', None)
    if user_token is None:
      self.log.info('use proxy inner token')
      user.new_api_token()
    else:
      self.log.info('user outer authorizied token')
      user.new_api_token(token=user_token)
    self.db.commit()

    self.write(json.dumps({'RES': 'success'}))
    self.finish()

  @gen.coroutine
  def delete(self):
    applicant = self.get_current_user()
    if not applicant.orm_user.is_admin:
      self.log.error('no admin user call')
      self.set_status(500)
      self.finish()
      return

    user_name = self.get_argument('username', '')
    # check user name unique
    user = self.db.query(orm.User).filter(orm.User.name==user_name).one_or_none()

    if user is None:
      self.log.error('no user %s'%user_name)
      self.set_status(401)
      self.finish()
      return

    self.db.delete(user)
    self.db.commit()