#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import gzip
import time
from multiprocessing import cpu_count, Queue, Process, Lock, current_process
# https://docs.python.org/2/library/multiprocessing.html#multiprocessing.sharedctypes.Value
from multiprocessing.sharedctypes import Value
import logging
import re
import os
import random

from db.model import BlockCidr, BlockMember, BlockAttr, BlockParent
from db.helper import setup_connection
# https://docs.sqlalchemy.org/en/20/core/operators.html
from sqlalchemy import select, and_, or_, not_
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, PendingRollbackError
from netaddr import iprange_to_cidrs

VERSION = '2.1.0.21'
FILELIST = ['afrinic.db.gz', 'apnic.db.inetnum.gz', 'arin.db.gz', 'lacnic.db.gz', 'ripe.db.inetnum.gz', 'apnic.db.inet6num.gz', 'ripe.db.inet6num.gz']
NUM_WORKERS = cpu_count()
# NUM_WORKERS = 1
# LOG_FORMAT = '%(asctime)-15s - %(name)-9s/%(funcName)20s - %(levelname)-8s - %(processName)-11s %(process)d - %(filename)s - %(message)s'
LOG_FORMAT = '[%(name)s:%(lineno)4s - %(funcName)20s ] %(levelname)-8s: %(processName)-11s %(process)d - %(filename)s - %(message)s'
COMMIT_COUNT = 10000
# COMMIT_COUNT = 300  # testing
BLOCKLOAD_MODULO = {0:10000,8000000:100000,99999999:1000000}
NUM_BLOCKS = 0
CURRENT_FILENAME = "empty"
RESET_DB = False
AUTOFLUSH = False
DEBUG = False

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


# https://eli.thegreenplace.net/2012/01/04/shared-counter-with-pythons-multiprocessing#the-right-way
class CounterShared(object):
  def __init__(self, initval=0):
    self.val = Value('i', initval)
    self.lock = Lock()
  
  def increment(self):
    with self.lock:
      self.val.value += 1
  
  def decrement(self):
    with self.lock:
      self.val.value -= 1
  
  def value(self):
    with self.lock:
      return self.val.value


def get_source(filename: str):
  if filename.startswith('afrinic'):
    return 'afrinic'
  elif filename.startswith('apnic'):
    return 'apnic'
  elif filename.startswith('arin'):
    return 'arin'
  elif 'lacnic' in filename:
    return 'lacnic'
  elif filename.startswith('ripe'):
    return 'ripe'
  else:
    logger.error(f"Can not determine source for {filename}")
  return None

###################### testing ######################
# import re
# block=b'''as-set:         AS-1002-CUSTOMERS
# descr:          Customers
# members:        AS1001
# members:        AS1002,   AS147297, AS210527, AS147297, AS44570, AS400245, AS22951, AS210630, AS151338
# admin-c:        NOA32-ARIN
# tech-c:         NOA32-ARIN
# mnt-by:         MNT-VHL-190
# created:        2022-07-01T17:58:34Z
# last-modified:  2023-09-27T14:44:31Z
# source:         ARIN
# '''
# name = b'members'
# # match = [b'       AS1001', b'       AS1002, AS147297, AS210527, AS44570, AS400245, AS22951, AS210630, AS151338']
# x = b' '.join(list(filter(None, (x.strip().replace(b"%s: " % name, b'').replace(b"%s: " % name, b'') for x in match))))
# # x = b'AS1001   AS1002, AS147297,   AS210527,, AS44570, AS400245, AS22951, AS210630, AS151338'
# list(set( re.sub(r'\W+', ',', x.decode('utf-8')).split(',') ))

# block=b'route:          8.22.97.0/24\norigin:         AS12220\ndescr:          501 John James Audubon\n                Suite 201\n                Amherst NY 14228\n                United States\nmember-of:      RS-IEVOL-AMH\nadmin-c:        DAVID60-ARIN\ntech-c:         NETWO9152-ARIN\ntech-c:         RJDI1-ARIN\nmnt-by:         MNT-IEVOL\ncreated:        2022-03-31T21:24:03Z\nlast-modified:  2022-03-31T21:24:03Z\nsource:         ARIN\ncust_source: arin'
# name = b'mnt-by'
# match = re.findall(rb'^%s:\s?(.+)$' % (name), block, re.MULTILINE)
# # match = [b'        MNT-IEVOL']
# x = b' '.join(list(filter(None, (x.strip().replace(b"%s: " % name, b'').replace(b"%s: " % name, b'') for x in match))))
# # x = b'MNT-IEVOL'
# list(set( re.sub(r'\W+', ',', x.decode('utf-8')).split(',') ))
# # ['MNT', 'IEVOL']    # BUG!! \W+ separates words by spaces and also dashes... solution: use [ ,] instead
# list(set( re.sub(r'[ ,]+', ',', x.decode('utf-8')).split(',') ))

###################### testing ######################


def parse_properties(block: str, name: str) -> list:
  match = re.findall(rb'^%s:\s?(.+)$' % (name), block, re.MULTILINE)
  print
  if match:
    # remove empty lines and remove multiple names
    x = b' '.join(list(filter(None, (x.strip().replace(b"%s: " % name, b'').replace(b"%s: " % name, b'') for x in match))))
    # decode to latin-1 so it can be split
    # also double-split hack to make sure we have a clean list
    # also return uniq values
    # return re.split(',\s+|,|\s+|\n', x.decode('latin-1'))
    return list(set( re.sub(r'[ ,]+', ',', x.decode('utf-8')).split(',') ))
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
    # also return uniq values
    return ' '.join(x.decode('utf-8').split())
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
    ip_start = match[0][0].decode('utf-8')
    ip_end = match[0][1].decode('utf-8')
    cidrs = iprange_to_cidrs(ip_start, ip_end)
    return (str(x).encode('utf-8') for x in cidrs)
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
  # Together with the "origin:" attribute, these constitute a combined primary key of the route attr. 
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
  for cutoff in BLOCKLOAD_MODULO.keys():
    if filesize > cutoff: modulo = BLOCKLOAD_MODULO[cutoff]

  with opemethod(filepath, mode='rb') as f:
    for line in f:
      # skip comments and remarks
      if line.startswith(b'%') or line.startswith(b'#') or line.startswith(b'remarks:'):
        continue
      # block end
      if line.strip() == b'':
        if single_block.lower().startswith((b'inetnum:', b'inet6num:', b'route:', b'route6:', b'as-set:', b'inetnum', b'route', b'inet6num', b'route6', b'mntner', b'person', b'role', b'organisation', b'irt', b'aut-num', b'as-set', b'route-set', b'domain')):
          # add source
          single_block += b"cust_source: %s" % (cust_source.encode('utf-8'))
          blocks.append(single_block)
          if len(blocks) % modulo == 0:
            logger.debug(f"read_blocks: another {modulo} blocks so far, Kept ({len(blocks)} blocks, Ignored {ignored_blocks} blocks, ")
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
  logger.info(f"read_blocks: Kept {len(blocks)} blocks + Ignored {ignored_blocks} blocks = Total {len(blocks) + ignored_blocks} blocks")
  return blocks


def updateCounter(counter: int):
  # we do not reset TIME2COMMIT until it's False: this way even when we bypass the modulo, we get a commit close to it
  if not TIME2COMMIT:
    if counter % COMMIT_COUNT == 0:
      TIME2COMMIT = True
  return counter + 1

def updateCounterLocal(counter: int, time2commit: bool, commit_count=COMMIT_COUNT):
  # we do not reset TIME2COMMIT until it's False: this way even when we bypass the modulo, we get a commit close to it
  if not time2commit:
    if counter % commit_count == 0:
      time2commit = True
  return (counter + 1), time2commit

      # # global variable update is apparently a bit faster then returning 2 variables
      # import timeit
      # TIME2COMMIT = False
      # counter = 0
      # def flocal():
        # time2commit = False
        # for i in range(COMMIT_COUNT + 1):
          # counter, time2commit = (updateCounterLocal, time2commit)

      # def fglobal():
        # for i in range(COMMIT_COUNT + 1):
          # counter = (updateCounter)
      # timeit.timeit(flocal, number=1000)
      # timeit.timeit(fglobal, number=1000)


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


# getParentRow(BlockParent, "4.36.104.120/29")
# getParentRow(BlockParent, "ARIN", ""4.36.104.120/29")
# def getParentRow(session, base, child):
  # return session.query(BlockParent).filter(BlockParent.child == child).first()
# https://docs.sqlalchemy.org/en/20/tutorial/data_select.html#using-select-statements
# https://docs.sqlalchemy.org/en/20/core/operators.html
# v2.0.20:  Okay we have a problem here, in multiprocessing: since 1 route has multiple autnum, we get dupes mntn-by going into parent table.
#           That's not a problem with 1 thread, but in multithread, the select of Process-x occasionally happens before the insert of Process-y and boom we get an IntegrityError
def getParentRow(session, base, parent, parent_type, child, child_type):
  # https://docs.sqlalchemy.org/en/20/tutorial/data_select.html#using-select-statements
  # stmt = select(base).where(base.parent == parent, base.parent_type == parent_type, base.child == child, base.child_type == child_type)
  # return session.execute(stmt).first()
  try:
    session.flush() # if autoflush=True, select will flush; better perf if only select flushes, we spare the flush time from add()
    rows = session.query(base).filter(and_(base.parent == parent, base.parent_type == parent_type, base.child == child, base.child_type == child_type)).first()
  except:
    rows = None
  return rows


# https://docs.sqlalchemy.org/en/20/tutorial/data_select.html#using-select-statements
# https://docs.sqlalchemy.org/en/20/core/operators.html
def getCidrRow(session, base, cidr, autnum):
  stmt = select(base).where(and_(base.inetnum == cidr, base.autnum == autnum))
  # sqlalchemy.exc.InvalidRequestError: This session is in 'prepared' state; no further SQL can be emitted within this transaction.
  try:
    session.flush() # if autoflush=True, select will flush; better perf if only select flushes, we spare the flush time from add()
    # rows = session.query(base).filter(base.inetnum == cidr).first()
    rows = session.execute(stmt).first()
  except:
    rows = None
  logger.debug(f"(cidr=\"{cidr}\",autnum=\"{autnum}\" : rows={rows}")    # ('4.53.100.168/29',)
  return rows


def printDbSize(session, message):
  try:
    countCidr = session.query(BlockCidr).count()
    countParent = session.query(BlockParent).count()
  except Exception as e:
    logger.info(f"{message} countCidr={e.__class__.__name__} countParent={e.__class__.__name__}")
  else:
    logger.info(f"{message} countCidr={countCidr} countParent={countParent}")



def parse_blocks(jobs: Queue, connection_string: str, blocks_processed_total, bskip_total, blocks_duplicates_total):
  # A Session object is basically an ongoing transaction of changes to a database (update, insert, delete). These operations aren't persisted to the database until they are committed (if your program aborts for some reason in mid-session transaction, any uncommitted changes within are lost).
  # The session object registers transaction operations with session.add(), but doesn't yet communicate them to the database until session.flush() is called.
  # session.flush() communicates a series of operations to the database (insert, update, delete). The database maintains them as pending operations in a transaction. The changes aren't persisted permanently to disk, or visible to other transactions until the database receives a COMMIT for the current transaction (which is what session.commit() does).
  # session.commit() commits (persists) those changes to the database.
  # flush() is always called as part of a call to commit() (1).
  # When you use a Session object to query the database, the query will return results both from the database and from the flushed parts of the uncommitted transaction it holds. By default, Session objects autoflush their operations, but this can be disabled.
  session = setup_connection(connection_string)

  # all the value below are PER WORKER
  inserts = 0             # insert main rows
  dupes = 0               # dupes main rows detected
  rollbacks = 0           # dupes main rows missed = race condition
  insertsp = 0            # insert parent rows
  dupesp = 0              # dupes parent rows detected
  rollbacksp = 0          # dupes parent rows missed = race condition
  blocks_processed = 0    # processed rows: bypassed, added, and rollbacked
  bskip = 0               # this worker's blocks skipped
  TIME2COMMIT = False

  seconds = 0.0000000000000001
  seconds_total = 0.0000000000000001
  start_time = time.time()
  while True:
    block = jobs.get()
    if block is None:
      logger.debug(f"------------- End of blocks -------------")
      break
    
    source = parse_property(block, b'cust_source')
    
    # BlockCidr: inetnum, route, inet6num, route6
    inetnum       = parse_property_inetnum(block)   # will always be a list of byte encoded
    # route         = parse_property_route(block)   # easier to combine inetnum and route
    
    # BlockMember: mntner, person, role, organisation, irt
    mntner        = parse_property(block, b'mntner')
    person        = parse_property(block, b'person')
    role          = parse_property(block, b'role')
    organisation  = parse_property(block, b'organisation')
    irt           = parse_property(block, b'irt')
    
    # BlockAttr: aut-num, as-set, route-set, domain
    autnum        = parse_property(block, b'aut-num')
    asset         = parse_property(block, b'as-set')
    routeset      = parse_property(block, b'route-set')
    domain        = parse_property(block, b'domain')
    
    # if not inetnum and not mntner and not person and not role and not organisation and not domain and not irt and not autnum and not asset and not routeset:
    if not inetnum:
      # invalid entry, do not parse
      # logger.info(f"Could not parse block {block}.")
      bskip += 1
      bskip_total.increment()
      continue
    # logger.info(block)

    
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
    # member-of:      optional   multiple   inverse key     <- must match mbrs-by-ref in referenced attr
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
      # INETNUM netname: is a name given to a range of IP address space. 
      # A netname is made up of letters, digits, the underscore character and the hyphen character. 
      # The first character of a name must be a letter, and the last character of a name must be a letter or a digit. 
      # It is recommended that the same netname be used for any set of assignment ranges used for a common purpose, such as a customer or service.
      netname = parse_property(block, b'netname')
      if netname:
        attr='inetnum'
      else:
        # We need to be able to reference routes with aut-num as they have no name.
        # Therefore, we use route==netname in the parent table as parent for inverse keys
        # netname = route = 1.1.1.0/24
        netname = inetnum[0].decode('utf-8')
        attr='route'
      
      # ROUTE origin: is autnum=AS Number of the Autonomous System that originates the route into the interAS routing system. 
      # The corresponding aut-num attr for this Autonomous System may not exist in the RIPE Database.
      autnum = parse_property(block, b'origin')
      
      description = parse_property(block, b'descr')
      remarks = parse_property(block, b'remarks')
      
      country = parse_property(block, b'country')
      # if we have a city attr, append it to the country
      # we likely will never have one, instead they can be found in remarks
      # city = parse_property(block, b'city')
      
      # Parent table:
      mntby     = ('mntner', parse_properties(block, b'mnt-by'))
      memberof  = ('route-set', parse_properties(block, b'member-of'))
      org       = ('organisation', parse_properties(block, b'org'))
      mntlowers = ('mntner', parse_properties(block, b'mnt-lower'))
      mntroutes = ('mntner', parse_properties(block, b'mnt-routes'))
      mntdomains= ('mntner', parse_properties(block, b'mnt-domains'))
      mntnfy    = ('mntner', parse_properties(block, b'mnt-nfy'))
      mntirt    = ('mntner', parse_properties(block, b'mnt-irt'))
      adminc    = ('mntner', parse_properties(block, b'admin-c'))
      techc     = ('mntner', parse_properties(block, b'tech-c'))
      abusec    = ('mntner', parse_properties(block, b'abuse-c'))
      
      # Emails and local stuff
      notifys   = ('e-mail', parse_properties(block, b'notify'))
      
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
              logger.debug(f"ignoring invalid changed date {date} ({attr} {inetnum[0].decode('utf-8')} block={blocks_processed - 1})")
          else:
            logger.debug(f"ignoring invalid changed date {date} ({attr} {inetnum[0].decode('utf-8')} block={blocks_processed - 1})")
        elif "@" in changed:
          # email in changed field without date
          logger.debug(f"ignoring invalid changed date {changed} ({attr} {inetnum[0].decode('utf-8')} block={blocks_processed - 1})")
        else:
          last_modified = changed
      status = parse_property(block, b'status')
      
      # v2.0.19
      # v2.0.21
      session.begin_nested()
      
      # https://stackoverflow.com/questions/2136739/error-handling-in-sqlalchemy
      # https://stackoverflow.com/questions/32461785/sqlalchemy-check-before-insert-in-python
      # logger.debug('----------------------------------------------------- for cidr in inetnum: %s --- % attr')
      for cidr in inetnum:
        # logger.debug(f"inetnum={cidr.decode('utf-8')}, attr={attr}, netname={netname}, autnum={autnum}")
        
        # 1. Looking for an existing Block object for these url value
        # v2.0.20:  Okay we have a problem here, in multiprocessing: since 1 route has multiple autnum, we get dupes mntn-by going into parent table.
        #           That's not a problem with 1 thread, but in multithread, the select of Process-x occasionally happens before the insert of Process-y and boom we get an IntegrityError
        b = getCidrRow(session, BlockCidr, cidr.decode('utf-8'), autnum)
        if b:
          # 2. A Block object exist and so we move on
          dupes += 1
          continue
        # 3. A Block object doesn't exist so we create an instance
        b = BlockCidr(inetnum=cidr.decode('utf-8'), autnum=autnum, netname=netname, attr=attr, description=description, remarks=remarks, country=country, created=created, last_modified=last_modified, status=status, source=source)
        # 4. We create a savepoint in case of race condition 
        # session.begin_nested()
        try:
          # logger.debug('counter2: %d' % inserts)
          logger.debug("%s: BlockCidr %d/%d/%d:%d/%d inserts/blocks/btotal:dupes/dtotal (cidr='%s',autnum='%s',netname='%s','%s',..)" % ('before',inserts,blocks_processed,blocks_processed_total.value(),dupes,blocks_duplicates_total.value(), cidr.decode('utf-8'),autnum,netname,attr))
          session.add(b)
          # logger.debug('counter3: %d' % inserts)
          # The session.add() will not be flushed until the next "query operation" happens on the Session
          # 5. We try to insert and release the savepoint.
          # session.flush()   # supposedly done with add() when autoflush=True
          # session.commit()
          # logger.debug('counter4: %d' % inserts)
        except (IntegrityError) as e:
          # It is absolutely impossible to have fuplicate cidr, therefore that would be an actual error to raise
          # 6. The insert fail due to a concurrent transaction/actual dupe
          # session.rollback()
          rollbacks +=1
          blocks_duplicates_total.increment()
          logger.debug("%s: BlockCidr %d/%d/%d:%d/%d inserts/blocks/btotal:dupes/dtotal (cidr='%s',autnum='%s',netname='%s','%s',..)" % (e.__class__.__name__,inserts,blocks_processed,blocks_processed_total.value(),dupes,blocks_duplicates_total.value(), cidr.decode('utf-8'),autnum,netname,attr))
          # logger.debug('counter6: %d: %s' % (inserts, type(e))) #  <class 'sqlalchemy.exc.IntegrityError'>
          # logger.debug('counter6: %d: %s' % (inserts, type(e))) #  <class 'sqlalchemy.exc.PendingRollbackError'>
          # logger.debug(block)
        except (Exception) as e:
          # session.rollback()
          rollbacks +=1
          logger.error("%s: BlockCidr %d/%d/%d:%d/%d inserts/blocks/btotal:dupes/dtotal (cidr='%s',autnum='%s',netname='%s','%s',..)" % (e.__class__.__name__,inserts,blocks_processed,blocks_processed_total.value(),dupes,blocks_duplicates_total.value(), cidr.decode('utf-8'),autnum,netname,attr))
        else:
          # inserts = updateCounter(inserts)
          inserts, TIME2COMMIT = updateCounterLocal(inserts, TIME2COMMIT)
          # inserts += 1
      # session.commit()
      # Okay.. there are so many of these relationships (order of magnitude 2 or 3 compared to actual inetnums) that we end up with deadlock detected
      # By 31577 blocks we are up to 17633 dupes and down to 37 inserts/s
      # By 95382 blocks we are up to 67665 dupes and down to 15 inserts/s
      
      # logger.debug('----------------------------------------------------- for parent in parents: %s --- % attr')
      # inverse keys:
      # session.begin_nested()
      # for parent_type, parents in [mntby, memberof, org, mntlowers, mntroutes, mntdomains, mntnfy, mntirt, adminc, techc, abusec, notifys]:
      for parent_type, parents in [mntby]:
        for parent in parents:
          # if parent in ('MNT-CLOUD14','MNT-IEVOL','MNT-ESLAC-Z') and netname == '8.224.34.0/24':
            # logger.info("%s: BlockParent %d dupe: select * from parent where parent='%s' and parent_type='%s' and child='%s' and child_type='%s';" % ('before',inserts, parent,parent_type,netname,attr))
            # logger.info(block)
          # 1. Looking for an existing Block object for these url value
          b = getParentRow(session, BlockParent, parent, parent_type, netname, attr)
          if b:
            # 2. A Block object exist and so we move on
            dupesp +=1
            continue
          # 3. A Block object doesn't exist so we create an instance
          b = BlockParent(parent=parent, parent_type=parent_type, child=netname, child_type=attr)
          # 4. We create a savepoint in case of race condition 
          # session.begin_nested()
          try:
            session.add(b)
            # 5. We try to insert and release the savepoint
            # session.flush()   # supposedly done with add() when autoflush=True
            # session.commit()
          except (IntegrityError) as e:
            # 6. The insert fail due to a concurrent transaction/actual dupe
            # session.rollback()
            rollbacksp +=1
            logger.debug("%s: BlockParent dupe %d: select * from parent where parent='%s' and parent_type='%s' and child='%s' and child_type='%s';" % (e.__class__.__name__,inserts, parent,parent_type,netname,attr))
          except Exception as e:
            # session.rollback()
            rollbacksp +=1
            logger.error("%s: BlockParent error %d: ('%s','%s','%s','%s')" % (e.__class__.__name__,inserts, parent,parent_type,netname,attr))
          else:
            # insertsp = updateCounter(inserts)
            # insertsp, TIME2COMMIT = updateCounterLocal(insertsp, TIME2COMMIT)
            insertsp += 1
          
        
      # session.commit()
      # logger.debug('----------------------------------------------------- for child in children: %s --- % attr')
      # local keys:
      # session.begin_nested()
      for child_type, children in [notifys]:
        for child in children:
          # 1. Looking for an existing Block object for these url value
          b = getParentRow(session, BlockParent, netname, attr, child, child_type)
          if b:
            # 2. A Block object exist and so we move on
            dupesp +=1
            continue
          # 3. A Block object doesn't exist so we create an instance
          b = BlockParent(parent=netname, parent_type=attr, child=child, child_type=child_type)
          # 4. We create a savepoint in case of race condition 
          # session.begin_nested()
          try:
            session.add(b)
            # 5. We try to insert and release the savepoint
            # session.flush()   # supposedly done with add() when autoflush=True
            # session.commit()
          except (IntegrityError) as e:
            # 6. The insert fail due to a concurrent transaction/actual dupe
            # session.rollback()
            rollbacksp +=1
            logger.debug("%s: BlockParent dupe %d: ('%s','%s','%s','%s')" % (e.__class__.__name__,inserts, parent,parent_type,netname,attr))
          except Exception as e:
            # session.rollback()
            rollbacksp +=1
            logger.error("%s: BlockParent error %d: ('%s','%s','%s','%s')" % (e.__class__.__name__,inserts, parent,parent_type,netname,attr))
          else:
            # insertsp = updateCounter(inserts)
            # insertsp, TIME2COMMIT = updateCounterLocal(insertsp, TIME2COMMIT)
            insertsp += 1
          
        
      # session.commit()
    
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
        # idd = name = mntner
        # attr = 'mntner'
      # if person:
        # idd = parse_property(block, b'nic-hdl')
        # name = person
        # attr = 'person'
      # if role:
        # idd = parse_property(block, b'nic-hdl')
        # name = role
        # attr = 'role'
      # if organisation:
        # idd = organisation
        # name = parse_property(block, b'org-name')
        # attr = 'organisation'
      # if irt:
        # idd = name = irt
        # attr = 'irt'
        
      # description = parse_property(block, b'descr')
      # remarks     = parse_property(block, b'remarks')
      
      # # Parent table:
      # org         =   ('organisation', parse_properties(block, b'org'))
      # mntby       =   ('mntner', parse_properties(block, b'mnt-by'))
      # adminc      =   ('mntner', parse_properties(block, b'admin-c'))
      # techc       =   ('mntner', parse_properties(block, b'tech-c'))
      # abusec      =   ('mntner', parse_properties(block, b'abuse-c'))
      # mntnfys     =   ('mntner', parse_properties(block, b'mnt-nfy'))
      # mntrefs     =   ('mntner', parse_properties(block, b'mnt-ref'))
      
      # # Emails and local stuff)
      # address     =   ('address', parse_properties(block, b'address'))
      # phone       =   ('phone', parse_properties(block, b'phone'))
      
      # notifys     =   ('e-mail', parse_properties(block, b'notify'))
      # irtnfys     =   ('e-mail', parse_properties(block, b'irt-nfy'))
      # emails      =   ('e-mail', parse_properties(block, b'e-mail'))
      # refnfys     =   ('e-mail', parse_properties(block, b'ref-nfy'))
      # updtos      =   ('e-mail', parse_properties(block, b'upd-to'))
      
      # b = BlockCidr(idd=idd, attr=attr, name=name, description=description, remarks=remarks)
      # session.add(b)
      # inserts = updateCounter(inserts)
      
      # # inverse keys:
      # for parent_type, parents in [org, mntby, adminc, techc, abusec, mntnfys, mntrefs]:
        # for parent in parents:
          # try:
            # b = BlockParent(parent=parent, parent_type=parent_type, child=netname, child_type=attr)
            # session.add(b)
            # inserts = updateCounter(inserts)
            # session.flush()
          # except SQLAlchemyError as e:
            # error = str(e.__dict__['orig'])
            # print(type(e), error)
      
      # # local keys:
      # for child_type, children in [address, phone, notifys, irtnfys, emails, refnfys, updtos]:
        # for child in children:
          # try:
            # b = BlockParent(parent=netname, parent_type=attr, child=child, child_type=child_type)
            # session.add(b)
            # inserts = updateCounter(inserts)
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
    
    # BlockAttr: aut-num, as-set, route-set, domain
    # autnum = parse_property(block, b'aut-num')
    # asset = parse_property(block, b'as-set')
    # routeset = parse_property(block, b'route-set')
    # domain = parse_property(block, b'domain')
    
    # if autnum or asset or routeset or domain:
      # if autnum:
        # name = autnum
        # attr = 'aut-num'
      # if asset:
        # name = asset
        # attr = 'as-set'
      # if routeset:
        # name = routeset
        # attr = 'route-set'
      # if domain:
        # name = domain
        # attr = 'domain'
        
      # description = parse_property(block, b'descr')
      # remarks     = parse_property(block, b'remarks')
      
      # # Parent table:
      # # if asset:
        # # mbrsbyref = ('aut-num', parse_properties(block, b'mbrs-by-ref'))
      # # else:
        # # # route-set contains a mix of aut-num and routes (CIDR), just great...
        # # # TODO: identify each value and create 2 lists one for each type
        # # mbrsbyref = (None, [])
        # # # mbrsbyref   = ('organisation', parse_properties(block, b'mbrs-by-ref'))
      # org         = ('organisation', parse_properties(block, b'org'))
      # mntby       = ('mntner', parse_properties(block, b'mnt-by'))
      # mntlowers   = ('mntner', parse_properties(block, b'mnt-lower'))
      # adminc      = ('mntner', parse_properties(block, b'admin-c'))
      # techc       = ('mntner', parse_properties(block, b'tech-c'))
      # abusec      = ('mntner', parse_properties(block, b'abuse-c'))
        
      # # Emails and local stuff
      # notifys     = ('e-mail', parse_properties(block, b'notify'))
      # members = routes_members = autnums_members = (None, [])
      
      # if asset:
        # members     = ('aut-num', parse_properties(block, b'members'))
      # else:
        # # route-set contains a mix of aut-num and routes (CIDR), just great...
        # # TODO: identify each value and create 2 lists one for each type: DONE
        # routes, autnums = partition(lambda x: re.search(rb'([0-9a-fA-F:\.]+/{1,3})', x), parse_properties(block, b'members'))
        # print('routes',routes)
        # print('autnums',autnums)
        # if routes:
          # routes_members = ('route', routes)
        # if autnums:
          # autnums_members = ('aut-num', autnums)
      
      # b = BlockAttr(name=name, attr=attr, description=description, remarks=remarks)
      # session.add(b)
      # inserts = updateCounter(inserts)
      
      # # inverse keys:
      # for parent_type, parents in [org, mntby, mntlowers, adminc, techc, abusec]:
        # for parent in parents:
          # try:
            # b = BlockParent(parent=parent, parent_type=parent_type, child=name, child_type=attr)
            # session.add(b)
            # inserts = updateCounter(inserts)
            # session.flush()
          # except SQLAlchemyError as e:
            # error = str(e.__dict__['orig'])
            # print(type(e), error)
      
      # # local keys:
      # for child_type, children in [notifys, members, routes_members, autnums_members]:
        # for child in children:
          # try:
            # b = BlockParent(parent=name, parent_type=attr, child=child, child_type=child_type)
            # session.add(b)
            # inserts = updateCounter(inserts)
            # session.flush()
          # except SQLAlchemyError as e:
            # error = str(e.__dict__['orig'])
            # print(type(e), error)
    
    
    blocks_processed += 1
    logger.debug(f"{TIME2COMMIT} blocks_processed {blocks_processed} blocks_processed_total {blocks_processed_total.value()}")
    # wrong:    https://docs.python.org/3/library/multiprocessing.html#multiprocessing.Value
    # blocks_processed_total.value() += 1
    # wrong:    https://stackoverflow.com/questions/2080660/how-to-increment-a-shared-counter-from-multiple-processes
    # with inserts.get_lock():
      # blocks_processed_total.value() += 1
    # still wrong:  https://eli.thegreenplace.net/2012/01/04/shared-counter-with-pythons-multiprocessing#the-right-way
    # with lock:
      # blocks_processed_total.value() += 1
    # https://docs.python.org/2/library/multiprocessing.html#multiprocessing.sharedctypes.Value
    # blocks_processed_total.value() += 1
    blocks_processed_total.increment()
    
    # v2.0.17
    # v2.0.19
    # v2.0.21
    try:
      session.commit()
    except Exception as e:
      session.rollback()
      logger.error(f"{TIME2COMMIT} blocks_processed {blocks_processed} blocks_processed_total {blocks_processed_total.value()} !{e.__class__.__name__}!")
    
    
    # We do many more loops for each block because of the parent table, also we decrement it sometimes, and will inevitably pass the mark. cannot use counter inserts here:
    # if inserts % COMMIT_COUNT == 0:
    # Using a separate counter: inserts for actually added rows makes sense when updating the database, but less sense when building it. Lots of work for little results.
    # if blocks_processed % COMMIT_COUNT == 0:
    # Using a function to increment inserts, that updates a global variable TIME2COMMIT works better when there are more INSERTs then blocks
    if TIME2COMMIT:
      # time.sleep(1)
      TIME2COMMIT = False
      # if blocks_processed == 1: continue
      try:
        session.commit()
      except Exception as e:
        # usually PendingRollbackError, therefore cannot rollback: SAWarning: Session's state has been changed on a non-active transaction - this state will be discarded.
        session.rollback()
        if DEBUG:
          logger.error(f"TIME2COMMIT {e.__class__.__name__}: {e}")
        else:
          seconds = time.time() - start_time
          seconds_total += seconds
          start_time = time.time()
          insertsps = round(inserts / seconds_total)
          insertspps = round(insertsp / seconds_total)
          logger.error('{} {}/{}/{}:{}/{}/{} inserts/dupes/rollbacks:blocks/btotal/bskip + {}/{}/{} insertsp/dupesp/rollbacksp ({:.0f} seconds) {:.0f}% done, ({:.0f}/{:.0f} inserts/p/s)'.format(e.__class__.__name__, inserts,dupes,rollbacks,blocks_processed,blocks_processed_total.value(),bskip, insertsp,dupesp,rollbacksp, seconds, percent, insertsps,insertspps))# printDbSize(session, 'after')
        # v2.0.19: [create_db: 959 -         parse_blocks ] ERROR   : Process-4   20 - arin.db.gz - TIME2COMMIT StatementError: (builtins.RecursionError) maximum recursion depth exceeded
        #          [SQL: RELEASE SAVEPOINT sa_savepoint_144]
      else:
        # session.close()
        # session = setup_connection(connection_string)
        
        # each work will perform roughly the same number of blocks, but this number will never be the same
        # therefore blocks_processed * NUM_WORKERS will NEVER be == NUM_BLOCKS
        # percent = (blocks_processed * NUM_WORKERS * 100) / NUM_BLOCKS
        percent = (blocks_processed * 100) / NUM_BLOCKS
        if percent >= 100: percent = 100
        seconds = time.time() - start_time
        seconds_total += seconds
        start_time = time.time()
        insertsps = round(inserts / seconds_total)
        insertspps = round(insertsp / seconds_total)
        logger.info('committed {}/{}/{}:{}/{}/{} inserts/dupes/rollbacks:blocks/btotal/bskip + {}/{}/{} insertsp/dupesp/rollbacksp ({:.0f} seconds) {:.0f}% done, ({:.0f}/{:.0f} inserts/p/s)'.format(inserts,dupes,rollbacks,blocks_processed,blocks_processed_total.value(),bskip, insertsp,dupesp,rollbacksp, seconds, percent, insertsps,insertspps))# printDbSize(session, 'after')
        session.begin_nested()
      # /commit
    # /block
  # /while true
  
  session.commit()
  percent = (blocks_processed * 100) / NUM_BLOCKS
  if percent >= 100: percent = 100
  seconds = time.time() - start_time
  seconds_total += seconds
  start_time = time.time()
  insertsps = round(inserts / seconds_total)
  insertspps = round(insertsp / seconds_total)
  logger.info('done {}/{}/{}:{}/{}/{} inserts/dupes/rollbacks:blocks/btotal/bskip + {}/{}/{} insertsp/dupesp/rollbacksp ({:.0f} seconds) {:.0f}% done, ({:.0f}/{:.0f} inserts/p/s)'.format(inserts,dupes,rollbacks,blocks_processed,blocks_processed_total.value(),bskip, insertsp,dupesp,rollbacksp, seconds, percent, insertsps,insertspps))
  # printDbSize(session, 'done')
  session.close()


def main(connection_string):
  overall_start_time = time.time()
  setup_connection(connection_string, RESET_DB)

  for entry in FILELIST:
    global CURRENT_FILENAME
    CURRENT_FILENAME = entry
    f_name = f"./downloads/{entry}"
    if os.path.exists(f_name):
      logger.info(f"loading database file: {f_name}")
      start_time = time.time()
      blocks = read_blocks(f_name)
      # blocks = read_blocks(f_name)[:10000]  # testing
      global NUM_BLOCKS
      NUM_BLOCKS = len(blocks)
      
      seconds = time.time() - start_time
      seconds_total = seconds
      start_time = time.time()
      logger.info(f"file loading finished: {round(seconds)} seconds ({round(NUM_BLOCKS / seconds)} blocks/s)")

      jobs = Queue()
      # lock = Lock()
      # blocks_processed_total = Value('i', 0, lock=lock)
      # bskip_total = Value('i', 0, lock=lock)
      # Classes seem faster
      blocks_processed_total = CounterShared(0)
      bskip_total = CounterShared(0)
      blocks_duplicates_total = CounterShared(0)

      workers = []
      # start workers
      logger.info(f"BLOCKS PARSING START: starting {NUM_WORKERS} processes for {NUM_BLOCKS} blocks (~{round(NUM_BLOCKS/NUM_WORKERS)} per worker)")
      for _ in range(NUM_WORKERS):
        p = Process(target=parse_blocks, args=(jobs, connection_string, blocks_processed_total, bskip_total, blocks_duplicates_total), daemon=True)
        p.start()
        workers.append(p)

      # add tasks
      random.shuffle(blocks)
      for b in blocks:
        jobs.put(b)
      seconds = time.time() - start_time
      seconds_total += seconds
      start_time = time.time()
      logger.info(f"blocks load into workers finished: {round(seconds)} seconds")

      for _ in range(NUM_WORKERS):
        jobs.put(None)
      jobs.close()
      jobs.join_thread()

      # wait to finish
      for p in workers:
        p.join()

      seconds = time.time() - start_time
      seconds_total += seconds
      logger.info(f"BLOCKS PARSING DONE: {round(seconds_total)} seconds ({round(blocks_processed_total.value() / seconds_total)} blocks/s) for {blocks_processed_total.value()} blocks out of {NUM_BLOCKS}")
      try:
        os.rename(f"./downloads/{entry}", f"./downloads/done/{entry}")
      except Exception as error:
        logger.error(error)
    else:
      logger.info(
        f"File {f_name} not found. Please download using download_dumps.sh")

  CURRENT_FILENAME = "empty"
  logger.info(
    f"script finished: {round(time.time() - overall_start_time, 2)} seconds")


if __name__ == '__main__':
  # https://docs.python.org/3.10/library/argparse.html
  # https://docs.python.org/3/library/argparse.html#argparse.ArgumentParser
  parser = argparse.ArgumentParser(description='Create DB')
  parser.add_argument('-c', '--connection_string', dest='connection_string', type=str, required=True, help="Connection string to the postgres database")
  parser.add_argument("-d", "--debug", action='store_true', default=DEBUG, help="set loglevel to DEBUG")
  parser.add_argument('--reset_db', action='store_true', default=RESET_DB, help="reset the database")
  parser.add_argument('--commit_count', type=int, default=COMMIT_COUNT, help="commit every nth")
  parser.add_argument('--version', action='version', version=f"%(prog)s {VERSION}")
  
  args = parser.parse_args()
  # args = parser.parse_args('-c XXX --reset_db --commit_count 10'.split())
  # print('xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',args)
  # print('xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',args.reset_db)
  # print('xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',args.commit_count)
  # exit()
  
  if args.debug: logger.setLevel(logging.DEBUG)
  DEBUG         = args.debug
  RESET_DB      = args.reset_db
  COMMIT_COUNT  = args.commit_count
  
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

# v2.0.15 215 inserts/s: 1 commit/insert, 1 nested/insert, autoflush
# [create_db: 997 -         parse_blocks() ] INFO    : Process-4   18 - arin.db.gz - committed 35567/10000/39866 inserts/blocks/total (165.55 seconds) 32.1% done, ignored 339/9509 dupes/total (215 inserts/s)
# [create_db: 997 -         parse_blocks() ] INFO    : Process-2   16 - arin.db.gz - committed 35826/10000/39911 inserts/blocks/total (165.7 seconds) 32.1% done, ignored 261/9509 dupes/total (216 inserts/s)
# [create_db: 997 -         parse_blocks() ] INFO    : Process-1   15 - arin.db.gz - committed 35380/10000/39950 inserts/blocks/total (165.89 seconds) 32.1% done, ignored 371/9509 dupes/total (213 inserts/s)
# [create_db: 997 -         parse_blocks() ] INFO    : Process-3   17 - arin.db.gz - committed 35825/10000/40261 inserts/blocks/total (167.43 seconds) 32.4% done, ignored 284/9510 dupes/total (214 inserts/s)
# v2.0.16 300 inserts/s: 1 commit/block, 1 nested/insert, autoflush
# [create_db:1004 -         parse_blocks() ] INFO    : Process-1   17 - arin.db.gz - committed 35520/10000/39651 inserts/blocks/total (114.42 seconds) 31.9% done, ignored 553/10549 dupes/total (310 inserts/s)
# [create_db:1004 -         parse_blocks() ] INFO    : Process-2   18 - arin.db.gz - committed 35714/10000/40075 inserts/blocks/total (115.78 seconds) 32.2% done, ignored 614/10555 dupes/total (308 inserts/s)
# [create_db:1004 -         parse_blocks() ] INFO    : Process-4   20 - arin.db.gz - committed 35723/10000/40112 inserts/blocks/total (115.91 seconds) 32.3% done, ignored 583/10555 dupes/total (308 inserts/s)
# [create_db:1004 -         parse_blocks() ] INFO    : Process-3   19 - arin.db.gz - committed 35682/10000/40131 inserts/blocks/total (115.99 seconds) 32.3% done, ignored 549/10555 dupes/total (308 inserts/s)
# v2.0.17 317 inserts/s: 1 commit/block, 1 nested/insert, no_autoflush
# [create_db:1004 -         parse_blocks() ] INFO    : Process-2   18 - arin.db.gz - committed 35794/10000/39876 inserts/blocks/total (112.95 seconds) 32.1% done, ignored 559/10538 dupes/total (317 inserts/s)
# [create_db:1004 -         parse_blocks() ] INFO    : Process-1   17 - arin.db.gz - committed 35611/10000/39957 inserts/blocks/total (113.16 seconds) 32.1% done, ignored 557/10541 dupes/total (315 inserts/s)
# [create_db:1004 -         parse_blocks() ] INFO    : Process-4   20 - arin.db.gz - committed 35618/10000/40044 inserts/blocks/total (113.45 seconds) 32.2% done, ignored 579/10544 dupes/total (314 inserts/s)
# [create_db:1004 -         parse_blocks() ] INFO    : Process-3   19 - arin.db.gz - committed 35585/10000/40112 inserts/blocks/total (113.66 seconds) 32.3% done, ignored 593/10544 dupes/total (313 inserts/s)
# v2.0.19 379 inserts/s: 1 commit/block/worker, 1 nested/block, no_autoflush
# [create_db: 979 -         parse_blocks ] INFO    : Process-2   18 - arin.db.gz - committed 35691/10000/39909 inserts/blocks/total (94.05 seconds) 32.1% done, ignored 546/10489 dupes/total (379 inserts/s)
# [create_db: 979 -         parse_blocks ] INFO    : Process-1   17 - arin.db.gz - committed 35667/10000/39909 inserts/blocks/total (94.06 seconds) 32.1% done, ignored 542/10489 dupes/total (379 inserts/s)
# [create_db: 979 -         parse_blocks ] INFO    : Process-3   19 - arin.db.gz - committed 35629/10000/40054 inserts/blocks/total (94.46 seconds) 32.2% done, ignored 568/10494 dupes/total (377 inserts/s)
# [create_db: 979 -         parse_blocks ] INFO    : Process-4   20 - arin.db.gz - committed 35615/10000/40150 inserts/blocks/total (94.67 seconds) 32.3% done, ignored 584/10494 dupes/total (376 inserts/s)
# v2.0.19 374 inserts/s: 1 commit/block/worker, 1 nested/block, autoflush
# [create_db: 979 -         parse_blocks ] INFO    : Process-2   18 - arin.db.gz - committed 35560/10000/39809 inserts/blocks/total (94.96 seconds) 32.0% done, ignored 567/10494 dupes/total (374 inserts/s)
# [create_db: 979 -         parse_blocks ] INFO    : Process-3   19 - arin.db.gz - committed 35632/10000/39885 inserts/blocks/total (95.11 seconds) 32.1% done, ignored 555/10494 dupes/total (375 inserts/s)
# [create_db: 979 -         parse_blocks ] INFO    : Process-4   20 - arin.db.gz - committed 35776/10000/40095 inserts/blocks/total (95.63 seconds) 32.3% done, ignored 525/10498 dupes/total (374 inserts/s)
# [create_db: 979 -         parse_blocks ] INFO    : Process-1   17 - arin.db.gz - committed 35666/10000/40227 inserts/blocks/total (95.94 seconds) 32.4% done, ignored 595/10498 dupes/total (372 inserts/s)
# v2.0.20 compare 1 NUM_WORKERS with 10000 blocks: cidr=1746 parent=4583
# [create_db: 346 -         parse_blocks ] INFO    : Process-1   17 - arin.db.gz - committed 1746/0/0:1746/1746/8254 inserts/dupes/rollbacks:blocks/btotal/bskip + 8254/1846/126 insertsp/dupesp/rollbacksp (0 seconds) 1.0% done, (0.01 inserts/s)
# [create_db:1085 -                 main ] INFO    : MainProcess 16 - arin.db.gz - BLOCKS PARSING DONE: 15 seconds (669 blocks/s) for 10000 blocks
# v2.0.20 compare 2 NUM_WORKERS with 10000 blocks
# [create_db: 346 -         parse_blocks ] INFO    : Process-2   18 - arin.db.gz - committed 874/0/0:874/1745/4285 inserts/dupes/rollbacks:blocks/btotal/bskip + 8254/927/46 insertsp/dupesp/rollbacksp (11 seconds) 0.5% done, (0.01 inserts/s)
# [create_db: 346 -         parse_blocks ] INFO    : Process-1   17 - arin.db.gz - committed 872/0/0:872/1746/3969 inserts/dupes/rollbacks:blocks/btotal/bskip + 8254/919/52 insertsp/dupesp/rollbacksp (17 seconds) 0.5% done, (0.02 inserts/s)
# [create_db:1085 -                 main ] INFO    : MainProcess 16 - arin.db.gz - BLOCKS PARSING DONE: 10 seconds (1034 blocks/s) for 10000 blocks
# v2.0.20 compare 4 NUM_WORKERS with 10000 blocks
# [create_db: 348 -         parse_blocks ] INFO    : Process-3   19 - arin.db.gz - committed 439/0/0:439/1743/2277 inserts/dupes/rollbacks:blocks/btotal/bskip + 8254/471/11 insertsp/dupesp/rollbacksp (14 seconds) 0.4% done, (0.03/93 inserts/p/s)
# [create_db: 348 -         parse_blocks ] INFO    : Process-2   18 - arin.db.gz - committed 448/0/0:448/1744/2255 inserts/dupes/rollbacks:blocks/btotal/bskip + 8254/472/24 insertsp/dupesp/rollbacksp (10 seconds) 0.4% done, (0.02/95 inserts/p/s)
# [create_db: 348 -         parse_blocks ] INFO    : Process-1   17 - arin.db.gz - committed 432/0/0:432/1745/2068 inserts/dupes/rollbacks:blocks/btotal/bskip + 8254/456/18 insertsp/dupesp/rollbacksp (16 seconds) 0.4% done, (0.07/92 inserts/p/s)
# [create_db: 348 -         parse_blocks ] INFO    : Process-4   20 - arin.db.gz - committed 427/0/0:427/1746/1654 inserts/dupes/rollbacks:blocks/btotal/bskip + 8254/447/13 insertsp/dupesp/rollbacksp (20 seconds) 0.4% done, (0.01/91 inserts/p/s)
# [create_db:1093 -                 main ] INFO    : MainProcess 16 - arin.db.gz - BLOCKS PARSING DONE: 7 seconds (1536 blocks/s) for 10000 blocks
# v2.0.20 1 452 blocks/s: 1 begin+commit/insert as recommended, autoflush:
# [create_db:1038 -         parse_blocks ] INFO    : Process-1   17 - arin.db.gz - done 28594/0/0:28594/113895/2791 inserts/dupes/rollbacks:blocks/btotal/bskip + 23674/6034/807 insertsp/dupesp/rollbacksp (69 seconds) 23% done, (114/95 inserts/p/s)
# [create_db:1038 -         parse_blocks ] INFO    : Process-4   20 - arin.db.gz - done 28528/0/0:28528/113895/2198 inserts/dupes/rollbacks:blocks/btotal/bskip + 23604/6057/835 insertsp/dupesp/rollbacksp (69 seconds) 23% done, (114/94 inserts/p/s)
# [create_db:1038 -         parse_blocks ] INFO    : Process-3   19 - arin.db.gz - done 28378/0/0:28378/113895/2951 inserts/dupes/rollbacks:blocks/btotal/bskip + 23514/6059/745 insertsp/dupesp/rollbacksp (68 seconds) 23% done, (114/94 inserts/p/s)
# [create_db:1038 -         parse_blocks ] INFO    : Process-2   18 - arin.db.gz - done 28395/0/0:28395/113895/2485 inserts/dupes/rollbacks:blocks/btotal/bskip + 23283/6166/848 insertsp/dupesp/rollbacksp (67 seconds) 23% done, (114/93 inserts/p/s)
# [create_db:1098 -                 main ] INFO    : MainProcess 16 - arin.db.gz - BLOCKS PARSING DONE: 252 seconds (452 blocks/s) for 113895 blocks out of 124320
# v2.0.20 compare 1 NUM_WORKERS with 10000 blocks:                                        cidr=1746 parent=1846, 0% loss
# v2.0.21 1 331 blocks/s: 1 begin+commit/block, autoflush:                                cidr=1683 parent=1846, 4% loss, terrible
# v2.0.21 1 282 blocks/s: 1 begin+commit/subblock, autoflush + shuffle:                   cidr=1746 parent=1846, 0% loss
# v2.0.21 1 348 blocks/s: 1 begin+commit/block, autoflush    + shuffle:                   cidr=1746 parent=1846, 0% loss
# v2.0.21 1 337 blocks/s: 1 begin+commit/block, autoflush    + shuffle + 1 flush/select:  cidr=1746 parent=1846, 0% loss   adding flushes definitely slow things down
# v2.0.21 1 356 blocks/s: 1 begin+commit/block, no_autoflush + shuffle                 :  cidr=1746+/- parent=1846, 0+/-1% loss   removing all flushes definitely speeds things up but we randomely lose cidrs
# v2.0.21 1 466 blocks/s: 1 begin+commit/1000block, no_autoflush + shuffle             :  cidr=4 parent=4,     100% loss   cannot select smth that was not commited...
# v2.0.21 1 258 blocks/s: 1 begin+commit/1000block, no_autoflush + shuffle +flush/select: cidr=118 parent=136,  93% loss   flush before select helps but commits get Process 55923 waits for ShareLock on transaction 5724382; blocked by process 55925.
# v2.0.21 1 366 blocks/s: 1 begin+commit/rnd block, autoflush    + shuffle +flush/select: cidr=rnd parent=rnd, rnd% loss   random commit_count produces random results. I have random feelings about that.
# v2.0.21 1 337 blocks/s: 1 begin+commit/block, autoflush    + shuffle + 1 flush/select:  cidr=1746 parent=1846, 0% loss   adding flushes definitely slow things down
# v2.0.21 1 192 blocks/s: 1 begin+flush/block, autoflush + shuffle + 1 flush/block:       cidr=952 parent=1029, rnd% loss  flush supposedly maintains them as pending operations in a transaction, but this proves they are not visible to other transactions
# v2.0.21 1 348 blocks/s: 1 begin+commit/block, no_autoflush + shuffle + 1 flush/select:  cidr=1746 parent=1846, 0% loss   flush before select seems to give consistant results, best solution so far


