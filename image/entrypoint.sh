#!/bin/sh

set +e

/usr/bin/snapclient -l
/usr/bin/snapclient -h $SNAPCAST_HOST -p $SNAPCAST_PORT -s "$SNAPCAST_DEVICE"
