#!/bin/sh

psql -e -q -x -c "SELECT cidr.inetnum, cidr.netname, cidr.country, cidr.description, cidr.mntby, cidr.created, cidr.last_modified, cidr.source FROM cidr WHERE cidr.inetnum >> '$1' ORDER BY cidr.inetnum DESC;" whoisd
