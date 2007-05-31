#! /bin/bash

#DISTDIR="$HOME/towebmail/dist"
DISTDIR=`dirname $0`/dist
# Files to delete before creating our archive:
RMFILES="fetchtowebmail"

# Extract the version from the source:
VERSION=$(awk "/version = [\"']([0-9]+\..+)[\"']/ { split(\$0, V, /[ \t\n\"']+/); print V[3] }" $DISTDIR/fetchtowebmail.py)
TARBALL="../fetchtowebmail-$VERSION.tar.gz"


cd $DISTDIR

echo Cleaning $DISTDIR ...
rm -f $RMFILES

echo Creating $TARBALL from $DISTDIR ...
# Make a tar archive
tar -cvzf $TARBALL *

