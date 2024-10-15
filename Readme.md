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
2024-10-15 03:13:02,970 - create_db - INFO     - MainProcess 14 - afrinic.db.gz - File ./downloads/afrinic.db.gz not found. Please download using download_dumps.sh
2024-10-15 03:13:02,971 - create_db - INFO     - MainProcess 14 - apnic.db.inetnum.gz - File ./downloads/apnic.db.inetnum.gz not found. Please download using download_dumps.sh
2024-10-15 03:13:02,971 - create_db - INFO     - MainProcess 14 - arin.db.gz - parsing database file: ./downloads/arin.db.gz
2024-10-15 03:13:03,332 - create_db - DEBUG    - MainProcess 14 - arin.db.gz - parsed another 10000 blocks (10000 so far, ignored 0 blocks)
2024-10-15 03:13:03,421 - create_db - DEBUG    - MainProcess 14 - arin.db.gz - parsed another 10000 blocks (20000 so far, ignored 0 blocks)
2024-10-15 03:13:03,525 - create_db - DEBUG    - MainProcess 14 - arin.db.gz - parsed another 10000 blocks (30000 so far, ignored 0 blocks)
2024-10-15 03:13:03,618 - create_db - DEBUG    - MainProcess 14 - arin.db.gz - parsed another 10000 blocks (40000 so far, ignored 0 blocks)
2024-10-15 03:13:03,719 - create_db - DEBUG    - MainProcess 14 - arin.db.gz - parsed another 10000 blocks (50000 so far, ignored 0 blocks)
2024-10-15 03:13:03,818 - create_db - DEBUG    - MainProcess 14 - arin.db.gz - parsed another 10000 blocks (60000 so far, ignored 0 blocks)
2024-10-15 03:13:03,911 - create_db - DEBUG    - MainProcess 14 - arin.db.gz - parsed another 10000 blocks (70000 so far, ignored 0 blocks)
2024-10-15 03:13:04,048 - create_db - DEBUG    - MainProcess 14 - arin.db.gz - parsed another 10000 blocks (80000 so far, ignored 0 blocks)
2024-10-15 03:13:04,152 - create_db - DEBUG    - MainProcess 14 - arin.db.gz - parsed another 10000 blocks (90000 so far, ignored 0 blocks)
2024-10-15 03:13:04,248 - create_db - DEBUG    - MainProcess 14 - arin.db.gz - parsed another 10000 blocks (100000 so far, ignored 0 blocks)
2024-10-15 03:13:04,342 - create_db - DEBUG    - MainProcess 14 - arin.db.gz - parsed another 10000 blocks (110000 so far, ignored 0 blocks)
2024-10-15 03:13:04,449 - create_db - DEBUG    - MainProcess 14 - arin.db.gz - parsed another 10000 blocks (120000 so far, ignored 0 blocks)
2024-10-15 03:13:04,622 - create_db - INFO     - MainProcess 14 - arin.db.gz - Total 124320 blocks: Parsed 124320 blocks, ignored 0 blocks
2024-10-15 03:13:04,623 - create_db - INFO     - MainProcess 14 - arin.db.gz - file parsing finished: 1.65 seconds
2024-10-15 03:13:04,623 - create_db - INFO     - MainProcess 14 - arin.db.gz - parsing blocks
2024-10-15 03:13:04,648 - create_db - DEBUG    - MainProcess 14 - arin.db.gz - starting 4 processes
2024-10-15 03:13:04,858 - create_db - INFO     - MainProcess 14 - arin.db.gz - blocks load into workers finished: 0.24 seconds
2024-10-15 03:13:05,135 - create_db - DEBUG    - Process-3   17 - arin.db.gz - committed 1/2089/8116 blocks (0.47 seconds) 6.5% done, ignored 0 duplicates
2024-10-15 03:13:05,135 - create_db - DEBUG    - Process-4   18 - arin.db.gz - committed 1/1549/8116 blocks (0.47 seconds) 6.5% done, ignored 0 duplicates
2024-10-15 03:13:05,138 - create_db - DEBUG    - Process-2   16 - arin.db.gz - committed 1/2272/8119 blocks (0.48 seconds) 6.5% done, ignored 0 duplicates
2024-10-15 03:13:05,144 - create_db - DEBUG    - Process-1   15 - arin.db.gz - committed 1/2348/8132 blocks (0.49 seconds) 6.5% done, ignored 0 duplicates
2024-10-15 03:13:11,671 - create_db - DEBUG    - Process-4   18 - arin.db.gz - ignoring invalid changed date mike@elkhart.com20110613 (route 50.21.208.0/20 block=3223)
2024-10-15 03:13:15,420 - create_db - DEBUG    - Process-4   18 - arin.db.gz - ignoring invalid changed date 20113511 (route 66.211.112.0/20 block=4310)
2024-10-15 03:13:27,025 - create_db - DEBUG    - Process-1   15 - arin.db.gz - committed 10001/13000/45835 blocks (21.88 seconds) 36.9% done, ignored 326 duplicates
2024-10-15 03:13:27,055 - create_db - DEBUG    - Process-4   18 - arin.db.gz - committed 10001/12189/45876 blocks (21.92 seconds) 36.9% done, ignored 320 duplicates
2024-10-15 03:13:28,359 - create_db - DEBUG    - Process-2   16 - arin.db.gz - committed 10001/12922/48143 blocks (23.22 seconds) 38.7% done, ignored 325 duplicates
2024-10-15 03:13:34,817 - create_db - DEBUG    - Process-4   18 - arin.db.gz - ignoring invalid changed date 20113511 (route 173.241.64.0/20 block=13852)
2024-10-15 03:13:35,526 - create_db - DEBUG    - Process-4   18 - arin.db.gz - ignoring invalid changed date ispadmin@tdstelecom.com (route 184.61.135.0/24 block=14597)
2024-10-15 03:13:35,909 - create_db - DEBUG    - Process-3   17 - arin.db.gz - committed 10001/12801/62290 blocks (30.77 seconds) 50.1% done, ignored 356 duplicates
2024-10-15 03:13:51,191 - create_db - DEBUG    - Process-4   18 - arin.db.gz - committed 20001/24901/89043 blocks (24.13 seconds) 71.6% done, ignored 1676 duplicates
2024-10-15 03:13:51,756 - create_db - DEBUG    - Process-1   15 - arin.db.gz - committed 20001/25758/90240 blocks (24.73 seconds) 72.6% done, ignored 1705 duplicates
2024-10-15 03:14:02,205 - create_db - DEBUG    - Process-2   16 - arin.db.gz - committed 20001/28072/107901 blocks (33.85 seconds) 86.8% done, ignored 2900 duplicates
2024-10-15 03:14:02,212 - create_db - DEBUG    - Process-2   16 - arin.db.gz - committed 20001/28074/107915 blocks (0.01 seconds) 86.8% done, ignored 2901 duplicates
2024-10-15 03:14:03,042 - create_db - DEBUG    - Process-3   17 - arin.db.gz - ignoring invalid changed date 2011021700 (route 2604:CC00::/32 block=15597)
2024-10-15 03:14:07,812 - create_db - DEBUG    - Process-3   17 - arin.db.gz - ignoring invalid changed date noc@craigslist.org (route 2620:7e::/44 block=17526)
2024-10-15 03:14:08,451 - create_db - DEBUG    - Process-4   18 - arin.db.gz - Process-4 finished: 32579 blocks total
2024-10-15 03:14:08,451 - create_db - DEBUG    - Process-2   16 - arin.db.gz - Process-2 finished: 31548 blocks total
2024-10-15 03:14:08,452 - create_db - DEBUG    - Process-1   15 - arin.db.gz - Process-1 finished: 33173 blocks total
2024-10-15 03:14:08,467 - create_db - DEBUG    - Process-3   17 - arin.db.gz - Process-3 finished: 27020 blocks total
2024-10-15 03:14:08,476 - create_db - INFO     - MainProcess 14 - arin.db.gz - block parsing finished: 63.85 seconds
2024-10-15 03:14:08,476 - create_db - INFO     - MainProcess 14 - lacnic.db.gz - File ./downloads/lacnic.db.gz not found. Please download using download_dumps.sh
2024-10-15 03:14:08,476 - create_db - INFO     - MainProcess 14 - ripe.db.inetnum.gz - File ./downloads/ripe.db.inetnum.gz not found. Please download using download_dumps.sh
2024-10-15 03:14:08,476 - create_db - INFO     - MainProcess 14 - apnic.db.inet6num.gz - File ./downloads/apnic.db.inet6num.gz not found. Please download using download_dumps.sh
2024-10-15 03:14:08,476 - create_db - INFO     - MainProcess 14 - ripe.db.inet6num.gz - File ./downloads/ripe.db.inet6num.gz not found. Please download using download_dumps.sh
2024-10-15 03:14:08,476 - create_db - INFO     - MainProcess 14 - empty - script finished: 65.77 seconds

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

## version: 2.0.10

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

