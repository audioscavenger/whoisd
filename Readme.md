# Network Info Parser

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
2024-10-15 19:44:37,509 - create_db - INFO     - MainProcess 13 - afrinic.db.gz - File ./downloads/afrinic.db.gz not found. Please download using download_dumps.sh
2024-10-15 19:44:37,510 - create_db - INFO     - MainProcess 13 - apnic.db.inetnum.gz - File ./downloads/apnic.db.inetnum.gz not found. Please download using download_dumps.sh
2024-10-15 19:44:37,510 - create_db - INFO     - MainProcess 13 - arin.db.gz - loading database file: ./downloads/arin.db.gz
2024-10-15 19:44:37,870 - create_db - DEBUG    - MainProcess 13 - arin.db.gz - read_blocks: another 10000 blocks so far, Kept (10000 blocks, Ignored 0 blocks,
2024-10-15 19:44:37,961 - create_db - DEBUG    - MainProcess 13 - arin.db.gz - read_blocks: another 10000 blocks so far, Kept (20000 blocks, Ignored 0 blocks,
2024-10-15 19:44:38,065 - create_db - DEBUG    - MainProcess 13 - arin.db.gz - read_blocks: another 10000 blocks so far, Kept (30000 blocks, Ignored 0 blocks,
2024-10-15 19:44:38,158 - create_db - DEBUG    - MainProcess 13 - arin.db.gz - read_blocks: another 10000 blocks so far, Kept (40000 blocks, Ignored 0 blocks,
2024-10-15 19:44:38,259 - create_db - DEBUG    - MainProcess 13 - arin.db.gz - read_blocks: another 10000 blocks so far, Kept (50000 blocks, Ignored 0 blocks,
2024-10-15 19:44:38,357 - create_db - DEBUG    - MainProcess 13 - arin.db.gz - read_blocks: another 10000 blocks so far, Kept (60000 blocks, Ignored 0 blocks,
2024-10-15 19:44:38,449 - create_db - DEBUG    - MainProcess 13 - arin.db.gz - read_blocks: another 10000 blocks so far, Kept (70000 blocks, Ignored 0 blocks,
2024-10-15 19:44:38,548 - create_db - DEBUG    - MainProcess 13 - arin.db.gz - read_blocks: another 10000 blocks so far, Kept (80000 blocks, Ignored 0 blocks,
2024-10-15 19:44:38,652 - create_db - DEBUG    - MainProcess 13 - arin.db.gz - read_blocks: another 10000 blocks so far, Kept (90000 blocks, Ignored 0 blocks,
2024-10-15 19:44:38,747 - create_db - DEBUG    - MainProcess 13 - arin.db.gz - read_blocks: another 10000 blocks so far, Kept (100000 blocks, Ignored 0 blocks,
2024-10-15 19:44:38,840 - create_db - DEBUG    - MainProcess 13 - arin.db.gz - read_blocks: another 10000 blocks so far, Kept (110000 blocks, Ignored 0 blocks,
2024-10-15 19:44:38,947 - create_db - DEBUG    - MainProcess 13 - arin.db.gz - read_blocks: another 10000 blocks so far, Kept (120000 blocks, Ignored 0 blocks,
2024-10-15 19:44:39,120 - create_db - INFO     - MainProcess 13 - arin.db.gz - read_blocks: Kept 124320 blocks + Ignored 0 blocks = Total 124320 blocks
2024-10-15 19:44:39,120 - create_db - INFO     - MainProcess 13 - arin.db.gz - file loading finished: 1.61 seconds (77217 blocks/s)
2024-10-15 19:44:39,144 - create_db - INFO     - MainProcess 13 - arin.db.gz - BLOCKS PARSING START: starting 4 processes for 124320 blocks (~31080 per worker)
2024-10-15 19:44:39,347 - create_db - INFO     - MainProcess 13 - arin.db.gz - blocks load into workers finished: 0.23 seconds
2024-10-15 19:44:45,895 - create_db - DEBUG    - Process-3   16 - arin.db.gz - ignoring invalid changed date mike@elkhart.com20110613 (route 50.21.208.0/20 block=5092)
2024-10-15 19:44:49,451 - create_db - DEBUG    - Process-4   17 - arin.db.gz - ignoring invalid changed date 20113511 (route 66.211.112.0/20 block=6350)
2024-10-15 19:44:54,729 - create_db - DEBUG    - Process-3   16 - arin.db.gz - committed 7385/10000/36113 blocks (15.57 seconds) 29.0% done, ignored 271/1038 duplicates/total (474 inserts/s)
2024-10-15 19:44:56,029 - create_db - DEBUG    - Process-1   14 - arin.db.gz - committed 7572/10000/38713 blocks (16.87 seconds) 31.1% done, ignored 269/1057 duplicates/total (449 inserts/s)
2024-10-15 19:44:56,992 - create_db - DEBUG    - Process-2   15 - arin.db.gz - committed 7922/10000/40450 blocks (17.83 seconds) 32.5% done, ignored 280/1092 duplicates/total (444 inserts/s)
2024-10-15 19:44:57,678 - create_db - DEBUG    - Process-4   17 - arin.db.gz - committed 7783/10000/41554 blocks (18.51 seconds) 33.4% done, ignored 264/1132 duplicates/total (420 inserts/s)
2024-10-15 19:45:08,240 - create_db - DEBUG    - Process-3   16 - arin.db.gz - ignoring invalid changed date 20113511 (route 173.241.64.0/20 block=15924)
2024-10-15 19:45:08,999 - create_db - DEBUG    - Process-1   14 - arin.db.gz - ignoring invalid changed date ispadmin@tdstelecom.com (route 184.61.135.0/24 block=16958)
2024-10-15 19:45:17,356 - create_db - DEBUG    - Process-1   14 - arin.db.gz - committed 16387/20000/76817 blocks (21.33 seconds) 61.8% done, ignored 1454/5821 duplicates/total (429 inserts/s)
2024-10-15 19:45:18,665 - create_db - DEBUG    - Process-3   16 - arin.db.gz - committed 16182/20000/78778 blocks (23.94 seconds) 63.4% done, ignored 1474/5870 duplicates/total (410 inserts/s)
2024-10-15 19:45:19,969 - create_db - DEBUG    - Process-4   17 - arin.db.gz - committed 16592/20000/81003 blocks (22.29 seconds) 65.2% done, ignored 1455/5934 duplicates/total (407 inserts/s)
2024-10-15 19:45:19,989 - create_db - DEBUG    - Process-2   15 - arin.db.gz - committed 16684/20000/81047 blocks (23.0 seconds) 65.2% done, ignored 1518/5938 duplicates/total (409 inserts/s)
2024-10-15 19:45:40,425 - create_db - DEBUG    - Process-1   14 - arin.db.gz - ignoring invalid changed date 2011021700 (route 2604:CC00::/32 block=28461)
2024-10-15 19:45:41,889 - create_db - DEBUG    - Process-3   16 - arin.db.gz - committed 24753/30000/115993 blocks (23.22 seconds) 93.3% done, ignored 2903/11677 duplicates/total (395 inserts/s)
2024-10-15 19:45:44,889 - create_db - DEBUG    - Process-2   15 - arin.db.gz - ignoring invalid changed date noc@craigslist.org (route 2620:7e::/44 block=29733)
2024-10-15 19:45:45,110 - create_db - DEBUG    - Process-4   17 - arin.db.gz - committed 24845/30000/121402 blocks (25.14 seconds) 97.7% done, ignored 3202/12886 duplicates/total (377 inserts/s)
2024-10-15 19:45:45,195 - create_db - DEBUG    - Process-1   14 - arin.db.gz - committed 24643/30000/121631 blocks (27.84 seconds) 97.8% done, ignored 3198/12890 duplicates/total (373 inserts/s)
2024-10-15 19:45:45,214 - create_db - DEBUG    - Process-2   15 - arin.db.gz - committed 24911/30000/121700 blocks (25.22 seconds) 97.9% done, ignored 3291/12891 duplicates/total (377 inserts/s)
2024-10-15 19:45:45,398 - create_db - DEBUG    - Process-3   16 - arin.db.gz - Process-3 finished: 32345 blocks total (66 seconds) (488 blocks/s)
2024-10-15 19:45:45,398 - create_db - DEBUG    - Process-1   14 - arin.db.gz - Process-1 finished: 30663 blocks total (66 seconds) (463 blocks/s)
2024-10-15 19:45:45,399 - create_db - DEBUG    - Process-4   17 - arin.db.gz - Process-4 finished: 30597 blocks total (66 seconds) (462 blocks/s)
2024-10-15 19:45:45,411 - create_db - DEBUG    - Process-2   15 - arin.db.gz - Process-2 finished: 30715 blocks total (66 seconds) (464 blocks/s)
2024-10-15 19:45:45,421 - create_db - INFO     - MainProcess 13 - arin.db.gz - BLOCKS PARSING DONE: 68 seconds (1831 blocks/s) for 124320 blocks
2024-10-15 19:45:45,421 - create_db - INFO     - MainProcess 13 - lacnic.db.gz - File ./downloads/lacnic.db.gz not found. Please download using download_dumps.sh
2024-10-15 19:45:45,421 - create_db - INFO     - MainProcess 13 - ripe.db.inetnum.gz - File ./downloads/ripe.db.inetnum.gz not found. Please download using download_dumps.sh
2024-10-15 19:45:45,421 - create_db - INFO     - MainProcess 13 - apnic.db.inet6num.gz - File ./downloads/apnic.db.inet6num.gz not found. Please download using download_dumps.sh
2024-10-15 19:45:45,421 - create_db - INFO     - MainProcess 13 - ripe.db.inet6num.gz - File ./downloads/ripe.db.inet6num.gz not found. Please download using download_dumps.sh
2024-10-15 19:45:45,421 - create_db - INFO     - MainProcess 13 - empty - script finished: 68.16 seconds

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

- [ ] test REBUILD with the new name
- [ ] replace all binstubs commands with demonized compose
- [ ] Start charging for my hard work?

## version: 2.0.11

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

