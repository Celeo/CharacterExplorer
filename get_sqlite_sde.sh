#!/bin/bash
echo "Getting file from fuzzwork"
wget https://www.fuzzwork.co.uk/dump/sqlite-latest.sqlite.bz2
echo "Decompressing"
bzip2 -d sqlite-latest.sqlite.bz2
mv sqlite-latest.sqlite sde.db
echo "Done"
