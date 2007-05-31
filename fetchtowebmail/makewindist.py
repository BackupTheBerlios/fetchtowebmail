# Erstellt die Windows-Distribution von fetchtowebmail

import sys, os, shutil, re, zipfile

# Directory we should copy the source from:
src_src = "//pc1/jonas/towebmail/repository/fetchtowebmail/dist"
# Destination dir (its content is DELETED before copying the source):
src_dst = os.environ["USERPROFILE"] + "/Eigene Dateien/fetchtowebmail-py2exe"

# Location of the setup.py inside the distribution directory:
setup_py = "win32/setup.py"

print "Copying source code..."
# Copy source:
try:
    shutil.rmtree(src_dst)
except:
    pass

shutil.copytree(src_src, src_dst)

os.chdir(src_dst)

# Get version ...
f = open(setup_py, "r")
match = re.search("[\s,]*version\s*=\s*[\"'](\d+\.[\w\.]+?)[\"'][\s,]*", f.read())
f.close()
if match:
   version = match.group(1)
   print "Version is:", version

print "Launching py2exe ..."
# Make exe
os.system(sys.executable + " " + setup_py + " py2exe -c -O1 -dpy2exe-dist --excludes=pycurl")
print "py2exe is done, press return to continue"
raw_input()

zipname = "fetchtowebmail-win32exe-" + version + ".zip"
print "Creating ", zipname, "..."
# Make zip
#os.chdir("py2exe-dist\\fetchtowebmail")
os.chdir("py2exe-dist")
zip = zipfile.ZipFile("..\\" + zipname, "w", zipfile.ZIP_DEFLATED)

def addtozip(zipfile, dir):
	if dir:
		files = os.listdir(dir)
	else:
		files = os.listdir(".")
	for f in files:
		file = os.path.join(dir, f)
		if os.path.isdir(file):
			addtozip(zipfile, file)
		else:
			print "Adding %s." % file
			zipfile.write(file)
addtozip(zip, "")
zip.close()
print "Copying zip file back ..."
shutil.copy("..\\" + zipname, os.path.join(os.path.dirname(src_src), zipname))
print "Done, press return to continue..."
raw_input()
