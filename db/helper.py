#!/usr/bin/env python3
# -*- coding: utf-8 -*- ®

from sqlalchemy import create_engine
# MovedIn20Warning: The ``declarative_base()`` function is now available as sqlalchemy.orm.declarative_base(). (deprecated since: 2.0) (Background on SQLAlchemy 2.0 at: https://sqlalche.me/e/b8d9)
# from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker, exc

Base = declarative_base()

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

# connection_string = 'postgresql+psycopg://whoisd:whoisd@db:5432/whoisd'
# session = setup_connection(connection_string)
def setup_connection(connection_string, create_db=False, auto_commit=False):
  engine = create_postgres_pool(connection_string)
  session = sessionmaker()
  session.configure(bind=engine)
  
  if create_db:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
  
  return session()

