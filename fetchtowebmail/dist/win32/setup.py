# setup.py fuer die Verwendung von py2exe (http://starship.python.net/crew/theller/py2exe/)
# mit fetchtowebmail 

import os

from distutils.core import setup
import py2exe

if (not os.path.exists("fetchtowebmail.py")):
	os.chdir("..") # setup.py ist normalerweise im Unterverzeichnis win32

setup(name="fetchtowebmail",
      version="0.3.2",
      description="Downloads mails from T-Online webmail",
      author="Jonas Wolz",
      author_email="jwolz@freenet.de",
      url="http://www.fetchtowebmail.de.vu/",
#      scripts=["fetchtowebmail.py"],
      console=["fetchtowebmail.py"],
      data_files=["README.en", "README", "FAQ", "COPYING", "ChangeLog", "fetchtowebmailrc.example.en", 
                   "win32/Install.txt", "win32/runandwait.bat", "win32/fetchtowebmailrc"],
)
