#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# ./bin/query 168.80.174.2
# SELECT block.inetnum, block.netname, block.country, block.description, block.mntby, block.created, block.last_modified, block.source FROM block WHERE block.inetnum >> '168.80.174.2' ORDER BY block.inetnum DESC;
# -[ RECORD 1 ]-+--------------------------------------------------------------
# inetnum     | 168.80.168.0/21
# netname     | AS24567
# country     |
# description   | Route-object
# mntby | TF-168-80-0-0-168-81-255-255-MNT
# created     |
# last_modified | 2020-05-23 00:00:00
# source    | afrinic
# -[ RECORD 2 ]-+--------------------------------------------------------------
# inetnum     | 168.80.0.0/15
# netname     | NETBLK-ANS-B
# country     | SC
# description   | Suite 9, Ansuya Estate Revolution Avenue Victoria, Seychelles
# mntby | AFRINIC-HM-MNT
# created     |
# last_modified | 1994-02-15 00:00:00
# source    | afrinic
# -[ RECORD 3 ]-+--------------------------------------------------------------
# inetnum     | 0.0.0.0/0
# netname     | IANA-BLK
# country     | EU # Country is really world wide
# description   | The whole IPv4 address space
# mntby | AFRINIC-HM-MNT
# created     |
# last_modified | 2001-05-29 00:00:00
# source    | afrinic

import argparse
import gzip
import time
from multiprocessing import cpu_count, Queue, Process, current_process
import logging
import re
import os

from db.model import BlockCidr
from db.model import BlockMember
from db.model import BlockObject
from db.model import BlockParent
from db.helper import setup_connection
from sqlalchemy.exc import SQLAlchemyError
from netaddr import iprange_to_cidrs

VERSION = '2.1'
FILELIST = ['afrinic.db.gz', 'apnic.db.inetnum.gz', 'arin.db.gz', 'lacnic.db.gz', 'ripe.db.inetnum.gz', 'apnic.db.inet6num.gz', 'ripe.db.inet6num.gz']
NUM_WORKERS = cpu_count()
LOG_FORMAT = '%(asctime)-15s - %(name)-9s - %(levelname)-8s - %(processName)-11s %(process)d - %(filename)s - %(message)s'
COMMIT_COUNT = 10000
MODULO = 10000
TIME2COMMIT = False
NUM_BLOCKS = 0
CURRENT_FILENAME = "empty"


class ContextFilter(logging.Filter):
  def filter(self, record):
    record.filename = CURRENT_FILENAME
    return True


logger = logging.getLogger('create_db')
logger.setLevel(logging.INFO)
f = ContextFilter()
logger.addFilter(f)
formatter = logging.Formatter(LOG_FORMAT)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)



def get_source(filename: str):
  if filename.startswith('afrinic'):
    return b'afrinic'
  elif filename.startswith('apnic'):
    return b'apnic'
  elif filename.startswith('arin'):
    return b'arin'
  elif 'lacnic' in filename:
    return b'lacnic'
  elif filename.startswith('ripe'):
    return b'ripe'
  else:
    logger.error(f"Can not determine source for {filename}")
  return None

###################### testing ######################
# block=b"""as-set:         AS-1002-CUSTOMERS
# descr:          Customers
# members:        AS1001
# members:        AS1002,   AS147297, AS210527, AS44570, AS400245, AS22951, AS210630, AS151338
# admin-c:        NOA32-ARIN
# tech-c:         NOA32-ARIN
# mnt-by:         MNT-VHL-190
# created:        2022-07-01T17:58:34Z
# last-modified:  2023-09-27T14:44:31Z
# source:         ARIN
# """
# members = parse_property(block, b'members')
# name = b'members'
# match = re.findall(rb'^%s:\s?(.+)$' % (name), block, re.MULTILINE)
# match = [b'       AS1001', b'       AS1002, AS147297, AS210527, AS44570, AS400245, AS22951, AS210630, AS151338']
# x = b' '.join(list(filter(None, (x.strip().replace(b"%s: " % name, b'').replace(b"%s: " % name, b'') for x in match))))
# x = b'AS1001   AS1002, AS147297,   AS210527,, AS44570, AS400245, AS22951, AS210630, AS151338'
###################### testing ######################


def parse_properties(block: str, name: str) -> list:
  match = re.findall(rb'^%s:\s?(.+)$' % (name), block, re.MULTILINE)
  print
  if match:
    # remove empty lines and remove multiple names
    x = b' '.join(list(filter(None, (x.strip().replace(b"%s: " % name, b'').replace(b"%s: " % name, b'') for x in match))))
    # decode to latin-1 so it can be split
    # also double-split hack to make sure we have a clean list
    # return re.split(',\s+|,|\s+|\n', x.decode('latin-1'))
    return re.sub(r'\W+', ',', x.decode('latin-1')).split(',')
  else:
    return []

def parse_property(block: str, name: str) -> str:
  match = re.findall(rb'^%s:\s?(.+)$' % (name), block, re.MULTILINE)
  print
  if match:
    # remove empty lines and remove multiple names
    x = b' '.join(list(filter(None, (x.strip().replace(b"%s: " % name, b'').replace(b"%s: " % name, b'') for x in match))))
    # remove multiple whitespaces by using a split hack
    # decode to latin-1 so it can be inserted in the database
    return ' '.join(x.decode('latin-1').split())
  else:
    return None


# An inetnum object contains information on allocations and assignments of IPv4 address space resources. 
# This is one of the main elements of the RIPE Internet Number Registry.
# org: is the parent organisation
def parse_property_inetnum(block: str):
  # IPv4
  match = re.findall(
    rb'^inetnum:[\s]*((?:\d{1,3}\.){3}\d{1,3})[\s]*-[\s]*((?:\d{1,3}\.){3}\d{1,3})', block, re.MULTILINE)
  if match:
    # netaddr can only handle strings, not bytes
    ip_start = match[0][0]
    ip_end = match[0][1]
    cidrs = iprange_to_cidrs(ip_start, ip_end)
    return cidrs
  # direct CIDR in lacnic db
  match = re.findall(rb'^inetnum:[\s]*((?:\d{1,3}\.){3}\d{1,3}/\d+)', block, re.MULTILINE)
  if match:
    return [match[0]]
  # lacnic with wrong ip
  # inetnum:  177.46.7/24
  match = re.findall(rb'^inetnum:[\s]*((?:\d{1,3}\.){2}\d{1,3}/\d+)', block, re.MULTILINE)
  if match:
    tmp = match[0].split(b"/")
    return [f"{tmp[0].decode('utf-8')}.0/{tmp[1].decode('utf-8')}".encode("utf-8")]
  # inetnum:  148.204/16
  match = re.findall(rb'^inetnum:[\s]*((?:\d{1,3}\.){1}\d{1,3}/\d+)', block, re.MULTILINE)
  if match:
    tmp = match[0].split(b"/")
    return [f"{tmp[0].decode('utf-8')}.0.0/{tmp[1].decode('utf-8')}".encode("utf-8")]
  # IPv6
  match = re.findall(
    rb'^inet6num:[\s]*([0-9a-fA-F:\/]{1,43})', block, re.MULTILINE)
  if match:
    return [match[0]]
  # return None
  
  # no sir, a route is not an inet. 
  # route: specifies the IPv4 address prefix of the route. 
  # Together with the "origin:" attribute, these constitute a combined primary key of the route object. 
  # The address can only be specified as a prefix. It can be one or more IP addresses.
  # HOWEVER... we will combine them in cidr table as our goal is to identify an IP not reverse-engineer ARPA databases
    
  # def parse_property_route(block: str):
  # route IPv4
  match = re.findall(
    rb'^route:[\s]*((?:\d{1,3}\.){3}\d{1,3}/\d{1,2})', block, re.MULTILINE)
  if match:
    return [match[0]]
  # route6 IPv6
  match = re.findall(
    rb'^route6:[\s]*([0-9a-fA-F:\/]{1,43})', block, re.MULTILINE)
  if match:
    return [match[0]]
  return None


def read_blocks(filepath: str) -> list:
  if filepath.endswith('.gz'):
    opemethod = gzip.open
  else:
    opemethod = open
  cust_source = get_source(filepath.split('/')[-1])
  single_block = b''
  blocks = []
  ignored_blocks = 0
  filesize = os.stat(filepath).st_size
  global MODULO
  if filesize >  8000000: MODULO = 100000
  if filesize > 99999999: MODULO = 1000000

  with opemethod(filepath, mode='rb') as f:
    for line in f:
      # skip comments and remarks
      if line.startswith(b'%') or line.startswith(b'#') or line.startswith(b'remarks:'):
        continue
      # block end
      if line.strip() == b'':
        if single_block.lower().startswith((b'inetnum:', b'inet6num:', b'route:', b'route6:', b'as-set:', b'inetnum', b'route', b'inet6num', b'route6', b'mntner', b'person', b'role', b'organisation', b'irt', b'aut-num', b'as-set', b'route-set', b'domain')):
          # add source
          single_block += b"cust_source: %s" % (cust_source)
          blocks.append(single_block)
          if len(blocks) % MODULO == 0:
            logger.debug(
              f"parsed another {MODULO} blocks ({len(blocks)} so far, ignored {ignored_blocks} blocks)")
          single_block = b''
          # comment out to only parse x blocks
          # if len(blocks) == 100:
          #  break
        else:
          # empty block
          single_block = b''
          ignored_blocks += 1
      else:
        single_block += line
  logger.info(f"Total {len(blocks) + ignored_blocks} blocks: Parsed {len(blocks)} blocks, ignored {ignored_blocks} blocks")
  global NUM_BLOCKS
  NUM_BLOCKS = len(blocks)
  return blocks


def updateCounter(counter: int):
  # we do not reset TIME2COMMIT until it's False: this way even when we bypass the modulo, we get a commit close to it
  global TIME2COMMIT
  if not TIME2COMMIT:
    if counter % COMMIT_COUNT == 0:
      TIME2COMMIT = True
  return counter + 1


# https://stackoverflow.com/questions/4578590/python-equivalent-of-filter-getting-two-output-lists-i-e-partition-of-a-list
# partition: how to split lists based of a filter
# partition: trues, falses = partition(lambda x: x > 10, [1,4,12,7,42])
def partition(pred, iterable):
  trues = []
  falses = []
  for item in iterable:
    if pred(item):
      trues.append(item)
    else:
      falses.append(item)
  return trues, falses


def parse_blocks(jobs: Queue, connection_string: str):
  session = setup_connection(connection_string)

  counter = 0
  duplicates = 0
  blocks_done = 0
  global TIME2COMMIT

  start_time = time.time()
  while True:
    block = jobs.get()
    if block is None:
      break
    
    source = parse_property(block, b'cust_source')
    
    # BlockCidr: inetnum, route, inet6num, route6
    inetnum       = parse_property_inetnum(block)
    # route         = parse_property_route(block)   # easier to combine inetnum and route
    
    # BlockMember: mntner, person, role, organisation, irt
    mntner        = parse_property(block, b'mntner')
    person        = parse_property(block, b'person')
    role          = parse_property(block, b'role')
    organisation  = parse_property(block, b'organisation')
    irt           = parse_property(block, b'irt')
    
    # BlockObject: aut-num, as-set, route-set, domain
    autnum        = parse_property(block, b'aut-num')
    asset         = parse_property(block, b'as-set')
    routeset      = parse_property(block, b'route-set')
    domain        = parse_property(block, b'domain')
    
    if not inetnum and not mntner and not person and not role and not organisation and not domain and not irt and not autnum and not asset and not routeset:
      # invalid entry, do not parse
      logger.info(f"Could not parse block {block}.")
      continue
    
    
    # Attribute Name    Presence   Repeat     Indexed
    # inetnum:          mandatory  single     primary/lookup key
    # netname:          mandatory  single     lookup key
    # descr:            optional   multiple  
    # country:          mandatory  multiple  
    # geofeed:          optional   single
    # geoloc:           optional   single    
    # language:         optional   multiple  
    # org:              optional   single     inverse key
    # sponsoring-org:   optional   single    
    # admin-c:          mandatory  multiple   inverse key
    # tech-c:           mandatory  multiple   inverse key
    # abuse-c:          optional   single     inverse key
    # status:           mandatory  single    
    # assignment-size:  optional   single 
    # remarks:          optional   multiple  
    # notify:           optional   multiple   inverse key
    # mnt-by:           mandatory  multiple   inverse key
    # mnt-lower:        optional   multiple   inverse key
    # mnt-routes:       optional   multiple   inverse key
    # mnt-domains:      optional   multiple   inverse key
    # mnt-irt:          optional   multiple   inverse key
    # created:          generated  single
    # last-modified:    generated  single
    # source:           mandatory  single  

    # Attribute Name  Presence   Repeat     Indexed
    # route:          mandatory  single     primary/lookup key
    # descr:          optional   multiple   
    # origin:         mandatory  single     primary/inverse key
    # pingable:       optional   multiple   
    # ping-hdl:       optional   multiple   inverse key
    # holes:          optional   multiple   
    # org:            optional   multiple   inverse key
    # member-of:      optional   multiple   inverse key     <- must match mbrs-by-ref in referenced object
    # inject:         optional   multiple   
    # aggr-mtd:       optional   single     
    # aggr-bndry:     optional   single     
    # export-comps:   optional   single     
    # components:     optional   single     
    # remarks:        optional   multiple   
    # notify:         optional   multiple   inverse key
    # mnt-lower:      optional   multiple   inverse key
    # mnt-routes:     optional   multiple   inverse key
    # mnt-by:         mandatory  multiple   inverse key
    # created:        generated  single     
    # last-modified:  generated  single     
    # source:         mandatory  single     
    
    # BlockCidr: inetnum, route
    # if inetnum or route:
    if inetnum:
      # INETNUM netname: is a name given to a range of IP address space. A netname is made up of letters, digits, the underscore character and the hyphen character. The first character of a name must be a letter, and the last character of a name must be a letter or a digit. It is recommended that the same netname be used for any set of assignment ranges used for a common purpose, such as a customer or service.
      netname = parse_property(block, b'netname')
      if netname:
        object=b'inetnum'
      else:
        # we need to be able to reference routes with aut-num as they have no name
        # netname = route
        netname = inetnum
        object=b'route'
      
      # ROUTE origin: is AS Number of the Autonomous System that originates the route into the interAS routing system. The corresponding aut-num object for this Autonomous System may not exist in the RIPE Database.
      origin = parse_property(block, b'origin')
      
      description = parse_property(block, b'descr')
      remarks = parse_property(block, b'remarks')
      
      country = parse_property(block, b'country')
      # if we have a city object, append it to the country
      # we likely will never have one, instead they can be found in remarks
      # city = parse_property(block, b'city')
      
      # Parent table:
      mntby     = (b'mntner', parse_properties(block, b'mnt-by'))
      memberof  = (b'route-set', parse_properties(block, b'member-of'))
      org       = (b'organisation', parse_properties(block, b'org'))
      mntlowers = (b'mntner', parse_properties(block, b'mnt-lower'))
      mntroutes = (b'mntner', parse_properties(block, b'mnt-routes'))
      mntdomains= (b'mntner', parse_properties(block, b'mnt-domains'))
      mntnfy    = (b'mntner', parse_properties(block, b'mnt-nfy'))
      mntirt    = (b'mntner', parse_properties(block, b'mnt-irt'))
      adminc    = (b'mntner', parse_properties(block, b'admin-c'))
      techc     = (b'mntner', parse_properties(block, b'tech-c'))
      abusec    = (b'mntner', parse_properties(block, b'abuse-c'))
      
      # Emails and local stuff
      notifys   = (b'e-mail', parse_properties(block, b'notify'))
      
      created   = parse_property(block, b'created')
      last_modified = parse_property(block, b'last-modified')
      if not last_modified:
        changed = parse_property(block, b'changed')
        # *@ripe.net   19960624
        # *@domain.com 20060331
        # maybe repeated multiple times, we only take the first
        if re.match(r'^.+?@.+? \d+', changed):
          date = changed.split(" ")[1].strip()
          if len(date) == 8:
            year = int(date[0:4])
            month = int(date[4:6])
            day = int(date[6:8])
            # some sanity checks for dates
            if month >= 1 and month <=12 and day >= 1 and day <= 31:
              last_modified = f"{year}-{month}-{day}"
            else:
              logger.debug(f"ignoring invalid changed date {date}")
          else:
            logger.debug(f"ignoring invalid changed date {date}")
        elif "@" in changed:
          # email in changed field without date
          logger.debug(f"ignoring invalid changed date {changed}")
        else:
          last_modified = changed
      status = parse_property(block, b'status')
      
      # https://stackoverflow.com/questions/2136739/error-handling-in-sqlalchemy
      for cidr in inetnum:
        try:
          # logger.debug('counter1: %d' % counter)
          b = BlockCidr(inetnum=cidr.decode('utf-8'), object=object, netname=netname, autnum=origin, description=description, remarks=remarks, country=country, created=created, last_modified=last_modified, status=status, source=source)
          # logger.debug('counter2: %d' % counter)
          session.add(b)
          # logger.debug('counter3: %d' % counter)
          counter = updateCounter(counter)
          # logger.debug('counter4: %d' % counter)
          # session.flush()
          # logger.debug('counter5: %d' % counter)
        except SQLAlchemyError as e:
          counter -=1
          duplicates +=1
          session.rollback()
          # logger.debug('counter6: %d: %s' % (counter, type(e))) #  <class 'sqlalchemy.exc.IntegrityError'>
          # logger.debug('     -1 : %d: %s' % (counter, e.__class__.__name__))
    
      # inverse keys:
      for parent_type, parents in [mntby, memberof, org, mntlowers, mntroutes, mntdomains, mntnfy, mntirt, adminc, techc, abusec, notifys]:
        for parent in parents:
          try:
            b = BlockParent(parent=parent, parent_type=parent_type, child=netname, child_type=object)
            session.add(b)
            counter = updateCounter(counter)
          except SQLAlchemyError as e:
            counter -=1
            duplicates +=1
            session.rollback()
      
      # local keys:
      for child_type, children in [notifys]:
        for child in children:
          try:
            b = BlockParent(parent=netname, parent_type=object, child=child, child_type=child_type)
            session.add(b)
            counter = updateCounter(counter)
          except SQLAlchemyError as e:
            counter -=1
            duplicates +=1
            session.rollback()
    
    
    
    # Attribute Name  Presence   Repeat     Indexed
    # mntner:         mandatory  single     primary/lookup key
    # descr:          optional   multiple  
    # org:            optional   multiple   inverse key
    # admin-c:        mandatory  multiple   inverse key
    # tech-c:         optional   multiple   inverse key
    # upd-to:         mandatory  multiple   inverse key
    # mnt-nfy:        optional   multiple   inverse key
    # auth:           mandatory  multiple   inverse key
    # remarks:        optional   multiple  
    # notify:         optional   multiple   inverse key
    # mnt-by:         mandatory  multiple   inverse key
    # mnt-ref:        optional   multiple   inverse key 
    # created:        generated  single
    # last-modified:  generated  single
    # source:         mandatory  single  

    # Attribute Name    Presence   Repeat     Indexed
    # organisation:     mandatory  single     primary/lookup key
    # org-name:         mandatory  single     lookup key
    # org-type:         mandatory  single    
    # descr:            optional   multiple  
    # remarks:          optional   multiple  
    # address:          mandatory  multiple 
    # country:          optional   single 
    # phone:            optional   multiple  
    # fax-no:           optional   multiple  
    # e-mail:           mandatory  multiple   lookup key
    # geoloc:           optional   single    
    # language:         optional   multiple  
    # org:              optional   multiple   inverse key
    # admin-c:          optional   multiple   inverse key
    # tech-c:           optional   multiple   inverse key
    # abuse-c:          optional   single     inverse key
    # ref-nfy:          optional   multiple   inverse key
    # mnt-ref:          mandatory  multiple   inverse key
    # notify:           optional   multiple   inverse key
    # mnt-by:           mandatory  multiple   inverse key
    # created:          generated  single
    # last-modified:    generated  single
    # source:           mandatory  single   

    # Attribute Name    Presence   Repeat     Indexed 
    # person:           mandatory  single     lookup key
    # nic-hdl:          mandatory  single     primary/lookup key
    # address:          mandatory  multiple  
    # phone:            mandatory  multiple  
    # fax-no:           optional   multiple  
    # e-mail:           optional   multiple   lookup key
    # org:              optional   multiple   inverse key
    # remarks:          optional   multiple  
    # notify:           optional   multiple   inverse key
    # mnt-by:           mandatory  multiple   inverse key
    # mnt-ref:          optional   multiple   inverse key
    # created:          generated  single
    # last-modified:    generated  single
    # source:           mandatory  single  

    # Attribute Name  Presence   Repeat     Indexed
    # role:           mandatory  single     lookup key
    # nic-hdl:        mandatory  single     primary/lookup key
    # address:        mandatory  multiple  
    # phone:          optional   multiple  
    # fax-no:         optional   multiple  
    # e-mail:         mandatory  multiple   lookup key
    # org:            optional   multiple   inverse key
    # admin-c:        optional   multiple   inverse key
    # tech-c:         optional   multiple   inverse key
    # remarks:        optional   multiple  
    # notify:         optional   multiple   inverse key
    # abuse-mailbox:  optional   single     inverse key
    # mnt-by:         mandatory  multiple   inverse key
    # mnt-ref:        optional   multiple   inverse key
    # created:        generated  single
    # last-modified:  generated  single
    # source:         mandatory  single   
    
    # Attribute Name   Presence   Repeat     Indexed
    # irt:            mandatory  single     primary/lookup key
    # address:        mandatory  multiple  
    # phone:          optional   multiple  
    # fax-no:         optional   multiple  
    # e-mail:         mandatory  multiple   lookup key
    # signature:      optional   multiple  
    # encryption:     optional   multiple  
    # org:            optional   multiple   inverse key
    # admin-c:        mandatory  multiple   inverse key
    # tech-c:         mandatory  multiple   inverse key
    # auth:           mandatory  multiple   inverse key
    # remarks:        optional   multiple  
    # irt-nfy:        optional   multiple   inverse key
    # notify:         optional   multiple   inverse key
    # mnt-by:         mandatory  multiple   inverse key
    # mnt-ref:        optional   multiple   inverse key
    # created:        generated  single
    # last-modified:  generated  single
    # source:         mandatory  single   
    
    # BlockMember: mntner, person, role, organisation, irt
    # mntner = parse_property(block, b'mntner')
    # person = parse_property(block, b'person')
    # role = parse_property(block, b'role')
    # organisation = parse_property(block, b'organisation')
    # irt = parse_property(block, b'irt')
    
    # if mntner or person or role or organisation or irt:
      # if mntner:
        # id = name = mntner
        # object = b'mntner'
      # if person:
        # id = parse_property(block, b'nic-hdl')
        # name = person
        # object = b'person'
      # if role:
        # id = parse_property(block, b'nic-hdl')
        # name = role
        # object = b'role'
      # if organisation:
        # id = organisation
        # name = parse_property(block, b'org-name')
        # object = b'organisation'
      # if irt:
        # id = name = irt
        # object = b'irt'
        
      # description = parse_property(block, b'descr')
      # remarks     = parse_property(block, b'remarks')
      
      # # Parent table:
      # org         =   (b'organisation', parse_properties(block, b'org'))
      # mntby       =   (b'mntner', parse_properties(block, b'mnt-by'))
      # adminc      =   (b'mntner', parse_properties(block, b'admin-c'))
      # techc       =   (b'mntner', parse_properties(block, b'tech-c'))
      # abusec      =   (b'mntner', parse_properties(block, b'abuse-c'))
      # mntnfys     =   (b'mntner', parse_properties(block, b'mnt-nfy'))
      # mntrefs     =   (b'mntner', parse_properties(block, b'mnt-ref'))
      
      # # Emails and l  ocal stuff)
      # address     =   (b'address', parse_properties(block, b'address'))
      # phone       =   (b'phone', parse_properties(block, b'phone'))
      
      # notifys     =   (b'e-mail', parse_properties(block, b'notify'))
      # irtnfys     =   (b'e-mail', parse_properties(block, b'irt-nfy'))
      # emails      =   (b'e-mail', parse_properties(block, b'e-mail'))
      # refnfys     =   (b'e-mail', parse_properties(block, b'ref-nfy'))
      # updtos      =   (b'e-mail', parse_properties(block, b'upd-to'))
      
      # b = BlockCidr(id=id, object=object, name=name, description=description, remarks=remarks)
      # session.add(b)
      # counter = updateCounter(counter)
      
      # # inverse keys:
      # for parent_type, parents in [org, mntby, adminc, techc, abusec, mntnfys, mntrefs]:
        # for parent in parents:
          # try:
            # b = BlockParent(parent=parent, parent_type=parent_type, child=netname, child_type=object)
            # session.add(b)
            # counter = updateCounter(counter)
            # session.flush()
          # except SQLAlchemyError as e:
            # error = str(e.__dict__['orig'])
            # print(type(e), error)
      
      # # local keys:
      # for child_type, children in [address, phone, notifys, irtnfys, emails, refnfys, updtos]:
        # for child in children:
          # try:
            # b = BlockParent(parent=netname, parent_type=object, child=child, child_type=child_type)
            # session.add(b)
            # counter = updateCounter(counter)
            # session.flush()
          # except SQLAlchemyError as e:
            # error = str(e.__dict__['orig'])
            # print(type(e), error)
    
    
    
    # Attribute Name   Presence   Repeat     Indexed 
    # aut-num:         mandatory  single     primary/lookup
    # as-name:         mandatory  single          <- most often == netname
    # descr:           optional   multiple  
    # member-of:       optional   multiple   inverse
    # import-via:      optional   multiple  
    # import:          optional   multiple  
    # mp-import:       optional   multiple  
    # export-via:      optional   multiple  
    # export:          optional   multiple  
    # mp-export:       optional   multiple  
    # default:         optional   multiple  
    # mp-default:      optional   multiple  
    # remarks:         optional   multiple  
    # org:             optional   single     inverse
    # sponsoring-org:  optional   single     inverse
    # admin-c:         mandatory  multiple   inverse
    # tech-c:          mandatory  multiple   inverse
    # abuse-c:         optional   single     inverse
    # status:          generated  single    
    # notify:          optional   multiple   inverse
    # mnt-by:          mandatory  multiple   inverse
    # created:         generated  single
    # last-modified:   generated  single
    # source:          mandatory  single  

    # Attribute Name  Presence   Repeat     Indexed
    # as-set:         mandatory  single     primary/lookup key
    # descr:          optional   multiple
    # members:        optional   multiple  
    # mbrs-by-ref:    optional   multiple   inverse key
    # remarks:        optional   multiple  
    # org:            optional   multiple   inverse key
    # tech-c:         mandatory  multiple   inverse key
    # admin-c:        mandatory  multiple   inverse key
    # notify:         optional   multiple   inverse key
    # mnt-by:         mandatory  multiple   inverse key
    # mnt-lower:      optional   multiple   inverse key
    # created:        generated  single
    # last-modified:  generated  single
    # source:         mandatory  single 

    # Attribute Name  Presence   Repeat     Indexed
    # route-set:      mandatory  single     primary/lookup key
    # descr:          optional   multiple
    # members:        optional   multiple  
    # mp-members:     optional   multiple  
    # mbrs-by-ref:    optional   multiple   inverse key
    # remarks:        optional   multiple  
    # org:            optional   multiple   inverse key
    # tech-c:         mandatory  multiple   inverse key
    # admin-c:        mandatory  multiple   inverse key
    # notify:         optional   multiple   inverse key
    # mnt-by:         mandatory  multiple   inverse key
    # mnt-lower:      optional   multiple   inverse key
    # created:        generated  single
    # last-modified:  generated  single
    # source:         mandatory  single   
    
    # Attribute Name    Presence       Repeat       Indexed
    # domain:           mandatory      single       primary/lookup
    # descr:            optional       multiple
    # org:              optional       multiple     inverse
    # admin-c:          mandatory      multiple     inverse
    # tech-c:           mandatory      multiple     inverse
    # zone-c:           mandatory      multiple     inverse
    # nserver:          mandatory      multiple     inverse
    # ds-rdata:         optional       multiple     inverse
    # remarks:          optional       multiple
    # notify:           optional       multiple     inverse
    # mnt-by:           mandatory      multiple     inverse
    # created:          generated      single
    # last-modified:    generated      single
    # source:           mandatory      single
    
    # BlockObject: aut-num, as-set, route-set, domain
    # autnum = parse_property(block, b'aut-num')
    # asset = parse_property(block, b'as-set')
    # routeset = parse_property(block, b'route-set')
    # domain = parse_property(block, b'domain')
    
    # if autnum or asset or routeset or domain:
      # if autnum:
        # name = autnum
        # object = b'aut-num'
      # if asset:
        # name = asset
        # object = b'as-set'
      # if routeset:
        # name = routeset
        # object = b'route-set'
      # if domain:
        # name = domain
        # object = b'domain'
        
      # description = parse_property(block, b'descr')
      # remarks     = parse_property(block, b'remarks')
      
      # # Parent table:
      # # if asset:
        # # mbrsbyref = (b'aut-num', parse_properties(block, b'mbrs-by-ref'))
      # # else:
        # # # route-set contains a mix of aut-num and routes (CIDR), just great...
        # # # TODO: identify each value and create 2 lists one for each type
        # # mbrsbyref = (None, [])
        # # # mbrsbyref   = (b'organisation', parse_properties(block, b'mbrs-by-ref'))
      # org         = (b'organisation', parse_properties(block, b'org'))
      # mntby       = (b'mntner', parse_properties(block, b'mnt-by'))
      # mntlowers   = (b'mntner', parse_properties(block, b'mnt-lower'))
      # adminc      = (b'mntner', parse_properties(block, b'admin-c'))
      # techc       = (b'mntner', parse_properties(block, b'tech-c'))
      # abusec      = (b'mntner', parse_properties(block, b'abuse-c'))
        
      # # Emails and local stuff
      # notifys     = (b'e-mail', parse_properties(block, b'notify'))
      # members = routes_members = autnums_members = (None, [])
      
      # if asset:
        # members     = (b'aut-num', parse_properties(block, b'members'))
      # else:
        # # route-set contains a mix of aut-num and routes (CIDR), just great...
        # # TODO: identify each value and create 2 lists one for each type: DONE
        # routes, autnums = partition(lambda x: re.search(rb'([0-9a-fA-F:\.]+/{1,3})', x), parse_properties(block, b'members'))
        # print('routes',routes)
        # print('autnums',autnums)
        # if routes:
          # routes_members = (b'route', routes)
        # if autnums:
          # autnums_members = (b'aut-num', autnums)
      
      # b = BlockObject(name=name, object=object, description=description, remarks=remarks)
      # session.add(b)
      # counter = updateCounter(counter)
      
      # # inverse keys:
      # for parent_type, parents in [org, mntby, mntlowers, adminc, techc, abusec]:
        # for parent in parents:
          # try:
            # b = BlockParent(parent=parent, parent_type=parent_type, child=name, child_type=object)
            # session.add(b)
            # counter = updateCounter(counter)
            # session.flush()
          # except SQLAlchemyError as e:
            # error = str(e.__dict__['orig'])
            # print(type(e), error)
      
      # # local keys:
      # for child_type, children in [notifys, members, routes_members, autnums_members]:
        # for child in children:
          # try:
            # b = BlockParent(parent=name, parent_type=object, child=child, child_type=child_type)
            # session.add(b)
            # counter = updateCounter(counter)
            # session.flush()
          # except SQLAlchemyError as e:
            # error = str(e.__dict__['orig'])
            # print(type(e), error)
    
    
    blocks_done += 1
    # we do many more sessions for each block because of the parent table and will inevitably pass the mark
    # counter += 1
    # if counter % COMMIT_COUNT == 0:
    if TIME2COMMIT:
      TIME2COMMIT = False
      try:
        # session.flush()
        session.commit()
      except SQLAlchemyError as e:
        print(type(e), e)
      # session.flush()
      # session.close()
      # session = setup_connection(connection_string)
      
      percent = (blocks_done * NUM_WORKERS * 100) / NUM_BLOCKS
      if percent >= 100:
        percent = 100
      logger.debug('committed {} blocks ({} seconds) {:.1f}% done, ignored {} duplicates'.format(
        counter, round(time.time() - start_time, 2), percent, duplicates))
      start_time = time.time()
    # /block
  # /while true
  
  session.commit()
  logger.debug('committed last blocks')
  session.close()
  logger.debug(f"{current_process().name} finished")


def main(connection_string):
  overall_start_time = time.time()
  # reset database
  setup_connection(connection_string, create_db=True)

  for entry in FILELIST:
    global CURRENT_FILENAME
    CURRENT_FILENAME = entry
    f_name = f"./downloads/{entry}"
    if os.path.exists(f_name):
      logger.info(f"parsing database file: {f_name}")
      start_time = time.time()
      blocks = read_blocks(f_name)
      logger.info(f"database parsing finished: {round(time.time() - start_time, 2)} seconds")

      logger.info('parsing blocks')
      start_time = time.time()

      jobs = Queue()

      workers = []
      # start workers
      logger.debug(f"starting {NUM_WORKERS} processes")
      for _ in range(NUM_WORKERS):
        p = Process(target=parse_blocks, args=(
          jobs, connection_string,), daemon=True)
        p.start()
        workers.append(p)

      # add tasks
      for b in blocks:
        jobs.put(b)
      for _ in range(NUM_WORKERS):
        jobs.put(None)
      jobs.close()
      jobs.join_thread()

      # wait to finish
      for p in workers:
        p.join()

      logger.info(
        f"block parsing finished: {round(time.time() - start_time, 2)} seconds")
      try:
        os.rename(f"./downloads/{entry}", f"./downloads/done/{entry}")
      except Exception as error:
        print(error)
    else:
      logger.info(
        f"File {f_name} not found. Please download using download_dumps.sh")

  CURRENT_FILENAME = "empty"
  logger.info(
    f"script finished: {round(time.time() - overall_start_time, 2)} seconds")


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Create DB')
  parser.add_argument('-c', dest='connection_string', type=str,
            required=True, help="Connection string to the postgres database")
  parser.add_argument("-d", "--debug", action="store_true",
            help="set loglevel to DEBUG")
  parser.add_argument('--version', action='version',
            version=f"%(prog)s {VERSION}")
  args = parser.parse_args()
  if args.debug:
    logger.setLevel(logging.DEBUG)
  main(args.connection_string)


# https://docs.db.ripe.net/RPSL-Object-Types/Description-of-Attributes-Common-to-all-Objects/
# https://docs.db.ripe.net/RPSL-Object-Types/Descriptions-of-Primary-Objects/#description-of-the-aut-num-object
# https://docs.db.ripe.net/RPSL-Object-Types/Descriptions-of-Secondary-Objects/
# Attribute Name  Presence   Repeat     Indexed
# as-block:       mandatory  single     primary/lookup
# descr:          optional   multiple  
# remarks:        optional   multiple  
# org:            optional   multiple   inverse
# notify:         optional   multiple   inverse
# mnt-lower:      optional   multiple   inverse
# mnt-by:         mandatory  multiple   inverse
# created:        generated  single
# last-modified:  generated  single
# source:         mandatory  single  




# https://www.ripe.net/manage-ips-and-asns/resource-management/abuse-c-information/
# https://www.arin.net/resources/manage/irr/userguide/#route6example

######################################################################
# ARIN pub does not offer organisation: nor role: structures.
######################################################################
# /docker/whoisd/downloads/arin.db

# aut-num: This object specifies an ASN and its routing policies. It can have an optional as-set
# aut-num:        AS22346                     optional: not every as-set are included in an aut-num
# as-name:        PINNACLE-TELECOM-1
# mnt-by:         MNT-NRZ               <- super maintainer, usually ARIN itself, useless
# descr:          300 Towson Avenue
                # Fort Smith AR 72901
                # United States
# import:         from AS1239 accept ANY
# import:         from AS7018 accept ANY
# export:         to AS1239 announce AS11528
# export:         to AS7018 announce AS11528
# admin-c:        IPADM192-ARIN
# tech-c:         RD838-ARIN
# source:         ARIN
# created:        2020-07-01T16:53:20Z
# last-modified:  2020-07-01T16:53:20Z

# as-set: This object defines a group of ASNs that are peers in the routing network and through which traffic can be routed. The as-set members can include ASNs as well as the names of other as-sets. This does not indicate if the parent organisation has more ASNs.
# as-set:         AS-WIRELESS-BLUE
# descr:          Wireless Blue Inc.
                # 1257 Sanguinetti Road Unit 111
                # Sonora CA 95370
                # United States
# members:        AS400540                  <- aut-num but not always defined, maybe in as-set members
# members:        AS1001
# members:        AS1002,  AS147297,, AS210527, AS44570, AS400245, AS22951, AS210630, AS151338
# admin-c:        VYHME7-ARIN
# tech-c:         VYHME7-ARIN
# mnt-by:         MNT-WB-436              <- organisation
# created:        2024-09-05T00:32:01Z
# last-modified:  2024-09-05T00:32:01Z
# source:         ARIN

# route/route6: A route object specifies the IPv4 and a route6 object specifies the IPv6 address prefix and the ASN of the autonomous system from which the route originates.
# route:      69.1.71.0/24
# origin:     AS400540                  <- aut-num but not always defined, maybe in as-set members
# descr:      Wireless Blue Inc.
        # 1257 Sanguinetti Road Unit 111
        # Sonora CA 95370
        # United States
# member-of:    RS-WIRELESS-BLUE          <- route-set
# admin-c:    VYHME7-ARIN
# tech-c:     VYHME7-ARIN
# mnt-by:     MNT-AS-780              <- organisation
# created:    2024-09-05T00:36:31Z
# last-modified:  2024-09-05T00:36:31Z
# source:     ARIN

# route/route6: A route object specifies the IPv4 and a route6 object specifies the IPv6 address prefix and the ASN of the autonomous system from which the route originates.
# route6:     2602:F857::/40
# origin:     AS400540                  <- aut-num but not always defined, maybe in as-set members
# descr:      Wireless Blue Inc.
        # 1257 Sanguinetti Road Unit 111
        # Sonora CA 95370
        # United States
# admin-c:    VYHME7-ARIN
# tech-c:     VYHME7-ARIN
# mnt-by:     MNT-WB-436              <- organisation
# created:    2024-09-04T06:29:47Z
# last-modified:  2024-09-04T06:29:47Z
# source:     ARIN

# route-set: This object is a record that defines a group of IP address prefixes or other route-sets. Route sets are used in aut-num objects and other route-set objects. (A route-set is not a group of IRR database route objects.)
# route-set:      RS-WIRELESS-BLUE
# descr:          Wireless Blue Inc.
                # 1257 Sanguinetti Road Unit 111
                # Sonora CA 95370
                # United States
# members:        69.1.71.0/24
# mp-members:     2602:F857::/40
# admin-c:        VYHME7-ARIN
# tech-c:         VYHME7-ARIN
# mnt-by:         MNT-WB-436              <- organisation
# created:        2024-09-03T17:52:02Z
# last-modified:  2024-09-03T17:52:02Z
# source:         ARIN


######################################################################
# AFRINIC
######################################################################
# /docker/whoisd/downloads/afrinic.db

# organisation:   ORG-CNpl1-AFRINIC
# org-name:       CNRST (Centre National pour la Recherche Scientifique et Technique)
# org-type:       LIR
# country:        MA
# address:        ***
# address:        ***
# address:        ***
# address:        Rabat 10102
# e-mail:         ***@cnrst.ma
# phone:          tel:+212-..........
# fax-no:         tel:+212-..........
# admin-c:        RM2528-AFRINIC
# admin-c:        HB1439-AFRINIC
# tech-c:         SAAO2-AFRINIC
# tech-c:         HB1439-AFRINIC
# mnt-ref:        AFRINIC-HM-MNT
# mnt-ref:        MARWAN-MNT
# mnt-by:         AFRINIC-HM-MNT
# notify:         ***@afrinic.net
# remarks:        data has been transferred from RIPE Whois Database 20050221
# changed:        ***@ripe.net 20040415
# changed:        ***@afrinic.net 20050205
# changed:        ***@cnrst.ma 20071007
# changed:        ***@cnrst.ma 20090828
# changed:        ***@afrinic.net 20140916
# changed:        ***@afrinic.net 20170908
# changed:        ***@afrinic.net 20201006
# changed:        ***@afrinic.net 20210708
# changed:        ***@afrinic.net 20220228
# changed:        ***@afrinic.net 20220308
# source:         AFRINIC

# as-block:       AS30980 - AS30980
# type:           REGULAR
# descr:          *** ASN Block ***
# org:            ORG-AFNC1-AFRINIC
# admin-c:        TEAM-AFRINIC
# tech-c:         TEAM-AFRINIC
# mnt-by:         AFRINIC-DB-MNT
# mnt-lower:      AFRINIC-HM-MNT
# changed:        ***@afrinic.net 20170213
# changed:        ***@afrinic.net 20211004
# source:         AFRINIC

# aut-num:        AS30983
# as-name:        MARWAN-AS
# descr:          Moroccan Academic Network - MARWAN
# status:         ASSIGNED
# admin-c:        HB1439-AFRINIC
# admin-c:        RM2528-AFRINIC
# tech-c:         SAAO2-AFRINIC
# tech-c:         HB1439-AFRINIC
# org:            ORG-CNpl1-AFRINIC
# mnt-by:         AFRINIC-HM-MNT
# mnt-routes:     MARWAN-MNT
# remarks:        import:      from AS20965 action pref=100; accept ANY
# remarks:        export:       to AS6713 announce AS30983
# remarks:        import:       from AS6713 action pref=100; accept ANY
# remarks:        export:       to AS20965 announce AS30983
# remarks:        data has been transferred from RIPE Whois Database 20050221
# notify:         ***@cnrst.ma
# changed:        ***@ripe.net 20040521
# changed:        ***@afrinic.net 20050205
# changed:        ***@afrinic.net 20190927
# changed:        ***@afrinic.net 20220310
# changed:        ***@afrinic.net 20240813
# source:         AFRINIC

# inetnum:        196.200.128.0 - 196.200.191.255
# netname:        MA-MARWAN-20040518
# descr:          PROVIDER Local Registry
# descr:          CNRST (Centre National pour la Recherche Scientifique et Technique)
# country:        MA
# admin-c:        RM2528-AFRINIC
# admin-c:        HB1439-AFRINIC
# tech-c:         SAAO2-AFRINIC
# tech-c:         HB1439-AFRINIC
# org:            ORG-CNpl1-AFRINIC
# status:         ALLOCATED PA
# mnt-by:         AFRINIC-HM-MNT
# mnt-lower:      MARWAN-MNT
# remarks:        data has been transferred from RIPE Whois Database 20050221
# remarks:        Geofeed https://marwan.ma/geofeed.csv
# notify:         ***@cnrst.ma
# changed:        ***@ripe.net 20040518
# changed:        ***@afrinic.net 20050205
# changed:        ***@afrinic.net 20220310
# changed:        ***@afrinic.net 20231031
# source:         AFRINIC

# route:          196.200.128.0/18
# origin:         AS30983
# descr:          MARWAN AS
# mnt-by:         MARWAN-MNT
# changed:        ***@cnrst.ma 20211013
# changed:        ***@marwan.ma 20220708
# source:         AFRINIC
# remarks:        Network: noc@marwan.ma
# remarks:        Abuse: abuse@marwan.ma
# remarks:        Security: soc@marwan.ma

# inetnum:        102.216.118.0 - 102.216.118.255
# netname:        MARWAN-ANYCAST
# descr:          CNRST (Centre National pour la Recherche Scientifique et Technique)
# country:        MA
# admin-c:        RM2528-AFRINIC
# admin-c:        HB1439-AFRINIC
# tech-c:         SAAO2-AFRINIC
# tech-c:         HB1439-AFRINIC
# org:            ORG-CNpl1-AFRINIC
# status:         ASSIGNED ANYCAST
# mnt-by:         AFRINIC-HM-MNT
# mnt-lower:      MARWAN-MNT
# mnt-domains:    MARWAN-MNT
# notify:         ***@cnrst.ma
# changed:        ***@afrinic.net 20220426
# source:         AFRINIC

# route:          102.216.118.0/24
# origin:         AS30983
# descr:          MARWAN DNS anycast
# mnt-by:         MARWAN-MNT
# changed:        ***@marwan.ma 20220603
# source:         AFRINIC

# domain:         131.200.196.in-addr.arpa
# descr:          Reverse Adress for ma-marwan-cnrst CNRST 196.200.131
# org:            ORG-CNpl1-AFRINIC
# admin-c:        RM2528-AFRINIC
# tech-c:         RM2528-AFRINIC
# zone-c:         RM2528-AFRINIC
# nserver:        ns1.cnrst.ma
# nserver:        ns2.cnrst.ma
# remarks:        data has been transferred from RIPE Whois Database 20050221
# notify:         ***@marwan.ma
# mnt-by:         MARWAN-MNT
# mnt-lower:      MARWAN-MNT
# changed:        ***@marwan.ma 20050208
# changed:        ***@afrinic.net 20050221
# changed:        ***@marwan.ma 20180612
# source:         AFRINIC

# person:         Name Removed
# address:        Institut National de la Recherche Agronomique
                # Avenue de la Victoire B.P. 415 - Rabat R.P. , MOROCCO
# phone:          tel:+212.........
# fax-no:         tel:+212.........
# e-mail:         ***@ibnawam.inra.org.ma
# nic-hdl:        OS2-AFRINIC
# notify:         ***@ibnawam.inra.org.ma
# mnt-by:         GENERATED-6NI6PNWVCY0UTE7SZ1RK0WK0PS5QO9T1-MNT
# changed:        ***@ibnawam.inra.org.ma 20070104
# source:         AFRINIC

# mntner:         GENERATED-6NI6PNWVCY0UTE7SZ1RK0WK0PS5QO9T1-MNT
# descr:          Auto-generated maintainer
# admin-c:        AGMT2310-AFRINIC
# upd-to:         ***@afrinic.net
# auth:           BCRYPT-PW # Filtered
# mnt-by:         AFRINIC-HM-MNT
# changed:        ***@afrinic.net
# source:         AFRINIC

# mntner:         KANARTEL-MNT
# descr:          Canar Telecom CO. Ltd
# admin-c:        MAMS1-AFRINIC
# admin-c:        MM219-AFRINIC
# tech-c:         WM29-AFRINIC
# tech-c:         AAME1-AFRINIC
# tech-c:         MAMS1-AFRINIC
# tech-c:         MM219-AFRINIC
# tech-c:         MHMS1-AFRINIC
# tech-c:         MZAA2-AFRINIC
# upd-to:         ***@canar.com.sd
# mnt-nfy:        ***@canar.com.sd
# auth:           BCRYPT-PW # Filtered
# notify:         ***@canar.com.sd
# mnt-by:         KANARTEL-MNT
# changed:        ***@canar.com.sd 20060801
# changed:        ***@afrinic.net 20180309
# changed:        ***@afrinic.net 20181106
# changed:        ***@afrinic.net 20210219
# changed:        ***@afrinic.net 20221106
# changed:        ***@afrinic.ne 20221122
# changed:        ***@afrinic.net 20240111
# source:         AFRINIC




# organisation:   ORG-IS28-AFRINIC
# org-name:       Orange Mali SA
# org-type:       LIR
# country:        ML
# address:        ***
# address:        ***
# address:        ***
# address:        ***
# address:        Bamako
# e-mail:         ***@orangemali.net
# e-mail:         ***@orangemali.com
# phone:          tel:+223........
# phone:          tel:+223........
# fax-no:         tel:+223........
# admin-c:        NOC3-AFRINIC
# admin-c:        COS1-AFRINIC
# admin-c:        ABS3-AFRINIC
# admin-c:        FD21-AFRINIC
# tech-c:         NOC3-AFRINIC
# tech-c:         COS1-AFRINIC
# tech-c:         ABS3-AFRINIC
# tech-c:         FD21-AFRINIC
# mnt-ref:        AFRINIC-HM-MNT
# mnt-ref:        MNT-IKATEL
# mnt-by:         AFRINIC-HM-MNT
# notify:         ***@afrinic.net
# remarks:        data has been transferred from RIPE Whois Database 20050221
# changed:        ***@ripe.net 20040415
# changed:        ***@ripe.net 20040604
# changed:        ***@ripe.net 20040609
# changed:        ***@afrinic.net 20050205
# changed:        ***@afrinic.net 20100127
# changed:        ***@afrinic.net 20100218
# changed:        ***@afrinic.net 20131029
# changed:        ***@orangemali.com 20140617
# changed:        ***@orangemali.com 20150327
# changed:        ***@afrinic.net 20170803
# changed:        ***@afrinic.net 20180321
# changed:        ***@afrinic.net 20180712
# changed:        ***@afrinic.net 20240126
# changed:        ***@afrinic.net 20240223
# source:         AFRINIC

# aut-num:        AS30985
# as-name:        IKATELNET
# descr:          IKATEL SA. Service Provider in Mali
# status:         ASSIGNED
# admin-c:        COS1-AFRINIC
# admin-c:        NOC3-AFRINIC
# admin-c:        ABS3-AFRINIC
# admin-c:        FD21-AFRINIC
# tech-c:         COS1-AFRINIC
# tech-c:         NOC3-AFRINIC
# tech-c:         ABS3-AFRINIC
# tech-c:         FD21-AFRINIC
# org:            ORG-IS28-AFRINIC
# mnt-by:         AFRINIC-HM-MNT
# mnt-lower:      MNT-IKATEL
# mnt-routes:     MNT-IKATEL
# remarks:        import:       from AS8346 accept ANY
# remarks:        import:       from AS5511 accept ANY
# remarks:        export:       to AS8346 announce AS30985
# remarks:        export:       to AS5511 announce AS30985
# notify:         ***@orangemali.net
# notify:         ***@orangemali.com
# changed:        ***@ripe.net 20040609
# changed:        ***@afrinic.net 20050205
# changed:        ***@afrinic.net 20100118
# changed:        ***@afrinic.net 20100120
# changed:        ***@afrinic.net 20131029
# changed:        ***@orangemali.com 20211110
# changed:        ***@afrinic.net 20240130
# changed:        ***@afrinic.net 20240226
# source:         AFRINIC
# export:         to AS29571 announce AS30985
# import:         from AS29571 accept ANY

# as-set:         AS-IKATELNET
# descr:          IKATEL-NET
# descr:          IKATEL SA / MALIAN GLOBAL SERVICE PROVIDER
# members:        AS30985
# members:        AS36864
# admin-c:        MA1231-AFRINIC
# tech-c:         MA1231-AFRINIC
# notify:         ***@orangemali.com
# mnt-by:         MNT-IKATEL
# changed:        ***@orangemali.com 20050826
# source:         AFRINIC

# as-set:         AS-SET-OML
# descr:          AS-SET-ORANGE-MALI
# members:        AS30985
# mbrs-by-ref:    ANY
# tech-c:         ABS3-AFRINIC
# admin-c:        ABS3-AFRINIC
# mnt-by:         MNT-IKATEL
# changed:        ***@orangemali.com 20161221
# source:         AFRINIC

# inetnum:        196.200.85.0 - 196.200.85.63
# netname:        DATATECH-IKATEL
# descr:          DATATECH ISP in Bamako
# country:        ML
# admin-c:        MA1231-AFRINIC
# tech-c:         MA1231-AFRINIC
# status:         ASSIGNED PA
# remarks:        http://www.ikatelnet.net
# remarks:        ***************************************************
# remarks:        For spam use :   abuse@orangemali.com
# remarks:        ***************************************************
# notify:         ***@orangemali.com
# mnt-by:         MNT-IKATEL
# mnt-lower:      MNT-IKATEL
# notify:         ***@orangemali.com
# changed:        ***@orangemali.com 20050628
# source:         AFRINIC

# inetnum:        41.221.176.0 - 41.221.191.255
# netname:        ML-IKATEL-20070912
# descr:          IKATEL SA
# descr:          PROVIDER Local Registry
# country:        ML
# admin-c:        ABS3-AFRINIC
# admin-c:        NOC3-AFRINIC
# admin-c:        COS1-AFRINIC
# admin-c:        FD21-AFRINIC
# tech-c:         ABS3-AFRINIC
# tech-c:         NOC3-AFRINIC
# tech-c:         COS1-AFRINIC
# tech-c:         FD21-AFRINIC
# org:            ORG-IS28-AFRINIC
# status:         ALLOCATED PA
# mnt-by:         AFRINIC-HM-MNT
# mnt-lower:      MNT-IKATEL
# notify:         ***@orangemali.net
# notify:         ***@orangemali.com
# changed:        ***@afrinic.net 20070912
# changed:        ***@afrinic.net 20100118
# changed:        ***@afrinic.net 20100120
# changed:        ***@afrinic.net 20131029
# changed:        ***@afrinic.net 20240130
# changed:        ***@afrinic.net 20240226
# source:         AFRINIC

# route:          41.221.176.0/20
# descr:          ROUTE OML 41.221.176.0/20
# origin:         AS30985
# mnt-by:         MNT-IKATEL
# changed:        ***@orangemali.com 20161221
# source:         AFRINIC

# route:          196.200.88.0/21
# descr:          route oml 196.200.88.0/21
# origin:         AS30985
# mnt-by:         MNT-IKATEL
# changed:        ***@orangemali.com 20161227
# source:         AFRINIC

# domain:         80.200.196.in-addr.arpa
# descr:          Reverse delegation for IKATEL
# nserver:        dnsp01.ikatelnet.net
# nserver:        dnsp02.ikatelnet.net
# nserver:        dnsp03.ikatelnet.net
# org:            ORG-IS28-AFRINIC
# admin-c:        ABS3-AFRINIC
# tech-c:         ABS3-AFRINIC
# zone-c:         ABS3-AFRINIC
# mnt-by:         MNT-IKATEL
# mnt-lower:      MNT-IKATEL
# remarks:        Reverse delegation
# changed:        ***@orangemali.com 20041006
# changed:        ***@afrinic.net 20050221
# changed:        ***@orangemali.com 20201028
# changed:        ***@orangemali.com 20210826
# changed:        ***@afrinic.net 20210927
# changed:        ***@orangemali.com 20230926
# source:         AFRINIC

# mntner:         MNT-IKATEL
# descr:          IKATEL Maintainer Object
# admin-c:        MA1231-AFRINIC
# upd-to:         ***@ikatel.net
# auth:           BCRYPT-PW # Filtered
# remarks:        data has been transferred from RIPE Whois Database 20050221
# mnt-by:         MNT-IKATEL
# changed:        ***@afrinic.net 20050205
# changed:        ***@afrinic.net 20161221
# changed:        ***@afrinic.net 20211110
# source:         AFRINIC

# person:         Name Removed
# address:        ***
# address:        ***
# address:        Bamako ACI 2000
# phone:          tel:+223........
# e-mail:         ***@orangemali.com
# nic-hdl:        SD2024-AFRINIC
# mnt-by:         MNT-IKATEL
# changed:        ***@orangemali.com 20070129
# source:         AFRINIC

# role:           Internet Assigned Numbers Authority
# address:        see http://www.iana.org.
# e-mail:         ***@afrinic.net
# admin-c:        TEAM-AFRINIC
# tech-c:         TEAM-AFRINIC
# nic-hdl:        IANA1-AFRINIC
# remarks:        For more information on IANA services
# remarks:        go to IANA web site at http://www.iana.org.
# remarks:        data has been transferred from RIPE Whois Database 20050221
# mnt-by:         AFRINIC-DB-MNT
# changed:        ***@afrinic.net 20050101
# changed:        ***@afrinic.net 20050205
# changed:        ***@afrinic.net 20170710
# source:         AFRINIC


