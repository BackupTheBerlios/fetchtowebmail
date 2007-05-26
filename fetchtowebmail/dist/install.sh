#!/bin/sh
# install.sh: Installs fetchtowebmail into /usr/local/bin or into a different directory
# Usage: install.sh [directory] 

# default directory:
DEFINSTDIR=/usr/local/bin

# The file to install:
SCRIPTNAME=fetchtowebmail

# Check if the user wants a different directory
if [ $1 ]; then
	INSTDIR="$1" ;
else
	INSTDIR="$DEFINSTDIR" ;
fi

if [ ! -f $SCRIPTNAME ]; then
	echo "Executing setup.sh to setup the right interpreter path..."
	./setup.sh || exit 2 ;
fi

echo "Installing $SCRIPTNAME to $INSTDIR ..."
install -m 0755 $SCRIPTNAME $INSTDIR/$SCRIPTNAME

echo 
echo "Installation done. Now open fetchtowebmailrc.example (comments in German)"
echo "or fetchtowebmailrc.example.en (comments in English) in your favourite"
echo "text editor, edit it to reflect the configuration you need and save it as"
echo ".fetchtowebmailrc into your home directory."
echo "After that the installation should be complete."

