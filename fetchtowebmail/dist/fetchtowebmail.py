#! /usr/bin/python
# -*- coding: iso-8859-15 -*-
#
# fetchtowebmail.py: A python script that fetches mails from T-Online's webmail
#                    interface (at https://webmail.t-online.de/) and forwards them
#                    into your mailbox
#
#  Copyright (c) 2003-2007 Jonas Wolz <jwolz@freenet.de>
#
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#


import sys, sgmllib, string, os, re, time, cPickle, getopt, ConfigParser
import urllib, urlparse, rfc822, socket, smtplib

useunixstyle = (os.name == "posix") # if this is true, use unix-specific stuff

#Default settings:
#  Retrieval settings:
website = "https://webmail.t-online.de/" # You usually don't want to change this
username = ""
password = ""

# Delete mails after fetching them (dangerous)
deleteafterfetching = 0

# Fetch only new mails (whose id is not in mailidsfile)
fetchonlynewmails = 0
# for mailidsfile, pathes are relative to the directory where the script is located
if useunixstyle: 
	mailidsfile = "~/.fetchtowebmailids" # On unices, put it in the home directory
else:
	mailidsfile = "fetchtowebmailids" # else use the dir where the script is installed

#  Delivery settings:
if os.environ.has_key("USER"):
	forwardaddress = os.environ["USER"] + "@localhost" # as a default forward it to the user currently logged in
else:
	forwardaddress = "" # needs to be configured
usesmtp = 1
smtpserver = "localhost"
smtpuser = ""
smtppass = ""
#   MDA: use %f as a placeholder for the "FROM" Address, %t for the forward (to) address
mda = "/usr/sbin/sendmail -f %f -bm %t"

# Header line to add:
addheaderline = ""
# text to prepend to subject
prependtosubject = ""
# If pycurl should be used
# 0: use urllib2/cookielib (Python >= 2.4 required)
# 1: use pycurl
# 2: use pycurl if present, else fall back to urllib2
usepycurl = 2

# (Extra) folders to poll. "INBOX" is added automatically if not present
pollfolders = []
#-- end of user settings

# Enables debug mode if set to 1:
# This saves all html pages retrieved in debug_savedir and the maildirs for analysis in ourtempdir
#  which is a SECURITY RISK (it's only intended for development)
debug=0
ourtempdir = "/tmp/fetchtowebmail/"

class LoginFormParser(sgmllib.SGMLParser):

	def __init__(self):
		sgmllib.SGMLParser.__init__(self)

		self.inputs = []
		self.forminfo = {}
		self.postdata = []
	#	imglist = []
		self.user = "keiner"
		self.password = "geheim"
	
	def do_form(self, attributes):
		# Load the attributes into a dictionary
		for att in attributes:
			self.forminfo[att[0]] = att[1]

	def do_input(self, attributes):
		# Load attributes into a dictionary
		attrdict = {}
		for att in attributes:
			attrdict[att[0]] = att[1]
		# ... and append them to the list of input forms
		self.inputs.append(attrdict)

		# Fill postdata to create a dictionary containing the data ready
		#  for POSTing to login
		#  For this to work 'user' and 'password' of course have to be specified before
		#  calling feed()
		#  Currently this function assumes that there is only one text input (for the username)
		#  and only one password input (for the password) in the form.

		type = attrdict["type"].lower()
		if (type == "password"):
			#self.postdata[attrdict["name"]] = self.password
			self.postdata.append((attrdict["name"], self.password.decode("latin-1").encode("utf-8")))
		elif (type == "text"):
			# Assume the text input is for the username
			#self.postdata[attrdict["name"]] = self.user
			self.postdata.append((attrdict["name"], self.user))
		elif (type == "hidden"):
			#self.postdata[attrdict["name"]] = attrdict["value"]
			self.postdata.append((attrdict["name"], attrdict["value"]))
		elif (type == "image"): # submit "button"
#			self.postdata[attrdict["name"] + ".x"] = "5"
#			self.postdata[attrdict["name"] + ".y"] = "5"
			self.postdata.append((attrdict["name"] + ".x", "5"))
			self.postdata.append((attrdict["name"] + ".y", "6"))
			if (attrdict.has_key("value")):
#				self.postdata[attrdict["name"]] = attrdict["value"]
				self.postdata.append((attrdict["name"], attrdict["value"]))

		# In the current form there aren't other input types
		
#	def do_img(self, attributes):
#		for att in attributes:
#			if (att[0] == 'src'):
#				self.imglist.append(att[1])

	def clear(self):
		# Clear input:
		self.inputs = []
		self.forminfo = {}
		self.postdata = []
#		self.imglist = []
		self.reset()
# --- end of class LoginFormParser

class MessageListParser(sgmllib.SGMLParser):
	# Handle HTML entitys correctly (we need to handle text normally visible to the user here):
	from htmlentitydefs import entitydefs
	logoutname = "Logout"	
	nextname = "N&auml;chste Seite"
	mainformname = "fmform"
	

	def __init__(self):
		sgmllib.SGMLParser.__init__(self)
		self.logoutpage = ""
		self.nextpage = ""

		# idlist contains only the values
		self.idlist = []
		self.checkboxname = ""
		self.mailids = []
		self.mailidsfetched = [] # The list of successfully fetched mailIDs
		self.foldername = "<default>"
	
		# Initialize variables:
		self.hiddenpostdata = {}
		self.mainformattr = {}
		self.inmainform = 0
		self.mailcount = 0
	
		self.nextpage = ""
		self.lastlink = ""
		self.linktext = ""
		self.url = ""

	# mailer: MyMailer instance to use
	def fetchidlistmails(self, mailer):
		# code ported from T-Online's JavaScript 
		targeturl = urlparse.urljoin(self.url, 'index.php?ctl=save_message')
		actualpostdata = dict(self.hiddenpostdata)
		actualpostdata['p[action]'] = "save"
		for id in self.idlist:
			do_print("Fetching mail " + id, 0)
			actualpostdata[self.checkboxname] = id
			page = geturl(targeturl, urllib.urlencode(actualpostdata))
			if (not mailer.sendmail(page, self.foldername)):
				return 0					
			page.close()
			self.mailidsfetched.append(id)
		return 1
		
	def deleteidlistmails(self):
		def hiddenmap(x):
			if (x == 'p[action]'):
				return (x, "delete")
			else:
				return (x, self.hiddenpostdata[x])
	
		# code ported from T-Online's JavaScript 
		targeturl = urlparse.urljoin(self.url, 'index.php?ctl=message_list')
		actualpostdata = map(hiddenmap, self.hiddenpostdata) # Convert to list of tuples
		msglist = ""
		for id in self.mailidsfetched:
			msglist += id + " "
			actualpostdata.append((self.checkboxname, id))
		do_print("Deleting the following messages: " + msglist, 0)
		page = geturl(targeturl, urllib.urlencode(actualpostdata))
		page.read()
		page.close()
		#actualpostdata = dict(self.hiddenpostdata)
		#actualpostdata['p[action]'] = "delete"
		#for id in self.idlist:
		#	do_print("Deleting mail " + id, 0)
		#	actualpostdata[self.checkboxname] = id
		#	page = geturl(targeturl, urllib.urlencode(actualpostdata))
		#	page.read()				
		#	page.close()
		return 1

			
	def start_form(self, attributes):
		#Load attributes in a dictionary:
		attdict = {}
		for att in attributes:
			attdict[att[0]] = att[1]
		# There are two forms, but only one is interesting
		if (attdict["name"] == self.mainformname):
			self.mainformattr = attdict
			self.inmainform = 1
	def end_form(self):
		if self.inmainform: self.inmainform = 0
	def do_input(self, attributes):
		global fetchonlynewmails
		
		# Only the stuff in the main ("Mailoverview") form is interesting:
		if self.inmainform:
			#Load attributes in a dictionary:
			attdict = {}
			for att in attributes:
				attdict[att[0]] = att[1]
			
			#print attdict
			t = attdict["type"].lower()
			if (t == "checkbox"):
				# We assume here all checkboxes are there to select mails
				
				if (not attdict.has_key("value")): # "Alle auswählen" check box
					return
					
				id = attdict["value"]
				if fetchonlynewmails:
					for fetchedid in self.mailids:
						if (id == fetchedid): # If the ID is in the list ...
							self.mailidsfetched.append(id) # Append to the list of fetched mailids
							return # .. exit function (don't download)
				# end if fetchonlynewmails
				
				# Add id to the list of mails to fetch:
				#self.postdata[attdict["name"]] = id
				#self.postdata.append((attdict["name"], id))
				
				if (self.checkboxname != ""):
					if (attdict["name"] != self.checkboxname):
						do_print("Warning: checkboxnames differ in messagelist!")
				else:
					self.checkboxname = attdict["name"]
				
				self.idlist.append(id)
				self.mailcount += 1
			elif (t == "hidden"):
				#self.hiddenpostdata.append((attdict["name"], attdict["value"]))
				self.hiddenpostdata[attdict["name"]] = attdict["value"]
			else:
				do_print("Warning: Unknown input:" + str(attdict));
	
	# Handle Links:
	def start_a(self, attributes):
		self.lastlink = getattrib("href", attributes)
		self.linktext = ""
	def end_a(self):
		if (self.linktext.find(self.logoutname) > -1): # It's the "logout" link!
			lomatch = re.search("javascript:CMP_goto\\('(.*?)'\\)", self.lastlink)
			if (lomatch == None):
				do_print("No Logout link found!", 3)
			else:
				self.logoutpage = urlparse.urljoin(self.url, lomatch.group(1))
		elif (self.linktext.find(self.nextname) > -1): # next page link
			self.nextpage =  urlparse.urljoin(self.url, self.lastlink)
		#else:
		#	print self.linktext, self.lastlink	
		self.linktext = ""
		self.lastlink = ""


	# Handle "normal" text
	def handle_data(self, data):
		if self.lastlink:
			# we're inside a link
			self.linktext += data

	def start_img(self, attributes):
		if self.lastlink:
			# we're inside a link
			self.linktext += getattrib("alt", attributes)

	
# --- end of class MainPageParser

class JSRedirectionParser:

	redirectre = re.compile('top.location.href="(.*?)";')

	def __init__(self):
		self.redirecttarget = ""
	
	def feed(self, text):
		match = self.redirectre.search(text)
		if (match == None):
			do_print("No JavaScript redirection found on page.")
			self.redirecttarget = ""
			return 0

		self.redirecttarget = match.group(1)
		return 1

# end class JSRedirectionParser
		

class Logout1Parser(sgmllib.SGMLParser):
	def __init__(self):
		sgmllib.SGMLParser.__init__(self)
		self.logoutpage = ""
			
	# Handle Links:
	def start_a(self, attributes):
		href = getattrib("href", attributes)
		if (href.find("result=logout") > -1): # Assume it's the logout link if it contains "logout"
			self.logoutpage = href
			
# end class Logout1Parser


class MyMailer:
	
	def __init__(self):
		self.receivedline = ""
		self.tz = "+0"

		
	# Connects to the SMTP server (if usesmtp=1) and sets the URL for the "Received" line
	def connect(self, serverfromurl):
		global usesmtp, smtpserver, smtpuser, smtppass, version

		serverfromtupel = urlparse.urlparse(serverfromurl)
		
		# Our own "Received" line (without time information) ;-)
		self.receivedline = "Received: from " + serverfromtupel[1] + "\n" + \
		       "        by " + socket.gethostname() + " with " + serverfromtupel[0].upper() + " (fetchtowebmail " + version + ")\n" + \
	 	       "        for " + forwardaddress + "; "
		# determine the correct timezone value
		if (time.localtime()[8] == 1):
			self.tz = " %+05d\n"%(-time.altzone/36)
		else:
			self.tz = " %+05d\n"%(-time.timezone/36) # timezone gives the offset in seconds _west_ of UTC,
							    # while here the offset in hours _east_ of UTC is expected (thus -timezone)		
		
		if usesmtp:
			self.smtp = smtplib.SMTP(smtpserver)
			if (smtpuser and smtppass): # Authentication is requested
				if (sys.hexversion >= 0x02020000): # SMTP Auth is only supported in the smtplib of Python version >=2.2
					self.smtp.login(smtpuser, smtppass) # try to login ...
				else: # warn the user
					do_print("WARNING: To use SMTP authentication, you need Python 2.2 or higher.\n Trying to send mails without authentication...", 3)

	# end def connect
	
	# Sends a mail:
	# fin: file object to read the mail from
	# folder: folder the mail is from
	def sendmail(self, fin, folder):
		global forwardaddress, usesmtp, mda
	
		def getsendtext(mail):
			if addheaderline:
				res = addheaderline + "\n"
			else:
				res = ''
			if folder:
				res += "X-fetchtowebmail-FromFolder: %s\n" % folder
				
			res += self.receivedline + time.strftime("%a, %d %b %Y %H:%M:%S", time.localtime()) + self.tz
		
			if prependtosubject: # Modify subject:
				mail["Subject"] = prependtosubject + " " + mail["Subject"]
			#	res += ''.join(mail.headers) + "\n"
			#	mail.rewindbody()
			#else:
			#	mail.fp.seek(0)
			#	mail.fp.readline() # The first line is not needed (contains the separator)
			#res += mail.fp.read()
			res += ''.join(mail.headers) + "\n" + mail.fp.read()
			return res
		# end getsendtext
	
		msg = rfc822.Message(fin)
		 
		if usesmtp: # Send mail using smtp; if something goes wrong, it will raise an exception
			try:
				fromaddr = msg.getaddr("From")[1]
                                # fix if "From" has not been specified properly
                                if (fromaddr == ""):
                                        fromaddr = "no-user@no-domain.org"
				self.smtp.sendmail(fromaddr, forwardaddress, getsendtext(msg))
			except: # Something went wrong ...
				do_print("Error delivering a mail: %s: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])), 4)
				return 0
		else: # Send mail by piping it into a MDA
			try:
				pipe = os.popen(mda.replace("%f", mail.getaddr("From")[1]), "w")
				pipe.write(getsendtext(mail))
			except:
				do_print("An exception occured writing to the pipe: %s: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])), 4)
				return 0
			# end try
			exitstatus = pipe.close()
			if (exitstatus != None):
				do_print('Error delivering a mail: MDA returned %d (From: "%s", Subject: "%s")' % (os.WEXITSTATUS(exitstatus), mail.getaddr("From")[1], mail.getheader("Subject")), 4)
				return 0
		# end if usesmtp
		return 1
	# end def sendmails

	def quit(self):
		if usesmtp:
			self.smtp.quit()

#end class Mailer

# Returns a tuple (file, url)
def geturl2(url, postdata=None):
	if (usepycurl):
		globalcurl.setopt(pycurl.URL, url)
		if (postdata == None):
			globalcurl.setopt(pycurl.HTTPGET, 1)
		else:
			globalcurl.setopt(pycurl.POSTFIELDS, postdata)
			globalcurl.setopt(pycurl.POST, 1)

		pagebuf = cStringIO.StringIO()
		globalcurl.setopt(pycurl.WRITEFUNCTION, pagebuf.write)
		globalcurl.perform()
		pagebuf.seek(0)

		return (pagebuf, globalcurl.getinfo(pycurl.EFFECTIVE_URL))
	else:
		rv = urllib2.urlopen(url, postdata)
		return (rv, rv.geturl())

def geturl(url, postdata=None):
	return geturl2(url, postdata)[0]
	
# Print a text (maybe honour a -v flag here later ?)
# Priority values:
#   0: debug
#   1: information (default)
#   3: warning (goes to stderr)
#   4: error
def do_print(text, priority=1):
	if (priority < verbosity): return
	
	if (priority >= 3): 
		print >> sys.stderr, text
	else:
		print text

# If in debug mode (debug != 0), this function saves text into debug_savedir/name for further inspection
def saveifdebug(text, name):
	global debug, ourtempdir
	if debug:
		f = open(os.path.join(ourtempdir, name), "w")
		f.write(text)
		f.close()
	return text

# Get an attribute from the list of tuples supplied by SGMLparser in start_TAG or do_TAG 
def getattrib(name, attributes):
	for att in attributes:
		if (att[0] == name):
			return att[1]
	else:
		return ""
# -- end def getattrib

def printusage():
 print """Usage: fetchtowebmail [Options]

Options:
  -V, --version           print the version and exit
  -h, --help              print this message and exit
  -c, --configfile=<file> specifies the configuration file to use
  -s, --silent            print only error messages
  -d, --debugmsg          also print debug messages (this is NOT debug mode)
      --nopermissioncheck don't check if the configuration file has secure 
                          permissions (i.e. that only the owner can read it)

fetchtowebmail returns a zero exit code if fetching emails was successful
or if there were no (new) emails to fetch, non-zero if an error occured. """
#-- end def printusage()

def processcmdlineopts():
	global verbosity, configfile, permissioncheck

	rec_opts     = "hVc:sd"
	rec_longopts = ["help", "version", "configfile=", "silent", "debugmsg", "nopermissioncheck"]
	try:
		options = getopt.getopt(sys.argv[1:], rec_opts, rec_longopts)
	except getopt.GetoptError, err:
		do_print("fetchtowebmail: " + err.msg, 4)
		printusage()
		sys.exit(1)
	if (len(options[1]) > 0): # Some stuff was not recognized, so we print the usage and exit...
		do_print('fetchtowebmail: Unrecognized parameter "%s".' % options[1][0], 4)
		printusage()
		sys.exit(1)
	for opt in options[0]:
		o = opt[0] # Save the actual option in a short variable (since we don't have a switch/case statement in python :-( )
		if (o == "-h" or o =="--help"):
			printusage() #Print usage and exit
			sys.exit(0)
		elif (o == "-V" or o == "--version"):
			print "fetchtowebmail " + version #Print version info and exit
			sys.exit(0)
		elif (o == "-s" or o == "--silent"):
			verbosity = 4 # Print only error messages
		elif (o == "-d" or o == "--debugmsg"):
			verbosity = 0 # Print everything
		elif (o == "-c" or o == "--configfile"):
			configfile = opt[1] # Set a different configuration file
		elif (o == "--nopermissioncheck"):
			permissioncheck = 0
	# -- end for opt ...
# -- end def processcmdlineopts

def readconfigfile(file):
	global website, username, password, deleteafterfetching, fetchonlynewmails, mailidsfile, usepycurl, pollfolders
	global forwardaddress, usesmtp, smtpserver, smtpuser, smtppass, mda, addheaderline, prependtosubject
	
	cparser = ConfigParser.ConfigParser()
	
	# Read an option; return the default value if the value can't be found
	def readopt(name, defval, section, isint=0, parser=cparser):
		try:
			if not isint: # A string...
				retval = parser.get(section, name).strip()
				# If there is a trailing and a leading quotation mark, they are stripped:
				if (len(retval) == 0): return ""
				if (retval[0] == '"'):
					if (retval[len(retval) - 1] == '"'):
						if (len(retval) > 2): 
							retval = retval[1:len(retval)-1] #Strip the first and the last char
						else:
							retval = "" # Return a empty string
				elif (retval[0] == "'"): # Same for "'"
					if (retval[len(retval) - 1] == "'"):
						if (len(retval) > 2): 
							retval = retval[1:len(retval)-1] #Strip the first and the last char
						else:
							retval = "" # Return a empty string
				# -- end if retval ...
				return retval
			else: # An integer
				return parser.getint(section, name)
		except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
			return defval
	#-- end def readopt
	
	try:
		cparser.readfp(open(file, "r"))
	except IOError, err:
		do_print("WARNING: configuration file '%s' cannot be opened for reading: %s" % (file, err.strerror), 4)
	else:
		sect = "retrieval"
		username = readopt("username", username, sect)
		password = readopt("password", password, sect)
		website = readopt("website", website, sect)
		deleteafterfetching = readopt("deleteafterfetching", deleteafterfetching, sect, 1)
		fetchonlynewmails = readopt("fetchonlynewmails", fetchonlynewmails, sect, 1)
		mailidsfile = readopt("mailidsfile", mailidsfile, sect)
		usepycurl = readopt("usepycurl", usepycurl, sect, 1)
		s_pollfolders = readopt("pollfolders", "", sect)
		pollfolders = s_pollfolders.split()
		
		sect = "forwarding"
		forwardaddress = readopt("forwardaddress", forwardaddress, sect)
		usesmtp = readopt("usesmtp", usesmtp, sect, 1)
		smtpserver = readopt("smtpserver", smtpserver, sect)
		smtpuser = readopt("smtpuser", smtpuser, sect)
		smtppass = readopt("smtppass", smtppass, sect)
		mda = readopt("mda", mda, sect)

		addheaderline = readopt("addheaderline", addheaderline, sect)
		prependtosubject = readopt("prependtosubject", prependtosubject, sect)
		
		# Expand the home directory in paths:
		mailidsfile = os.path.expanduser(mailidsfile)
		if not os.path.isabs(mailidsfile):
			# If it's a relative path, add the directory where the script is located to make it absolute
			mailidsfile = os.path.join(os.path.dirname(sys.argv[0]), mailidsfile)

		# Set up the mda variable: (put the from address in and expand the path)
		mda = os.path.expanduser(mda).replace("%t", forwardaddress)
		
		if (useunixstyle and permissioncheck): # Test for secure permissions 
			if (os.stat(file)[0] & 0044): # If other users than the owner also have read access, warn the user
				do_print('WARNING: The permissions of the configuration file %s\n'
				         '         allow other users to read its contents.\n'
				         '         Because it usually contains passwords this is very likely a BAD IDEA.\n'
					 '         (Use a command like "chmod 0600 %s" to fix the permissions)' % (file, file), 3)
		# end if useunixstyle
# end def readconfigfile

# --------------------------------------------------------------------------------------------------------------
# Constants:

# The script's version:
#   Don't forget to update win32/setup.py if you change this!
version = "0.3.4"

# The version number of the mailids
mailidsver = 2

# -- end of constants

# Initialize global variables:
mailids = {} # dictionary "folder name" -> idlist
mailidspresent = {}

# Configuration file name:
if (useunixstyle):
	configfile = os.path.expanduser("~/.fetchtowebmailrc") #On unices, search in the home directory
else:
	configfile = os.path.join(os.path.dirname(sys.argv[0]), "fetchtowebmailrc") # On other systems, use the directory 
	                                                                         #  where the script is installed
verbosity = 1
permissioncheck = 1

# The processes' exit code
exitcode = 0

# Process options:
processcmdlineopts()

# Read the config file:
readconfigfile(configfile)

# Some checks:
if not (username and password):
	do_print("Configuration error: No username and password specified.", 4)
	sys.exit(1)
if not forwardaddress:
	do_print("Configuration error: Please specify an email address for forwarding of the mails retrieved.", 4)
	sys.exit(1)
if usesmtp:
	if not smtpserver:
		do_print("Configuration error: Please specify a SMTP Server if you want to use SMTP for forwarding.", 4)
		sys.exit(1)
else:
	if not mda:
		do_print("Configuration error: Please specify an MDA for forwarding (or use SMTP).", 4)
		sys.exit(1)

if debug:
	if os.access(ourtempdir, os.F_OK):
		os.system("rm -rf " + ourtempdir) # Remove the directory if it exists (in a very "hackish" way ;-) )
	os.mkdir(ourtempdir, 0700)
	print >> sys.stderr, "NOTE: Running in debug mode. Use it only for development/debugging."
	verbosity = 0 # Print all messages

### begin doing the actual work ;-)

# Add "INBOX" to the list of folders to poll if not present:
for f in pollfolders:
	if (f == "INBOX"):
		break;
else:
	pollfolders.append("INBOX")

if (usepycurl == 2): # auto-detect
	try:
		import pycurl
		usepycurl = 1
	except ImportError:
		usepycurl = 0

if usepycurl:
	import pycurl, cStringIO
	do_print("Using PycURL (%s) for web access." % pycurl.version, 0)
	globalcurl = pycurl.Curl()
	globalcurl.setopt(pycurl.FOLLOWLOCATION, 1)
	globalcurl.setopt(pycurl.MAXREDIRS, 5)
	globalcurl.setopt(pycurl.COOKIEFILE, "") # Enable cookies
	globalcurl.setopt(pycurl.ENCODING, "") # Enable compression
	if debug:
		globalcurl.setopt(pycurl.VERBOSE, 1)
else:
	do_print("Using Python's urllib2/cookielib for web access.", 0)
	import cookielib, urllib2
	# Initialize urllib
	cookiejar = cookielib.CookieJar()
	opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cookiejar))
	urllib2.install_opener(opener)

do_print("Connecting to " + website + " ...")

page = geturl(website)
jsredirect = JSRedirectionParser()
jsredirect.feed(saveifdebug(page.read(), "first.html"))
page.close()

do_print("Redirecting to " + jsredirect.redirecttarget, 0)

# If opening the login page fails, an exception will be raised and the script will exit
page = geturl(jsredirect.redirecttarget)
# Parse the page:
lfp = LoginFormParser()
lfp.user = username
lfp.password = password
lfp.feed(saveifdebug(page.read(), "login.html"))
page.close()

# Try to login:
if (lfp.forminfo["method"].upper() == "POST"):
	target = urlparse.urljoin(jsredirect.redirecttarget, lfp.forminfo["action"])
	do_print("Logging in to " + target)
	pagetup = geturl2(target, urllib.urlencode(lfp.postdata))
	page = pagetup[0]
	saveifdebug(page.read(), "cookieerror.html")
	page.close()
	# Second load is obviously necessary (Cookie problem?)
	do_print("Loading " + pagetup[1] + " (again)", 0)
	pagetup = geturl2(pagetup[1])
	page = pagetup[0]
	saveifdebug(page.read(), "afterlogin.html")
	page.close()
else:
	sys.exit("Unsupported login method: " + lfp.forminfo["method"])


#target = urlparse.urljoin(page.geturl(), "/index.php?ctl=browser_register")
#do_print("Doing browser_register on " + target, 0)
#page = geturl(target)
#saveifdebug(page.read(), "browser_register.html")
#page.close()

#target = urlparse.urljoin(page.geturl(), "/index.php?ctl=overview")
#do_print("Going to overview: " + target, 0)
#page = geturl(target)
#saveifdebug(page.read(), "overview.html")
#page.close()

if fetchonlynewmails: # Load the IDs file if necessary
	try:
		idsfile = open(mailidsfile, "r")
	except IOError:
		pass
	else:
		mailid_load = cPickle.load(idsfile)
		# Old format: mailids_load is a list of 2-tuples in the form (id, timestamp); the first element contains the username
		# Format v1: first item: version number, second item: username, rest: list of ids
		# Format v2: first item: version number, second item: username, third item: dictionary "folder name" -> list of mailids
		try: 
			readver = int(mailid_load[0])
		except ValueError:
			readver = 0
		if (readver == mailidsver):
			if (mailid_load[1] != username.lower()):
				do_print("Mailids for different user id found, downloading all mails")
				mailids = {} # If the username is different (thus it's another account), download all mails
			else:
				mailids = mailid_load[2]
		elif (readver == 1):
			do_print("Mailids v1 found", 0)
			if (mailid_load[1] != username.lower()):
				do_print("Mailids for different user id found, downloading all mails")
				mailids = {} # If the username is different (thus it's another account), download all mails
			else:
				mailids = { "INBOX": mailid_load[2:] }
		else:
			do_print("Old format mailids found, downloading all mails")
			mailids = {}

		idsfile.close()
	#print "mailids: ", mailids
# -- end if fetchonlynewmails

mpstack = []

for folder in pollfolders:
	target = urlparse.urljoin(pagetup[1], "/index.php?ctl=message_list&p[folder]=%s" % folder)
	npage = 1

	# Retrieve new pages until we don't have any more "next page" links
	while True: 
		do_print("Loading message list for folder %s, page %d: %s" % (folder, npage, target), 0)
		page = geturl(target)
		mp = MessageListParser()
		mp.mailids = mailids.get(folder, [])
		mp.foldername = folder
		mp.url = target
		mp.feed(saveifdebug(page.read(), "messagelist.html"))
		page.close()
		
		if (len(mp.idlist) > 0):
			do_print("%d (new) mails on page %d of folder \"%s\"." % (len(mp.idlist), npage, folder))
			mpstack.append(mp)
		else:
			do_print("No new mails on page %d of folder \"%s\"." % (npage, folder))
			# Append the still present mail ids to the list:
			new_mailidspresent = mailidspresent.get(mp.foldername, [])
			new_mailidspresent.extend(mp.mailidsfetched)
			mailidspresent[mp.foldername] = new_mailidspresent	

		if (mp.nextpage):
			target =  urlparse.urljoin(target, mp.nextpage)
		else:
			break
		npage+=1
	# end "while True"
# end "for folder ..."

if (len(mpstack) > 0): # Do we have any new mails?
	do_print("Fetching and delivering mails...")
	mailer = MyMailer()
	mailer.connect(target)
	
	for mp in mpstack:
		ok = mp.fetchidlistmails(mailer)

		new_mailidspresent = mailidspresent.get(mp.foldername, [])
		new_mailidspresent.extend(mp.mailidsfetched)
		mailidspresent[mp.foldername] = new_mailidspresent

		if (not ok):
			do_print("An error occured fetching mails, cancelling fetch.", 4)
			#sys.exit(2)
			exitcode = 2
			break
	mailer.quit()
	
	if (deleteafterfetching): # Delete in opposite direction
		do_print("Deleting mails...")
		while (len(mpstack) > 0):
			mp = mpstack.pop()
			mp.deleteidlistmails()
	elif (fetchonlynewmails):
		#mailidspresent.insert(0, mailidsver) # Insert the username and version at the beginning
		#mailidspresent.insert(1, username)
		idsfile = open(mailidsfile, "w")
		cPickle.dump([mailidsver, username, mailidspresent], idsfile)
		idsfile.close()

do_print("Logging out...")
if (mp.logoutpage):
	do_print("Logout Step 1: " + mp.logoutpage, 0)
	page = geturl(mp.logoutpage)
	lp1 = Logout1Parser()
	lp1.feed(saveifdebug(page.read(), "logout1.html"))
	page.close()

#	if (lp1.logoutpage):
#		do_print("Logout Step 2: " + lp1.logoutpage, 0)
#		page = geturl(lp1.logoutpage)
#		saveifdebug(page.read(), "logout2.html")
#		page.close()
#	else:
#		do_print("Logout page #2 not found", 3)	
else:
	do_print("Logout page #1 not found.", 3)


if (usepycurl):
	globalcurl.close()

sys.exit(exitcode)

