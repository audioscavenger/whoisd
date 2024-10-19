#!/usr/bin/env python3
# -*- coding: utf-8 -*- ®

from sqlalchemy import create_engine
# # MovedIn20Warning: The ``declarative_base()`` function is now available as sqlalchemy.orm.declarative_base(). (deprecated since: 2.0) (Background on SQLAlchemy 2.0 at: https://sqlalche.me/e/b8d9)
# # from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker, exc

Base = declarative_base()

# TRY: handle race conditions https://rachbelaid.com/handling-race-condition-insert-with-sqlalchemy/
# RESULT: actually it only works because you commit instead of flushing... not efficient
# # from sqlalchemy.ext.declarative import declared_attr, as_declarative    # deprecated
# from sqlalchemy.orm import declared_attr, as_declarative
# from sqlalchemy import Column, Integer
# @as_declarative()
# class Base(object):
  # @declared_attr
  # def __tablename__(cls):
    # return cls.__name__.lower()
  # # deprecation warning: Note that as of SQLAlchemy 1.1, 'autoincrement=True' must be indicated explicitly for composite (e.g. multicolumn) primary keys if AUTO_INCREMENT/SERIAL/IDENTITY behavior is expected for one of the columns in the primary key.
  # id = Column(Integer, primary_key=True, autoincrement=True)

def get_base():
  return Base


# TODO: get this working to handle duplicat key inserts: https://stackoverflow.com/questions/10322514/dealing-with-duplicate-primary-keys-on-insert-in-sqlalchemy-declarative-style
# try:
  # # any query
# except exc.SQLAlchemyError as e:
  # error = str(e.__dict__['orig'])
  # print(type(e), error)


def create_postgres_pool(connection_string):
  engine = create_engine(connection_string)
  return engine

# TODO: read https://docs.sqlalchemy.org/en/20/core/connections.html#dbapi-autocommit
# connection_string = 'postgresql+psycopg://whoisd:whoisd@db:5432/whoisd'
# session = setup_connection(connection_string)
def setup_connection(connection_string, reset_db=False):
  engine = create_postgres_pool(connection_string)
  # session = sessionmaker()
  # session.configure(bind=engine)
  # session = scoped_session(sessionmaker(bind=engine))
  session = scoped_session(sessionmaker(autoflush=True, bind=engine))
  # Base.metadata.bind = engine
  
  if reset_db:
    try:
      Base.metadata.drop_all(engine)
    except:
      pass
    try:
      Base.metadata.create_all(engine)
    except:
      pass
  
  return session()

