# -*- coding: UTF-8 -*-
# @Time : 28/02/2018
# @File : user.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function

import os
from datetime import datetime, timedelta
from urllib.parse import quote, urlparse

from tornado import gen
from tornado.log import app_log

from sqlalchemy import inspect
from antproxy import orm


class UserDict(dict):
  """Like defaultdict, but for users

  Getting by a user id OR an orm.User instance returns a User wrapper around the orm user.
  """

  def __init__(self, db_factory, settings):
    self.db_factory = db_factory
    self.settings = settings
    super().__init__()

  @property
  def db(self):
    return self.db_factory

  def __contains__(self, key):
    if isinstance(key, (User, orm.User)):
      key = key.id
    return dict.__contains__(self, key)

  def __getitem__(self, key):
    if isinstance(key, User):
      key = key.id
    elif isinstance(key, str):
      orm_user = self.db.query(orm.User).filter(orm.User.name == key).first()
      if orm_user is None:
        raise KeyError("No such user: %s" % key)
      else:
        key = orm_user
    if isinstance(key, orm.User):
      # users[orm_user] returns User(orm_user)
      orm_user = key
      if orm_user.id not in self:
        user = self[orm_user.id] = User(orm_user, self.settings)
        return user
      user = dict.__getitem__(self, orm_user.id)
      user.db = self.db
      return user
    elif isinstance(key, int):
      id = key
      if id not in self:
        orm_user = self.db.query(orm.User).filter(orm.User.id == id).first()
        if orm_user is None:
          raise KeyError("No such user: %s" % id)
        user = self[id] = User(orm_user, self.settings)
      return dict.__getitem__(self, id)
    else:
      raise KeyError(repr(key))

  def __delitem__(self, key):
    user = self[key]
    user_id = user.id
    db = self.db
    db.delete(user.orm_user)
    db.commit()
    dict.__delitem__(self, user_id)


class User(object):
  settings = None
  _db = None
  orm_user = None

  @property
  def db(self):
    if self._db is None:
      return inspect(self.orm_user).session

    return self._db

  @db.setter
  def db(self, val):
    self._db = val

  def __init__(self, orm_user, settings, **kwargs):
    self.orm_user = orm_user
    self.settings = settings

  @property
  def name(self):
    return self.orm_user.name

  @property
  def is_authorized(self):
    return self.orm_user.is_authorized

  @property
  def is_admin(self):
    return self.orm_user.is_admin

  @property
  def max_instances(self):
    return self.orm_user.max_instances

  @property
  def expire_time(self):
    return self.orm_user.expire_time

  @property
  def id(self):
    return self.orm_user.id