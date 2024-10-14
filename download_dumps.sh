#!/bin/bash

DOWNLOAD_DIR="./downloads"
mkdir -p $DOWNLOAD_DIR/done

function download {
  dbzname=$(basename $1)
  if [ ! -s "$DOWNLOAD_DIR/$dbzname" -a ! -s "$DOWNLOAD_DIR/done/$dbzname" ]; then
    echo "Downloading $dbzname..."
    wget -O "$DOWNLOAD_DIR/$dbzname" "$1"
    chmod 644 "$DOWNLOAD_DIR/$dbzname"
  else
    echo "SKIP: $dbzname"
  fi
}

# APNIC (the Asia Pacific Network Information Centre)
# ARIN (North America)
# LACNIC (Latin America and the Caribbean)
# RIPE NCC (Europe)
# AFRINIC (Africa)

# download "https://ftp.apnic.net/apnic/whois/apnic.db.inetnum.gz"
# download "https://ftp.apnic.net/apnic/whois/apnic.db.inet6num.gz"
# download "https://ftp.apnic.net/apnic/whois/apnic.db.organisation.gz"
# download "https://ftp.apnic.net/apnic/whois/apnic.db.role.gz"

download "https://ftp.arin.net/pub/rr/arin.db.gz"

# download "https://ftp.lacnic.net/lacnic/dbase/lacnic.db.gz"

# download "https://ftp.ripe.net/ripe/dbase/ripe.db.gz"
# download "https://ftp.ripe.net/ripe/dbase/split/ripe.db.inetnum.gz"
# download "https://ftp.ripe.net/ripe/dbase/split/ripe.db.inet6num.gz"

download "https://ftp.afrinic.net/dbase/afrinic.db.gz"
