#
# This script runs fetchtowebmail and then shows a "Press any key when ready" prompt
# after it exited (as Windows would close the console window by default)
#

# This will fail if not on Windows...
import msvcrt

import sys, os

# The name of the script to execute
script = "fetchtowebmail.py"
# Script with path (to pass it to execfile)
execscript = ""

# Try to find it (in the current directory, it's parent directory,
#  the directory where this script is located and in it's parent directory)
for dir in [".", os.path.dirname(sys.argv[0])]:
	for dir2 in [".", ".."]:
		testname = os.path.join(dir, dir2, script)
		if (os.path.isfile(testname)):
			execscript=testname
			break
	if execscript: break

# Run the script ...
os.system('"%s" "%s"' % (sys.executable, execscript))

print "\nPress any key to continue ...",
msvcrt.readch()

