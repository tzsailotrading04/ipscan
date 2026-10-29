#!/bin/bash
set -e
CID=$(docker create traffmonetizer/cli_v2:latest)
docker cp "${CID}:/usr/local/bin/cli" /tmp/traff_cli
docker rm "${CID}"
ls -lh /tmp/traff_cli
strings /tmp/traff_cli | grep -E "(--token|--device-name|accept)" | head -n 20
