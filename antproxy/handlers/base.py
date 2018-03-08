# -*- coding: UTF-8 -*-
# @Time : 28/02/2018
# @File : base.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
import tornado.web
from antproxy import orm
import re
from tornado.log import app_log

auth_header_pat = re.compile(r'^token\s+([^\s]+)$')


class BaseHanlder(tornado.web.RequestHandler):
  @property
  def master_proxy(self):
    return self.settings['master_proxy']

  @property
  def db(self):
    return self.settings['db']

  @property
  def log(self):
    return self.settings.get('log', app_log)

  @property
  def users(self):
    return self.settings.get('users', None)

  @property
  def cookie_max_age_days(self):
    return self.settings.get('cookie_max_age_days', None)

  @property
  def port_range(self):
    return self.settings.get('port_range', None)

  def finish(self, *args, **kwargs):
    """Roll back any uncommitted transactions from the handler."""
    self.db.rollback()
    super().finish(*args, **kwargs)

  def get_current_user_token(self):
    """get_current_user from Authorization header token"""
    auth_header = self.request.headers.get('Authorization', '')
    match = auth_header_pat.match(auth_header)
    if not match:
      return None
    token = match.group(1)
    orm_token = orm.APIToken.find(self.db, token)
    if orm_token is None:
      return None

    user = self._user_from_orm(orm_token.user)
    if user is None:
      return None
    return user

  def _user_for_cookie(self, cookie_name, cookie_value=None):
    """Get the User for a given cookie, if there is one"""
    cookie_id = self.get_secure_cookie(
      cookie_name,
      cookie_value,
      max_age_days=self.cookie_max_age_days,
    )

    def clear():
      self.clear_cookie(cookie_name)

    if cookie_id is None:
      if self.get_cookie(cookie_name):
        self.log.warning("Invalid or expired cookie token")
        clear()
      return
    cookie_id = cookie_id.decode('utf8', 'replace')
    u = self.db.query(orm.User).filter(orm.User.cookie_id == cookie_id).first()
    user = self._user_from_orm(u)
    if user is None:
      self.log.warning("Invalid cookie token")
      # have cookie, but it's not valid. Clear it and start over.
      clear()
    return user

  def _user_from_orm(self, orm_user):
    """return User wrapper from orm.User object"""
    if orm_user is None:
      return
    return self.users[orm_user]

  def get_current_user_cookie(self):
    """get_current_user from a cookie token"""
    return self._user_for_cookie('proxy')

  def get_current_user(self):
    """get current username"""
    user = self.get_current_user_token()
    if user is not None:
      return user

    return self.get_current_user_cookie()

  def user_from_username(self, username):
    """Get User for username, creating if it doesn't exist"""
    user = self.find_user(username)
    return user

  def _set_user_cookie(self, user, server_name='proxy'):
    # tornado <4.2 have a bug that consider secure==True as soon as
    # 'secure' kwarg is passed to set_secure_cookie
    if self.request.protocol == 'https':
      kwargs = {'secure': True}
    else:
      kwargs = {}

    self.log.debug("Setting cookie for %s: %s, %s", user.name, server_name, kwargs)
    self.set_secure_cookie(
      server_name,
      user.cookie_id,
      path='/',
      **kwargs
    )

  def set_service_cookie(self, user):
    """set the login cookie for services"""
    self._set_user_cookie(user, 'proxy')

  def find_user(self, name):
    """Get a user by name

    return None if no such user
    """
    orm_user = orm.User.find(db=self.db, name=name)
    return self._user_from_orm(orm_user)


  def set_login_cookie(self, user):
    self.set_service_cookie(user)

  def clear_login_cookie(self, name=None):
    if name is None:
      user = self.get_current_user()
    else:
      user = self.find_user(name)

    self.clear_cookie('proxy')
