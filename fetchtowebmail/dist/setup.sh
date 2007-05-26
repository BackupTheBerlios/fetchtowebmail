#!/bin/sh
# setup.sh: �ndert die erste Zeile von fetchtowebmail.py, damit sie auf den
#    gew�nschten Interpreter verweist, gibt die ver�nderte Datei als 
#    fetchtowebmail (ohne .py) aus 
# Aufruf: setup.sh [Interpreter] 
# Wenn Interpreter weggelassen wird, wird "python" daf�r eingesetzt

# Der Name des Befehls, um Python zu starten
if [ $1 ]; then
	PYTHON="$1" ;
else
	PYTHON=python ;
fi

INPUTNAME=fetchtowebmail.py
OUTPUTNAME=fetchtowebmail

REALPYTHON=$(which $PYTHON)
if [ -z $REALPYTHON ]; then
	echo "No python executable found!" >&2
	exit 1 ;
fi

# Die erste Zeile durch eine f�r dieses System passende ersetzen
sed -e"1c\\
#!$REALPYTHON" $INPUTNAME > $OUTPUTNAME

# Ergebnis ausf�hrbar machen
chmod 0755 $OUTPUTNAME

