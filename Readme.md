# WHOISd: Local whois

Provides a local PostgreSQL database replica of ARPA (ARIN/APNIC/LACNIC/AfriNIC/RIPE) to avoid being rate-limited with mass whois queries.
After the parsing is finished you can get the infos for any IPv4 or IPv6 by querying the database.

This project was used in analysing some data dumps and cross referencing the IPs with the networks.
It can also be used to easily search for netranges assigned to a company in interest.

I recommend using the docker setup because it removes the hassle of installing everything manually.

Hint: The Database can grow fast so be sure to have enough space. On docker my postgres database uses 4.066GB of space.

# Requirements

- Python3 >= 3.3
- postgresql
- python3-netaddr
- python3-psycopg
- python3-sqlalchemy

# Docker

## Docker-Compose build (prefered)

If you have checked out the GIT repo you can run the script via `docker compose`.
I included some binstubs so you don't have to deal with all the docker commands.

If you run

```sh
git clone https://github.com/audioscavenger/whoisd
cd whoisd
./bin/whoisd
```

the image will be built, a postgres database is connected, the files are downloaded and the parsing begins.
* The database stays up after the run (you can see it via `docker ps`) so you can connect it to your script.
* The whoisd container only downloads the ARPA databases and parse them into the database container. It stops when done.

For a one shot query you can run

```
./bin/query 1.1.1.1
```

or

```
./bin/query 2606:4700:4700::1001
```

Or for a psql prompt

```
./bin/psql
```

### Usage
Example of Compose command:
`command: -c postgresql+psycopg://whoisd:whoisd@db:5432/whoisd --debug --commit_count 10`

```
usage: create_db.py [-h] -c CONNECTION_STRING [-d] [--version] [-R] [--commit_count COMMIT_COUNT]

Create DB

options:
  -h, --help            show this help message and exit
  -c CONNECTION_STRING, --connection_string CONNECTION_STRING
                        Connection string to the postgres database
  -d, --debug           set loglevel to DEBUG
  --version             show program's version number and exit
  -R, --reset_db        reset the database
  --commit_count COMMIT_COUNT
                        commit every nth block
```



## Docker-download (TBD)
- I did not push this image to docker yet -

You can simply pull the image from Docker Hub and connect it to a local database via

```sh
docker pull audioscavenger/whoisd
docker run --rm audioscavenger/whoisd -c postgresql://user:pass@db:5432/whoisd
```

Or cou can connect the docker container to another database container.

```sh
docker run --name whoisd_db -e POSTGRES_DB=whoisd -e POSTGRES_USER=whoisd -e POSTGRES_PASSWORD=whoisd -d postgres:9-alpine
docker run --rm --link whoisd_db:postgres audioscavenger/whoisd -c postgresql://user:pass@db:5432/whoisd
```

# Manual Installation

Installation of needed packages (Example on Ubuntu 16.04):

```sh
apt install postgresql python3 python3-netaddr python3-psycopg2 python3-sqlalchemy
```

or -

```sh
apt install postgresql python3 python-pip
pip install -r requirements.txt
```

Create PostgreSQL database (Use "whoisd" as password):

```sh
sudo -u postgres createuser --pwprompt --createdb whoisd
sudo -u postgres createdb --owner=whoisd whoisd
```

Prior to starting this script you need to download the database dumps by executing:

```sh
./download_dumps.sh
```

After importing you can lookup an IP address like:

```sql
SELECT block.inetnum, block.netname, block.country, block.description, block.maintained_by, block.created, block.last_modified, block.source FROM block WHERE block.inetnum >> '2001:db8::1' ORDER BY block.inetnum DESC;
SELECT block.inetnum, block.netname, block.country, block.description, block.maintained_by, block.created, block.last_modified, block.source FROM block WHERE block.inetnum >> '8.8.8.8' ORDER BY block.inetnum DESC;
```

or -

```bash
./query_db.sh 192.0.2.1
```

# Sample run (docker compose)

```
$ ./bin/whoisd
Creating network "ripe_default" with the default driver
Creating volume "ripe_pg_data" with local driver
Creating ripe_db_1
Downloading afrinic.db.gz...
Connecting to ftp.afrinic.net (196.216.2.24:21)
afrinic.db.gz        100% |****************************************************************************************************************************|  5419k  0:00:00 ETA
...
docker-compose -f docker-compose.yml run --rm --service-ports whoisd
[+] Creating 1/0
 ✔ Container whoisd-db  Created                                                                                                                                                                         0.0s
[+] Running 1/1
 ✔ Container whoisd-db  Started                                                                                                                                                                         0.2s
pwd=/app
whoami=uid=1000(app) gid=1000(app) groups=1000(app)
./download_dumps.sh
SKIP: arin.db.gz
SKIP: afrinic.db.gz
/app/create_db.py -c postgresql+psycopg://whoisd:whoisd@db:5432/whoisd --debug
[afrinic.db.gz:1060 -                 main() ] INFO    : MainProcess 14 - afrinic.db.gz - File ./downloads/afrinic.db.gz not found. Please download using download_dumps.sh
[apnic.db.inetnum.gz:1060 -                 main() ] INFO    : MainProcess 14 - apnic.db.inetnum.gz - File ./downloads/apnic.db.inetnum.gz not found. Please download using download_dumps.sh
[arin.db.gz:1011 -                 main() ] INFO    : MainProcess 14 - arin.db.gz - loading database file: ./downloads/arin.db.gz
[arin.db.gz: 254 -          read_blocks() ] INFO    : MainProcess 14 - arin.db.gz - read_blocks: Kept 124320 blocks + Ignored 0 blocks = Total 124320 blocks
[arin.db.gz:1016 -                 main() ] INFO    : MainProcess 14 - arin.db.gz - file loading finished: 1.61 seconds (77217 blocks/s)
[arin.db.gz:1029 -                 main() ] INFO    : MainProcess 14 - arin.db.gz - BLOCKS PARSING START: starting 4 processes for 124320 blocks (~31080 per worker)
[arin.db.gz:1040 -                 main() ] INFO    : MainProcess 14 - arin.db.gz - blocks load into workers finished: 0.24 seconds
[arin.db.gz: 988 -         parse_blocks() ] INFO    : Process-3   17 - arin.db.gz - committed 0/10000/39745 inserts/blocks/total (34.43 seconds) 32.0% done, ignored 0/8254 dupes/total (0 inserts/s)
[arin.db.gz: 988 -         parse_blocks() ] INFO    : Process-1   15 - arin.db.gz - committed 0/10000/39859 inserts/blocks/total (34.53 seconds) 32.1% done, ignored 0/8254 dupes/total (0 inserts/s)
[arin.db.gz: 988 -         parse_blocks() ] INFO    : Process-2   16 - arin.db.gz - committed 0/10000/40135 inserts/blocks/total (34.82 seconds) 32.3% done, ignored 0/8254 dupes/total (0 inserts/s)
[arin.db.gz: 988 -         parse_blocks() ] INFO    : Process-4   18 - arin.db.gz - committed 0/10000/40250 inserts/blocks/total (34.9 seconds) 32.4% done, ignored 0/8254 dupes/total (0 inserts/s)
[arin.db.gz: 988 -         parse_blocks() ] INFO    : Process-1   15 - arin.db.gz - committed 27799/20000/79820 inserts/blocks/total (145.57 seconds) 64.2% done, ignored 230/9134 dupes/total (154 inserts/s)
[arin.db.gz: 988 -         parse_blocks() ] INFO    : Process-3   17 - arin.db.gz - committed 27909/20000/79876 inserts/blocks/total (146.13 seconds) 64.3% done, ignored 212/9134 dupes/total (155 inserts/s)
[arin.db.gz: 988 -         parse_blocks() ] INFO    : Process-2   16 - arin.db.gz - committed 28066/20000/80132 inserts/blocks/total (147.0 seconds) 64.5% done, ignored 218/9137 dupes/total (154 inserts/s)
[arin.db.gz: 988 -         parse_blocks() ] INFO    : Process-4   18 - arin.db.gz - committed 28199/20000/80171 inserts/blocks/total (147.06 seconds) 64.5% done, ignored 221/9137 dupes/total (155 inserts/s)
J[arin.db.gz:1054 -                 main() ] INFO    : MainProcess 14 - arin.db.gz - BLOCKS PARSING DONE: 299 seconds (416 blocks/s) for 124320 blocks
[lacnic.db.gz:1060 -                 main() ] INFO    : MainProcess 14 - lacnic.db.gz - File ./downloads/lacnic.db.gz not found. Please download using download_dumps.sh
[ripe.db.inetnum.gz:1060 -                 main() ] INFO    : MainProcess 14 - ripe.db.inetnum.gz - File ./downloads/ripe.db.inetnum.gz not found. Please download using download_dumps.sh
[apnic.db.inet6num.gz:1060 -                 main() ] INFO    : MainProcess 14 - apnic.db.inet6num.gz - File ./downloads/apnic.db.inet6num.gz not found. Please download using download_dumps.sh
[ripe.db.inet6num.gz:1060 -                 main() ] INFO    : MainProcess 14 - ripe.db.inet6num.gz - File ./downloads/ripe.db.inet6num.gz not found. Please download using download_dumps.sh
[empty:1064 -                 main() ] INFO    : MainProcess 14 - empty - script finished: 298.87 seconds

$ ./bin/query 8.8.8.8
SELECT block.inetnum, block.netname, block.country, block.description, block.maintained_by, block.created, block.last_modified, block.source FROM block WHERE block.inetnum >> '8.8.8.8' ORDER BY block.inetnum DESC;
-[ RECORD 1 ]-+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
inetnum       | 8.0.0.0/8
netname       | IANA-NETBLOCK-8
country       | AU
description   | This network range is not allocated to APNIC. If your whois search has returned this message, then you have searched the APNIC whois database for an address that is allocated by another Regional Internet Registry (RIR). Please search the other RIRs at whois.arin.net or whois.ripe.net for more information about that range.
maintained_by | MAINT-APNIC-AP
created       |
last_modified | 2008-09-04 06:51:28
source        | apnic
-[ RECORD 2 ]-+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
inetnum       | 8.0.0.0/6
netname       | NON-RIPE-NCC-MANAGED-ADDRESS-BLOCK
country       | EU # Country is really world wide
description   | IPv4 address block not managed by the RIPE NCC
maintained_by | RIPE-NCC-HM-MNT
created       | 2019-01-07 10:49:33
last_modified | 2019-01-07 10:49:33
source        | ripe
-[ RECORD 3 ]-+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
inetnum       | 0.0.0.0/0
netname       | IANA-BLK
country       | EU # Country is really world wide
description   | The whole IPv4 address space
maintained_by | AFRINIC-HM-MNT
created       |
last_modified |
source        | afrinic
-[ RECORD 4 ]-+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
inetnum       | 0.0.0.0/0
netname       | IANA-BLK
country       | EU # Country field is actually all countries in the world and not just EU countries
description   | The whole IPv4 address space
maintained_by | RIPE-NCC-HM-MNT
created       | 2002-06-25 14:19:09
last_modified | 2018-11-23 10:30:34
source        | ripe
-[ RECORD 5 ]-+------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
inetnum       | 0.0.0.0/0
netname       | IANA-BLOCK
country       | AU
description   | General placeholder reference for all IPv4 addresses
maintained_by | MAINT-APNIC-AP
created       |
last_modified | 2008-09-04 06:51:49
source        | apnic
```

# RoadMap
TODO:

- [ ] increase efficiency
- [ ] Start charging for my hard work?

## version: 2.0.16

- 2.0.16  300 inserts/s: 1 commit/block, autoflush
- 2.0.15  215 inserts/s: 1 commit/insert, autoflush
- 2.0.14  added --reset_db and --commit_count 100
- 2.0.13  now getRow before insert. ALSO works much better when commit instead of flush: parallel process don't use same blocks anymore
- 2.0.12  added autoflush=True
- 2.0.11  parent table multicolumn primary keys: trying to Handle concurrent INSERT with SQLAlchemy: it works but... technique from rachbelaid.com is 2015 old and other errors arise (except IntegrityError bleed into Exception + RecursionError: maximum recursion depth exceeded)
- 2.0.10  better logging
- 2.0.9   multiple bugfixes
- 2.0.8   now increment shared counters
- 2.0.7   now storing strings and not bytes
- 2.0.6   now working again
- 2.0.5   WIP moving away from byte storage
- 2.0.4   WIP to get new database inserts working: inetnum works
- 2.0.3   [x] fix the bug where the whoisd build output is invisible - it fixed itself
- 2.0.2   download_dumps.sh does not re-download existing databases
- 2.0.1   complete rewrite of the create_db.py and database structure
- 2.0.0   initial fork and rename from network_info to whoisd

## :ribbon: Licence
[MIT](https://choosealicense.com/licenses/mit/)


## :beer: Buy me a beer
Like my work? This tool helped you? Want to sponsor more awesomeness like this?

<p align="center">
 <a href="https://www.paypal.com/donate/?hosted_button_id=CD7P7PK3WP8WU"><img src="/assets/paypal-Donate-QR-Code.png" /></a>
</p>

