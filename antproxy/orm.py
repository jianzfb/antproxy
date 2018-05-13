from sqlalchemy.types import TypeDecorator, TEXT
from sqlalchemy import (
    inspect,
    Column, Integer, ForeignKey, Unicode, Boolean,
    DateTime,Float,
)
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.expression import bindparam
from sqlalchemy import create_engine, Table
from sqlalchemy import LargeBinary
from sqlalchemy import and_
from sqlalchemy.orm import backref
from antproxy.utils import *

Base = declarative_base()

class User(Base):
  __tablename__ = 'users'

  def __repr__(self):
    return self.name

  id = Column(Integer, primary_key=True)
  name = Column(Unicode(1024), unique=True)
  password = Column(Unicode(1024), default='123456')
  is_admin = Column(Boolean, default=False)

  api_tokens = relationship("APIToken", backref="user")

  cookie_id = Column(Unicode(1024), default=new_token)
  proxys = relationship("InnerNetProxy", backref="user")

  expire_time = Column(Float, default=-1)
  max_instances = Column(Integer, default=-1)
  is_authorized = Column(Boolean, default=False)

  @classmethod
  def find(cls, db, name):
    """Find a user by name.

    Returns None if not found.
    """
    return db.query(cls).filter(cls.name == name).first()

  def new_api_token(self, token=None):
    """Create a new API token

    If `token` is given, load that token.
    """
    return APIToken.new(token=token, user=self)


class APIToken(Base):
  """An API token"""
  __tablename__ = 'api_tokens'

  @declared_attr
  def user_id(cls):
    return Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=True)

  id = Column(Integer, primary_key=True)
  hashed = Column(Unicode(1023))
  prefix = Column(Unicode(1023))
  prefix_length = 4
  algorithm = "sha512"
  rounds = 16384
  salt_bytes = 8

  @property
  def token(self):
    raise AttributeError("token is write-only")

  @token.setter
  def token(self, token):
    """Store the hashed value and prefix for a token"""
    self.prefix = token[:self.prefix_length]
    self.hashed = hash_token(token, rounds=self.rounds, salt=self.salt_bytes, algorithm=self.algorithm)

  def __repr__(self):
    if self.user is not None:
      kind = 'user'
      name = self.user.name
    else:
      # this shouldn't happen
      kind = 'owner'
      name = 'unknown'
    return "<{cls}('{pre}...', {kind}='{name}')>".format(
      cls=self.__class__.__name__,
      pre=self.prefix,
      kind=kind,
      name=name,
    )

  @classmethod
  def find(cls, db, token, *, kind=None):
    """Find a token object by value.

    Returns None if not found.

    `kind='user'` only returns API tokens for users
    `kind='service'` only returns API tokens for services
    """
    prefix = token[:cls.prefix_length]
    # since we can't filter on hashed values, filter on prefix
    # so we aren't comparing with all tokens
    prefix_match = db.query(cls).filter(bindparam('prefix', prefix).startswith(cls.prefix))
    if kind == 'user':
      prefix_match = prefix_match.filter(cls.user_id != None)
    elif kind is not None:
      raise ValueError("kind must be 'user', 'service', or None, not %r" % kind)
    for orm_token in prefix_match:
      if orm_token.match(token):
        return orm_token

  def match(self, token):
    """Is this my token?"""
    return compare_token(self.hashed, token)

  @classmethod
  def new(cls, token=None, user=None):
    """Generate a new API token for a user or service"""
    assert user
    db = inspect(user).session

    if token is None:
      token = new_token()
    else:
      if len(token) < 8:
        raise ValueError("Tokens must be at least 8 characters, got %r" % token)
      found = APIToken.find(db, token)
      if found:
        raise ValueError("Collision on token: %s..." % token[:4])
    orm_token = APIToken(token=token)
    if user:
      assert user.id is not None
      orm_token.user_id = user.id

    db.add(orm_token)
    db.commit()
    return token


class InnerNetProxy(Base):
  __tablename__ = 'proxy'

  def __repr__(self):
    return "<user %s(%s:%d -> *:%d)>" % (self.user.name, self.output_domain, self.output_port, self.inner_port)

  id = Column(Integer,primary_key=True)

  inner_port = Column(Integer, default=0)
  output_port = Column(Integer, default=0)
  output_ip = Column(Unicode(1024), default=0)
  output_domain = Column(Unicode(1024), default=0)

  start_time = Column(Float, default=0.0)
  duration_time = Column(Float, default=0.0)
  max_time = Column(Integer, default=0)

  user_ip = Column(Unicode(255), default='0.0.0.0')
  user_location = Column(Unicode(1024), default='')
  user_health = Column(Boolean, default=True)

  task_type = Column(Unicode(1024), default='')
  task_description = Column(Unicode(1024), default='')

  server_name = Column(Unicode(1024), default='')

  @declared_attr
  def user_id(cls):
    return Column(Integer, ForeignKey('users.id', ondelete="CASCADE"), nullable=True)


def new_session_factory(url="sqlite:///:memory:", reset=False, **kwargs):
  """Create a new session at url"""
  if url.startswith('sqlite'):
    kwargs.setdefault('connect_args', {'check_same_thread': False})
  elif url.startswith('mysql'):
    kwargs.setdefault('pool_recycle', 60)

  if url.endswith(':memory:'):
    # If we're using an in-memory database, ensure that only one connection
    # is ever created.
    kwargs.setdefault('poolclass', StaticPool)

  engine = create_engine(url, **kwargs)
  if reset:
    Base.metadata.drop_all(engine)
  Base.metadata.create_all(engine)

  session_factory = sessionmaker(bind=engine)
  return session_factory