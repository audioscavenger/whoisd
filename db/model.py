#!/usr/bin/env python3
# -*- coding: utf-8 -*- ®

from sqlalchemy import Unicode, Column, Integer, String, DateTime, Index, PrimaryKeyConstraint
from sqlalchemy import literal_column
from db.helper import get_base
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import func

Base = get_base()


# inetnum=str(cidr), attr=b'inetnum', netname=netname, autnum=origin, description=description, remarks=remarks, country=country, created=created, last_modified=last_modified, status=status, source=source
# BlockCidr: inetnum, route
class BlockCidr(Base):
  __tablename__ = 'cidr'
  id = Column(Integer, primary_key=True, autoincrement=True)
  # inetnum = Column(postgresql.CIDR, nullable=False, unique=True, index=True)
  inetnum = Column(String, nullable=False, unique=True, index=True)
  attr =  Column(String, nullable=False, index=True)
  netname = Column(String, nullable=True, index=True)
  autnum = Column(String, index=True)
  country = Column(String, index=True)
  created = Column(DateTime, index=True)
  last_modified = Column(DateTime, index=True)
  status = Column(String, index=True)
  source = Column(String, index=True)
  description = Column(String)
  remarks = Column(String)
  
  __table_args__ = (
    Index('ix_cidr_description', func.to_tsvector(literal_column("'english'"), description), postgresql_using="gin"), 
  )
  
  def __str__(self):
    return f'inetnum: {self.inetnum}, attr: {self.attr}, netname: {self.netname}, autnum: {self.autnum}, country: {self.country}, created: {self.created}, last_modified: {self.last_modified}, status: {self.status}, source: {self.source}, desc: {self.description}, remarks: {self.remarks}'
  
  def __repr__(self):
    return self.__str__()

# BlockMember: mntner, person, role, organisation, irt
# idd=idd, attr=attr, name=name, description=description, remarks=remarks
class BlockMember(Base):
  __tablename__ = 'member'
  id = Column(Integer, primary_key=True, autoincrement=True)
  idd = Column(String, nullable=False, unique=True, index=True)
  attr =  Column(String, nullable=False, index=True)
  name = Column(String, nullable=False, index=True)
  description = Column(String)
  remarks = Column(String)
  
  __table_args__ = (
    Index('ix_member_description', func.to_tsvector(literal_column("'english'"), description), postgresql_using="gin"), 
  )
  
  def __str__(self):
    return f'id: {self.id}, attr: {self.attr}, name: {self.name}, description: {self.description}, remarks: {self.remarks}'
  
  def __repr__(self):
    return self.__str__()

# BlockAttr: aut-num, as-set, route-set, domain
# name=name, attr=attr, description=description, remarks=remarks
class BlockAttr(Base):
  __tablename__ = 'attr'
  id = Column(Integer, primary_key=True, autoincrement=True)
  name = Column(String, nullable=False, index=True)
  attr =  Column(String, nullable=False, index=True)
  description = Column(String)
  remarks = Column(String, index=True)
  
  __table_args__ = (
    Index('ix_attr_description', func.to_tsvector(literal_column("'english'"), description), postgresql_using="gin"), 
  )
  
  def __str__(self):
    return f'name: {self.name}, attr: {self.attr}, description: {self.description}, remarks: {self.remarks}'
  
  def __repr__(self):
    return self.__str__()

# BlockParent: parent-children relationships between all 3 tables
class BlockParent(Base):
  __tablename__ = 'parent'
  parent      = Column(String, nullable=False, index=True)
  parent_type = Column(String, nullable=False, index=True)
  child       = Column(String, nullable=False, index=True)
  child_type  = Column(String, nullable=False, index=True)
  
  __table_args__ = (
    PrimaryKeyConstraint(parent, parent_type, child, child_type),
    {},
  )
  
  def __str__(self):
    return f'parent: {self.parent}, parent_type: {self.parent_type}, child: {self.child}, child_type: {self.child_type}'
  
  def __repr__(self):
    return self.__str__()
