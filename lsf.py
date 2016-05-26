#!/usr/bin/env python

#  Allow this module to work with Python 2 or 3
from __future__ import print_function

"""
lsf

Standalone Python module that combines the features of the
Unix commands 'ls' and 'find'.  Create a symbolic link so you can just
type 'lsf' to execute this file:

    ln -s lsf.py lsf
    
Then enter the command "lsf -h" to display usage information.
"""

import os, sys, stat, time, re, argparse

OPTS = None # global will contain results of parsing the command line
TOTFILES = TOTSIZE = GTOTFILES = GTOTSIZE = 0

OS_IS_WINDOWS = (os.name == "nt")
if OS_IS_WINDOWS:
    DEFAULT_FIELD_STRING = "Msmn"
else:
    DEFAULT_FIELD_STRING = "MNugsmnt"
    import pwd, grp   # Windows doesn't have these modules

class FileTypeCode(object):
    """Some helper dictionaries for dealing with the file type value
    embedded in the mode value returned from os.lstat().
    """
    #  Map IFMT field of mode to file type character
    #   (if we encounter a broken link, the statfile function returns mode=0)
    to_char = {
        0 : 'l',
        stat.S_IFDIR : 'd',
        stat.S_IFCHR : 'c',
        stat.S_IFBLK : 'b',
        stat.S_IFREG : '-',
        stat.S_IFLNK : 'l',
        stat.S_IFIFO : 'p',
        stat.S_IFSOCK : 'S'
    }
    #  Map file type characters as specified in '-e' option to type codes
    from_char = {
        'd' : stat.S_IFDIR,
        'c' : stat.S_IFCHR,
        'b' : stat.S_IFBLK,
        'r' : stat.S_IFREG,
        'l' : stat.S_IFLNK,
        'p' : stat.S_IFIFO,
        's' : stat.S_IFSOCK
    }
    #  Map IFMT field of mode to file type string
    to_string = {
        0 : 'broken link',
        stat.S_IFDIR : 'directory',
        stat.S_IFCHR : 'character special',
        stat.S_IFBLK : 'block special',
        stat.S_IFREG : 'regular',
        stat.S_IFLNK : 'symbolic link',
        stat.S_IFIFO : 'named pipe',
        stat.S_IFSOCK : 'socket'
    }
    
class Unixtime(object):
    """Uses standard 32 bit unix times, but makes them flexible by
    allowing comparisons to strings representing fixed or relative
    date/time values.
    
    >>> u = Unixtime(1412966220)
    >>> u == 'Oct 10 2014 11:37'
    True
    """
    display_long_times = False
    six_months_ago = time.time() - (6 * 30 * 24 * 60 * 60)
    known_strings = {}

    def __init__(self, date_time):
        """Takes a 32 bit unix date/time value as an integer argument.
        """
        self.value = date_time
        
    @staticmethod
    def str_to_secs(time_str):    
        """Convert string time_str into a 32 bit unix time.  The string may be
        a relative time like '2w' meaning 2 weeks prior to now, or an
        absolute date/time like 'Jul 22 2012 16:37'
        
        >>> time.ctime(Unixtime.str_to_secs('Jul 22 2012 16:37'))
        'Sun Jul 22 16:37:00 2012'
        >>> time.ctime(Unixtime.str_to_secs('Jul 22 2012')) # time of day is optional
        'Sun Jul 22 00:00:00 2012'
        """
        if time_str in Unixtime.known_strings:
            return Unixtime.known_strings[time_str]
        try: # if valid relative time string, this will work
            utime = int(time.time() - Unixtime.reltime_to_secs(time_str))
        except ValueError: # not a good relative time, try absolute date/time
            time_format = "%b %d %Y %H:%M"
            if len(time_str.split()) == 3: # assume it's just Month Day Year
                time_format = "%b %d %Y"
            try:
                utime = int(time.mktime(time.strptime(time_str, time_format)))
            except ValueError:
                raise ValueError("'%s' is not a valid DATETIME" % time_str)
        Unixtime.known_strings[time_str] = utime  # cache the result
        return utime       

    @staticmethod
    def reltime_to_secs(time_str):
        """Convert time interval from string with optional units character
        to integer seconds
        >>> Unixtime.reltime_to_secs('10h')  # 10 hours
        36000
        >>> Unixtime.reltime_to_secs('2')    # default unit is days (same as "2d")
        172800
        >>> Unixtime.reltime_to_secs("2days")
        Traceback (most recent call last):
        ValueError: '2days' is not a valid DATETIME string
        """
        modifier = time_str[-1].lower()
        if modifier not in "mhdwy":
            modifier = "d"
            secs = time_str
        else:
            secs = time_str[:-1]
        try:
            secs = float(secs)
        except ValueError:
            message = "'%s' is not a valid DATETIME string" % time_str
            raise ValueError(message)
        if   modifier == 'm':  secs = secs * 60                     # minutes
        elif modifier == 'h':  secs = secs * 60 * 60                # hours
        elif modifier == 'd':  secs = secs * 60 * 60 * 24           # days
        elif modifier == 'w':  secs = secs * 60 * 60 * 24 * 7       # weeks
        elif modifier == 'y':  secs = secs * 60 * 60 * 24 * 365     # years 
        return int(secs)
        
    def arg_to_unixtime(func):
        """Decorator that may be used on methods of this class that only handle
        integer arguments.  If the argument is a string, it is converted to an 
        integer before being passed to the method.
        """
        def wrapper(self, arg):
            if isinstance(arg, str):
                arg = Unixtime.str_to_secs(arg)
            return func(self, arg)
        return wrapper
            
    @arg_to_unixtime
    def __lt__(self, other):
        return self.value < other
        
    @arg_to_unixtime
    def __le__(self, other):
        return self.value <= other
        
    @arg_to_unixtime
    def __gt__(self, other):
        return self.value > other
        
    @arg_to_unixtime
    def __ge__(self, other):
        return self.value >= other
        
    @arg_to_unixtime
    def __eq__(self, other):
        return self.value == other
        
    @arg_to_unixtime
    def __ne__(self, other):
        return self.value != other
        
    def __str__(self):
        """Convert Unixtime to a string. For dates
        within the last 6 months, return "Month day time_of_day".  If file is 
        more than 6 months old, return "Month day year".  If 
        self.display_long_times is True, we always return 
        "Month day year time_of_day".
        
        >>> str(Unixtime(1272053661))
        'Apr 23  2010'
        """
        cdate = time.ctime(self.value) # "Weekday Month day time year"
        # Extract the fields we need (skip day of week)
        [month, day, timeofday, year] = cdate.split()[1:]
        if self.display_long_times:
            cdate = "%3s %2s %4s %5s" % (month, day, year, timeofday[:5])
        else:
            if self.value < self.six_months_ago:
                cdate = "%3s %2s %5s" % (month, day, year)
            else:
                cdate = "%3s %2s %5s" % (month, day, timeofday[:5])
        return cdate

        

class Uid(object):
    """Stores a numeric UID value, but allows comparisons to either
    another integer value or a username string.
    
    >>> u = Uid(0)
    >>> u == 'root'
    True
    """
    known_uids = {}
    known_usernames = {}
    
    @staticmethod               
    def from_str(user_or_id):
        """Converts argument string which may be either a username or
        a UID, into an integer UID.  Any integer string will be accepted
        and converted to an integer.  A non-integer string that is a valid
        username returns the corresponding user ID number.  An invalid
        username raises a ValueError exception.

        >>> Uid.from_str("root")
        0
        >>> Uid.from_str("123456789")
        123456789
        >>> Uid.from_str("not_a_valid_user_or_id")
        Traceback (most recent call last):
        ValueError: 'not_a_valid_user_or_id' is not a valid username or UID
        """
        if user_or_id in Uid.known_usernames:
            return Uid.known_usernames[user_or_id]
        if OS_IS_WINDOWS:
            return 0
        try:
            uid = int(user_or_id)
        except ValueError:   # wasn't an integer
            try:
                uid = pwd.getpwnam(user_or_id)[2]
            except KeyError:
                raise ValueError("'%s' is not a valid username or UID"
                                 % user_or_id)
        Uid.known_usernames[user_or_id] = uid
        return uid
                
    def make_uid(func):
        """A decorator that may be applied to a method in this class. 
        If the argument to the method is a string, it gets converted to an
        integer UID value before being passed to the method.
        """
        def wrapper(self, arg):
            if isinstance(arg, str):
                arg = Uid.from_str(arg)
            return func(self, arg)
        return wrapper
            
    def __init__(self, uid):
        self.value = uid
        
    @make_uid                
    def __lt__(self, other):
        return self.value < other                
        
    @make_uid                
    def __gt__(self, other):
        return self.value > other                
        
    @make_uid                
    def __le__(self, other):
        return self.value <= other                
        
    @make_uid                
    def __ge__(self, other):
        return self.value >= other
        
    @make_uid                
    def __eq__(self, other):
        return self.value == other                
        
    @make_uid                
    def __ne__(self, other):
        return self.value != other 
        
    def __str__(self):
        """Convert a UID to a username string.
        
        >>> str(Uid(0))
        'root'
        """
        if self.value in Uid.known_uids:
            return Uid.known_uids[self.value]
        username = None
        if not OS_IS_WINDOWS:
            try:
                username = pwd.getpwuid(self.value)[0]
            except KeyError:
                pass
        if username is None:
            username = str(self.value)  # just use integer
        Uid.known_uids[self.value] = username
        return username
               

class Gid(object):
    """Stores a numeric GID value, but allows comparisons to either
    another integer value or a group name string.
    
    >>> g = Gid(0)
    >>> g == 'root'
    True
    """
    known_gids = {}
    known_groups = {}
    
    @staticmethod
    def from_str(group_or_id):
        """Converts argument string which may be either a groupname or
        a GID, into an integer GID.  Any integer string will be accepted
        and converted to an integer.  A non-integer string that is a valid
        group name returns the corresponding group ID number.  An invalid
        group name raises a ValueError exception.

        >>> Gid.from_str("root")
        0
        >>> Gid.from_str("123456789")
        123456789
        >>> Gid.from_str("not_a_valid_group_or_id")
        Traceback (most recent call last):
        ValueError: 'not_a_valid_group_or_id' is not a valid group name or GID
        """
        if group_or_id in Gid.known_groups:
            return Gid.known_groups[group_or_id]
        if OS_IS_WINDOWS:
            return 0 
        try:  # try converting to integer directly
            gid = int(group_or_id)
        except ValueError:   # wasn't an integer
            try:  # look it up in the group file and get the GID
                gid = grp.getgrnam(group_or_id)[2]
            except KeyError:
                raise ValueError(
                    "'%s' is not a valid group name or GID" % group_or_id
                    )
        Gid.known_groups[group_or_id] = gid
        return gid
                
    def make_gid(func):
        """A decorator that may be applied to a method in this class. 
        If the argument to the method is a string, it gets converted to an
        integer GID value before being passed to the method.
        """
        def wrapper(self, arg):
            if isinstance(arg, str):
                arg = Gid.from_str(arg)
            return func(self, arg)
        return wrapper
            
    def __init__(self, gid):
        self.value = gid
        
    @make_gid
    def __lt__(self, other):
        return self.value < other                
        
    @make_gid
    def __gt__(self, other):
        return self.value > other                
        
    @make_gid
    def __le__(self, other):
        return self.value <= other                
        
    @make_gid
    def __ge__(self, other):
        return self.value >= other                
        
    @make_gid
    def __eq__(self, other):
        return self.value == other                
        
    @make_gid
    def __ne__(self, other):
        return self.value != other                
        
    def __str__(self):
        """Convert a GID to a group name string.
        
        >>> str(Gid(0))
        'root'
        """
        if self.value in Gid.known_gids:
            return Gid.known_gids[self.value]
        group = None
        if not OS_IS_WINDOWS:
            try:
                group = grp.getgrgid(self.value)[0]
            except KeyError:
                pass
        if group is None:
            group = str(self.value)
        Gid.known_gids[self.value] = group
        return group
        

class FileSize(object):
    """Stores an integer value representing the size of a file.  Allows
    comparison to another integer or a string that looks like an integer
    with an optional multiplier character (e.g. '8k' == 8 * 1024).
    
    >>> size = FileSize(2048)
    >>> size == 2048
    True
    >>> size == '2k'
    True
    >>> size > '3m'
    False
    """
    known_strings = {}
    
    @staticmethod
    def from_string(size_str):
        """Convert size from string with optional multipliers to integer
        >>> FileSize.from_string("1234")
        1234
        >>> FileSize.from_string("10k")
        10240
        >>> FileSize.from_string("10.5k")
        10752
        >>> FileSize.from_string("10KB")
        Traceback (most recent call last):
        ValueError: '10KB' is not a valid FILESIZE string
        """
        if size_str in FileSize.known_strings:
            return FileSize.known_strings[size_str]
        modifier = size_str[-1]
        if modifier not in "bkmg":
            modifier = ""
            size = size_str
        else:
            size = size_str[:-1]
        try:
            size = float(size)
        except ValueError:
            message = "'%s' is not a valid FILESIZE string" % size_str
            raise ValueError(message)
        if modifier:
            if   modifier == 'b':  size = size * 512                # blocks
            elif modifier == 'k':  size = size * 1024               # kilobytes
            elif modifier == 'm':  size = size * 1024 * 1024        # megabytes
            elif modifier == 'g':  size = size * 1024 * 1024 * 1024 # gigabytes
        size = int(size)
        FileSize.known_strings[size_str] = size
        return size
        
    def arg_to_int(func):
        """A decorator that may be applied to a method in this class. 
        If the argument to the method is a string, it gets converted to an
        integer file size before being passed to the method.
        """
        def wrapper(self, arg):
            if isinstance(arg, str):
                arg = FileSize.from_string(arg)
            return func(self, arg)
        return wrapper

    def __init__(self, size):
        self.value = size
        
    @arg_to_int
    def __lt__(self, other):
        return self.value < other                
        
    @arg_to_int
    def __gt__(self, other):
        return self.value > other                
        
    @arg_to_int
    def __le__(self, other):
        return self.value <= other                
        
    @arg_to_int
    def __ge__(self, other):
        return self.value >= other                
        
    @arg_to_int
    def __eq__(self, other):
        return self.value == other                
        
    @arg_to_int
    def __ne__(self, other):
        return self.value != other   
        
    def __str__(self):
        return "%10d" % self.value            
    
class OS_command:
    """Stores an operating system (shell) command that must contain the 
    string '{}'.  Then the execute method can be called with a filepath
    argument and the shell command will be executed with the filepath 
    substituted for the '{}' string.  Prompts for permission
    before each execution unless first charactere of command is '+'.
    """
    
    def __init__(self, command):
        self.command = command
        self.with_prompting = True
        if self.command[0] == '+':
            self.with_prompting = False
            self.command = self.command[1:]
        
    def execute(self, filepath):
        quoted_filepath = "'" + filepath.replace("'", "\\'") + "'"
        cmd = self.command.replace("{}", quoted_filepath)
        if self.with_prompting:
            response = raw_input (cmd + " (y[es],n[o],a[ll],q[uit])? ").strip().lower()
            if len(response) == 0: response = 'n'
            if response[0] == 'n':
               return
            elif response[0] == 'q':
                sys.exit(0)
            elif response[0] == 'a':
                self.with_prompting = False
        else:
            print (cmd)
        os.system (cmd)


def arg_has_plus(arg_string):
    """Return string s with any leading plus sign removed, along with either 
    True if there was a plus or False if there wasn't.
    
    >>> arg_has_plus("no plus")
    ('no plus', False)
    >>> arg_has_plus("+plus")
    ('plus', True)
    """
    plus = False
    if arg_string[0] == '+':
        plus = True
        arg_string = arg_string[1:]
    return arg_string, plus

def parse_value_list(val_list, valid_words):
    """"
    Convert string val_list into a string of letters consisting of the
    first letters of valid_words.  If string s contains commas, we assume
    it's a comma separated list of words, verify each word is valid and
    keep only the first letter.  If no comma, we assume it's already a
    string of first letters from valid_words and we verify that each
    letter is valid.  Raises ValueError if s is not a valid word list or
    string of first letters.
    
    >>> parse_value_list("abc", ["book", "chapter", "almanac"])
    'abc'
    >>> parse_value_list("almanac,book", ["book", "chapter", "almanac"])
    'ab'
    
    If you want to use only 1 complete word, you need a trailing comma:
    >>> parse_value_list("book,", ["book", "chapter"])
    'b'
    >>> parse_value_list("abcd", ["book", "chapter", "almanac"])
    Traceback (most recent call last):
    ValueError: 'abcd' contains letters not in 'bca'.
    >>> parse_value_list("chapter,dog", ["book", "chapter", "almanac"])
    Traceback (most recent call last):
    ValueError: 'dog' not in ['book', 'chapter', 'almanac']
    """
    if not val_list: raise ValueError("missing value")
    valid_letters = [ word[0] for word in valid_words ]
    words = val_list.split(',') 
    if len(words) == 1:  # no commas
        # If input consists of first letters of valid_words
        if set(val_list).issubset(set(valid_letters)):
            letters = val_list  # it's good
        else: # bad letter[s]
            msg = "'{}' contains letters not in '{}'.".format(
                val_list, ''.join(valid_letters)
                )
            # Perhaps user was trying to enter a single complete word
            if val_list in valid_words:
                msg += (
                    "\nIf you meant the keyword '{}', ".format(val_list) + 
                    "you need to follow it with a comma."
                    )
            raise ValueError(msg)
    else: # Input is one or more comma separated words
        # In case user added a trailing comma to enter only one word
        if words[-1] == "": del words[-1]
        letters = ""
        for word in words:
            if word not in valid_words : 
                raise ValueError("'%s' not in %s" % (word, valid_words))
            letters += word[0]  # just keep 1st letter
    return letters
                    

def bytecount_to_string(nbytes):
    """Convert integer nbytes into a string representing a number of bytes.
    
    >>> bytecount_to_string(849)
    '849 bytes'
    >>> bytecount_to_string(1500)
    '1500 bytes (1.46 Kbytes)'
    >>> bytecount_to_string(123456789123)
    '123456789123 bytes (114.98 Gbytes)'
    """
    if nbytes < 1024:
        return "%d bytes" % nbytes
    units = ["Kbytes", "Mbytes", "Gbytes", "Tbytes", "Pbytes"]
    fbytes = float(nbytes)
    unit_idx = -1
    while fbytes >= 1024.0 and ((unit_idx + 1) < len(units)):
        fbytes = fbytes / 1024.0
        unit_idx += 1
    return "%d bytes (%.2f %s)" % (nbytes, fbytes, units[unit_idx])
    

class FileStats(object):
    """This object consists of the results from os.lstat(fpath)
    along with the file's path, name, path+name, and link target.
    """
    
    field_words = [
        "Mode", "inode", "dev", "Nlink", "uid", "gid", "size", "atime",
        "mtime", "ctime", "path", "name", "filepath", "target", "Typecode"
        ]
    field_letters = [ word[0] for word in field_words ]
    file_type_words = [
        "regular", "dir", "link", "char", "block", "pipe", "socket"
        ]
    file_type_chars = set([ word[0] for word in file_type_words ])    
    time_field_words = ["atime", "mtime", "ctime"]

    filter_list = []

    def __init__(self, fpath):
        try:
            path = os.path.dirname(fpath)
            filename = os.path.basename(fpath)
            self.stats = os.lstat(fpath)  # use lstat to NOT follow symlinks
            typecode = stat.S_IFMT(self.stats[0])

            # If file is a link, find the target
            if os.path.islink(fpath):
                target = os.path.realpath(fpath)
                # If target and link are in the same directory
                target_dir = os.path.realpath(os.path.dirname(target))
                file_dir = os.path.realpath(path)
                if target_dir == file_dir:
                    # Don't need to include directory path
                    target = os.path.basename(target)
                target = "-> " + target # add arrow for display purposes
            else:
                target = ""  # not a link, so no target
            self.stats += (path, filename, fpath, target, typecode)
            self.error = False
        except os.error as error:
            sys.stderr.write("Cannot stat file %s: %s\n" % (fpath, error[1]))
            self.error = True 

    def mode_string(self):
        """Convert a numerical mode value (from lstat()) that we have stored
        in self.stats[0] to the string representation used in our output 
        (e.g. '-rwxr-xr-x').
        """
        # The first character indicates the file type, e.g. 'd' = directory
        mode_chars = [FileTypeCode.to_char[self.Typecode]] 
        # Add protection string characters
        mask = 0o400
        chars = 'rwxrwxrwx'
        i = 0
        while mask:
            bit_is_set = self.Mode & mask
            next_char = chars[i] if bit_is_set else '-'
            mode_chars.append(next_char)
            i = i + 1
            mask = mask >> 1
        return ''.join(mode_chars)
        
    @staticmethod
    def add_filter(field, value):
        """Add a filter to FileStats.filter_list"""
        op_index = 0    # use default (1st) comparison operator
        if value[0] == '+':
            op_index = 1  # use alternate (2nd) comparison operator
            value = value[1:]  # strip off the '+' character
            if not value: raise ValueError
        if field == "python":
            # Try out user's expression to make sure it's valid
            test_stats = FileStats(sys.argv[0])
            (Mode, inode, device, Nlink, uid, gid, size, atime, mtime, 
             ctime, path, name, filepath, target) = test_stats.to_objects()
            eval(value) # this may raise an exception 
            FileStats.filter_list.append((field, "eval", value, None, None))
            return
        if field in ("uid","gid"):
            comparison = ('in','not in')[op_index]
            value_list = value.split(',')
        if field == "Typecode":
            comparison = ('not in','in')[op_index]
            native_value = typecode_list_from_string(value)
        elif field == "uid":
            native_value = [ Uid.from_str(user) for user in value_list ]
        elif field == "gid":
            native_value = [ Gid.from_str(group) for group in value_list ]
        elif field in ["mtime", "atime", "ctime"]:
            comparison = ('>','<')[op_index]
            native_value = Unixtime.str_to_secs(value)
        elif field == "size":
            comparison = ('<','>')[op_index]
            native_value = FileSize.from_string(value)
        elif field in ("name", "path", "filepath"):
            comparison = ("~", "!~")[op_index]
            native_value = re.compile(value)
        field_index = FileStats.field_words.index(field)
        FileStats.filter_list.append((field, comparison, value, 
                                 field_index, native_value))
              
    def to_objects(self):
        """Take a FileStats object and convert some of the values into objects
        that can be more easily used in a user-generated Python expression.
        For example, the time fields (atime, mtime, ctime) are converted to
        objects that can be compared to strings.
        """
        mode = self.mode_string()
        inode = self.stats[1]
        device = self.stats[2]
        nlink = self.stats[3]
        uid = Uid(self.stats[4])
        gid = Gid(self.stats[5])
        size = FileSize(self.stats[6])
        atime = Unixtime(self.stats[7])
        mtime = Unixtime(self.stats[8])
        ctime = Unixtime(self.stats[9])
        path = self.stats[10]
        name = self.stats[11]
        filepath = self.stats[12]
        target = self.stats[13]
        return (mode, inode, device, nlink, uid, gid, size, atime, mtime, ctime,
                path, name, filepath, target)
                
    def printout(self, field_string):
        """Go through the letters in field_string and print out the 
        corresponding FileStats fields all on the same line.
        """
        objects = self.to_objects()
        for char in field_string:
            index = self.field_letters.index(char)
            field = objects[index]
            if field:
                print (objects[index], end=' ')
        print ('')
                
    def passes_filters(self):
        """Apply filters in self.filter_list to this instance. Return true if 
        all filters are true.
        """
        passes = True
        for (field, comparison, value, index, native_value) in self.filter_list:
            if comparison == '<':
                if not self.stats[index] < native_value:
                    passes = False
                    break
            elif comparison == '>':
                if not self.stats[index] > native_value:
                    passes = False
                    break
            elif comparison == 'in':
                if not self.stats[index] in native_value:
                    passes = False
                    break
            elif comparison == 'not in':
                if self.stats[index] in native_value:
                    passes = False
                    break
            elif comparison == '~':
                if not native_value.search(self.stats[index]):
                    passes = False
                    break
            elif comparison == '!~':
                if native_value.search(self.stats[index]):
                    passes = False
                    break
            elif comparison == "eval":
                (Mode, inode, device, Nlink, uid, gid, size, atime, mtime, 
                 ctime, path, name, filepath, target) = self.to_objects()
                if not eval(value):
                    passes = False
                    break
                
        if not passes and OPTS.debug:
            print ('%s excluded: fails test "%s %s %s"' % (self.filepath, field, comparison, value))
        return passes


    def __getitem__(self, index):
        if isinstance(index, str):
            if len(index) > 1:
                index = self.field_words.index(index)
            else:
                index = self.field_letters.index(index)
        return self.stats[index]
        
    def __getattr__(self, attrib):
        return self[attrib]
   
def typecode_list_from_string(type_list):
    """Convert strings like "dl" or "dir,link" to list of corresponding
    type type codes (integer values).
    """
    type_list, include = arg_has_plus(type_list)
    try:
        tstring = parse_value_list(type_list, FileStats.file_type_words)
    except ValueError as error:
        raise argparse.ArgumentTypeError(error.message)
    tc_set = set(tstring)  # convert string to set of characters
    if include: # then our exclude list is those types NOT in the users list
        tc_set = FileStats.file_type_chars.difference(tc_set)
    # Map type characters into list of type codes to exclude
    typecode_list = [ FileTypeCode.from_char[char] for char in tc_set ]
    if 'l' in tc_set:
        typecode_list.append(0) # add typecode for broken link
    return typecode_list
    
def stat_files(filepaths):
    """Returns a list of FileStat objects."""
    statlist = []
    for filepath in filepaths:
        stats = FileStats(filepath)
        if not stats.error:
            statlist.append(stats) # if successful add to list
    return statlist
                     
def apply_all_filters(statlist):
    if not FileStats.filter_list:
        return statlist
    newlist = []
    for stats in statlist:
        if stats.passes_filters():
            newlist.append(stats)
    return newlist
    
def sort_stats(statlist):
    "Sort the statlist according to OPTS.sort"
    from operator import itemgetter
    sort_fields, reverse_sort = arg_has_plus(OPTS.sort)
    for field_letter in sort_fields[::-1]:
        statlist.sort(key=itemgetter(field_letter), reverse=reverse_sort)
    return statlist

                        
def display_statlist(statlist):
    """Take a list of file stats and generate our output.  If the --merge
    option wasn't used, then statlist will be composed of files from a 
    single directory.
    """
    global GTOTSIZE, GTOTFILES, TOTSIZE, TOTFILES
    TOTSIZE = TOTFILES = 0
    statlist = apply_all_filters(statlist)
    statlist = sort_stats(statlist)

    if statlist and not OPTS.quiet and not OPTS.merge:
        # Since MERGE is off, we can assume all paths are
        # the same -- just grab the first one
        path = statlist[0].path
        if not path: path = "."
        print ("\nDirectory %s\n" % path)

    for stats in statlist:
        stats.printout(OPTS.fields)
        TOTFILES += 1
        TOTSIZE += stats.size
        if OPTS.os_command:
            OPTS.os_command.execute(stats.filepath)
            
    if statlist and not OPTS.quiet:
        print ("\nTotal of %s files, %s" % 
               (TOTFILES, bytecount_to_string(TOTSIZE)))
        GTOTFILES = GTOTFILES + TOTFILES
        GTOTSIZE = GTOTSIZE + TOTSIZE
    return 
    
def stat_directory(path):
    """Returns a list of stats for each file in path"""
    try:
        files = os.listdir(path)
    except os.error as error:
        sys.stderr.write("Unable to access %s: %s\n" % (path, error[1]))
        return []
    if not OPTS.all:
        files = [ f for f in files if f[0] != '.' ]
    if not files:
        return []
    filepaths = [ os.path.join(path, f) for f in files ]
    statlist = stat_files(filepaths)
    if not OPTS.merge:
        display_statlist(statlist)
        statlist = []
    if OPTS.recursive: 
        subdirectories = [ 
            f for f in filepaths 
                if (os.path.isdir(f) and not os.path.islink(f)) 
            ]
        if subdirectories:
            for directory in subdirectories:
                statlist += stat_directory(directory)
    return statlist

def show_paths(paths):
    """Display our 'ls'-like output for all files in all paths
    """
    statlist = []
    last_dir = None
    for path in paths:
        this_dir = os.path.dirname(path)
        if (last_dir is not None) and (this_dir != last_dir) and not OPTS.merge:
            display_statlist(statlist)
            statlist = []
        if os.path.isdir(path) and not OPTS.directory:
            statlist += stat_directory(path)
        else:
            statlist += stat_files([path])
        last_dir = this_dir
    if statlist:
        display_statlist(statlist)
    if (TOTFILES != GTOTFILES) and not OPTS.quiet:
        print ("\n Grand total of %s files, %s" % 
                (str(GTOTFILES), bytecount_to_string(GTOTSIZE)))
                              

HELP_NOTES = """
FIELDS is a comma-separated list of one or more of these words: 
  %s
or just the first letter of each word without commas (e.g. "-f Mode,size,name" 
is equivalent to "-f Msn").  The default value for FIELDS is "%s".

TIME_FIELDS is like FIELDS, but only uses the words: %s.

FILETYPES is a comma-separated list of one or more of the following words:
  %s
or just the first letter of each word without commas.

The FILESIZE value is a number optionally followed by a letter indicating 
units (one of b[locks],k[ilobytes],m[egabytes],g[igabytes]).

DATETIME values for the m, a, and c options may be a number followed by a letter
(one of m[inutes],h[ours],d[ays],w[eeks],y[ears]).  In that case they are
relative to now ('2w' means two weeks ago).  You may also specify a date and
optional time ('Jul 4 2014' or 'Jul 4 2014 09:51').

Preceding the value for an argument with a plus '+' character inverts the 
comparison:
  -e +[types] = INCLUDE only specified file types
  -n, -p or -r +RE = NOT matching the specified regular expression
  -u or -g +VALUE = NOT owned by the specified UIDs or GIDs
  -S +FIELDS = sort in DESCENDING order
  
You may set environment variable LSF_OPTIONS to a string containing any options
you want to set by default.
    """ % (','.join(FileStats.field_words), 
           DEFAULT_FIELD_STRING, 
           ','.join(FileStats.time_field_words),
            ','.join(FileStats.file_type_words))
            
def mtime_arg(arg):
    "Verify that string arg is a valid datetime argument"
    try:
        FileStats.add_filter("mtime", arg)
    except ValueError:
        msg = "%s is not a valid DATETIME value" % arg
        raise argparse.ArgumentTypeError(msg)
    return arg
            
def atime_arg(arg):
    "Verify that string arg is a valid datetime argument"
    try:
        FileStats.add_filter("atime", arg)
    except ValueError:
        msg = "%s is not a valid DATETIME value" % arg
        raise argparse.ArgumentTypeError(msg)
    return arg
            
def ctime_arg(arg):
    "Verify that string arg is a valid datetime argument"
    try:
        FileStats.add_filter("ctime", arg)
    except ValueError:
        msg = "%s is not a valid DATETIME value" % arg
        raise argparse.ArgumentTypeError(msg)
    return arg
    
def execute_arg(arg):
    "Verify that string arg contains the '{}' placeholder"
    if not arg or arg.find('{}') == -1:
        raise argparse.ArgumentTypeError("COMMAND must contain '{}' placeholder string")
    return OS_command(arg)

def python_expression(fexp):
    """Raise a ValueError if fexp is not a valid Python expression using
    FileStats.field_words as local variables.
    
    >>> python_expression("Mode[0] == 'l'")  # good
    "Mode[0] == 'l'"
    >>> python_expression("Mode[0]] == 'l'") # extra right bracket
    Traceback (most recent call last):
    ArgumentTypeError: invalid Python expression: Mode[0]] == 'l'
    """
    try:
        FileStats.add_filter("python", fexp)
    except SyntaxError as error:
        raise argparse.ArgumentTypeError(
            "invalid Python expression: %s" % (fexp))
    except (ValueError, NameError) as error:
        raise argparse.ArgumentTypeError(error.message)
    return fexp
    
def field_list_arg(arg):
    """Verify that arg is a valid field list and convert from a list of field
    words to a string of field characters."""
    try:
        arg = parse_value_list(arg, FileStats.field_words)
    except ValueError as error:
        raise argparse.ArgumentTypeError(error.message)
    return arg

def sort_field_arg(arg):
    """Verify that arg is a valid field list optionally preceded by a '+'.
    """
    fields, has_plus = arg_has_plus(arg)
    plus = '+' if has_plus else ''
    field_letters = field_list_arg(fields)
    return plus + field_letters
        
def regex_arg(arg):
    """Add filter for regular express arg."""    
    try:
        FileStats.add_filter("filepath", arg)
    except re.error as error:
        raise argparse.ArgumentTypeError(
            "'%s' is not a valid regular expression: %s" % (arg, error.message))
    return arg
        
def name_arg(arg):
    """Add filter for regular express arg."""    
    try:
        FileStats.add_filter("name", arg)
    except re.error as error:
        raise argparse.ArgumentTypeError(
            "'%s' is not a valid regular expression: %s" % (arg, error.message))
    return arg
        
def path_arg(arg):
    """Add filter for regular express arg."""    
    try:
        FileStats.add_filter("path", arg)
    except re.error as error:
        raise argparse.ArgumentTypeError(
            "'%s' is not a valid regular expression: %s" % (arg, error.message))
    return arg
    
def group_list_arg(arg):
    "Verify that arg is a valid list of group numbers and or names"
    try:
        FileStats.add_filter("gid", arg)
    except ValueError as error:
        raise argparse.ArgumentTypeError(error.message)
    return arg
    
def user_list_arg(arg):
    "Verify that users is a valid list of UIDs or usernames"
    try:
        FileStats.add_filter("uid", arg)
    except ValueError as error:
        raise argparse.ArgumentTypeError(error.message)
    return arg
    
def size_arg(arg):
    "Verify that arg is a valid file size argument"
    try:
        FileStats.add_filter("size", arg)
    except ValueError as error:
        raise argparse.ArgumentTypeError(error.message)
    return arg
    
def time_field_list_arg(arg):
    "Verify that arg is a valid list of time fields"
    try:
        arg = parse_value_list(arg, FileStats.time_field_words)
    except ValueError as error:
        raise argparse.ArgumentTypeError(error.message)
    return arg

def exclude_arg(type_list):
    """Add file type list to filters.
    """
    try:
        FileStats.add_filter("Typecode", type_list)
    except ValueError as error:
        raise argparse.ArgumentTypeError(error.message)
    return type_list
    
def parse_command_line(cmd_line):
    """Set up the argument parser and then parse the command line.
    Return the parsed results object.
    """
    parser = argparse.ArgumentParser(
        prog="lsf",
        description="lsf (ls + find utility)",
        epilog=HELP_NOTES,
        formatter_class = argparse.RawDescriptionHelpFormatter
        )
    parser.add_argument('-a', "--accessed", type=atime_arg,  
      metavar='DATETIME', help=
      "show only files accessed since DATETIME (or prior to +DATETIME)")
    parser.add_argument('-A', "--all", action='store_true', help=
      "show all files (i.e. include hidden files)")
    parser.add_argument('-c', "--created", type=ctime_arg,  
      metavar='DATETIME', help=
      "show only files created since DATETIME (or prior to +DATETIME)")
    parser.add_argument('-D', "--debug", action='store_true', help=
      "debug mode (shows why files were excluded from listing)")
    parser.add_argument('-d', "--directory", action='store_true', help=
      "list directory entries instead of their contents")
    parser.add_argument('-e', "--exclude", type=exclude_arg, 
      metavar='FILETYPES', help=
      "list of FILETYPES to exclude")
    parser.add_argument('-F', "--filter", type=python_expression,  help=
      "Python expression for file selection "
      "(e.g. 'uid == 0 or size < \"10m\"')")
    parser.add_argument('-f', "--fields", type=field_list_arg, help=
      "list of FIELDS to display (see definition of FIELDS below)")
    parser.add_argument('-g', "--group", type=group_list_arg,  help=
      "show only files owned by specifed list of group names and/or gids")
    parser.add_argument('-l', "--longtimes", action='store_true', help=
      "display times in long format (month day year time)")
    parser.add_argument('-m', "--modified", type=mtime_arg,  
      metavar='DATETIME', help=
      "show only files modified since DATETIME (or prior to +DATETIME)")
    parser.add_argument('-M',  "--merge", action='store_true', help=
     "merge directories together before applying sort")
    parser.add_argument('-n',  "--name", type=name_arg, 
      metavar='REGEX', help=
      "show only files whose name matches regular expression REGEX")
    parser.add_argument('-p',  "--path", type=path_arg, 
      metavar='REGEX', help=
      "show only files whose directory path matches regular expression REGEX")
    parser.add_argument('-q', "--quiet", action='store_true', help=
      "only print 1 line per file (no file counts, etc.)")
    parser.add_argument('-R', "--recursive", action='store_true', help=
      "recurse into subdirectories")
    parser.add_argument('-r', "--regex", type=regex_arg, 
      metavar='REGEX', help=
      "show only files whose full path matches regular expression REGEX")
    parser.add_argument('-s', "--size", type=size_arg,  
      metavar='FILESIZE', help=
      "show only files with size less than FILESIZE "
      "(or greater than +FILESIZE)")
    parser.add_argument('-S', "--sort", type=sort_field_arg, 
      metavar='FIELDS', help=
      "specify sort FIELDS (e.g. -Ssm = sort by size then mtime)")
    parser.add_argument('-t', "--time", type=time_field_list_arg, 
      metavar='TIME_FIELDS', help=
      "specify TIME_FIELDS to display (default is 'mtime')")
    parser.add_argument('-u', "--user", type=user_list_arg, help=
      "show only files owned by specified list of usernames and/or uids")
    parser.add_argument("-v", "--version", action='version', 
        version="%(prog)s 1.0")
    parser.add_argument("-x", "--execute", metavar="COMMAND", type=execute_arg, 
      dest="os_command", help=
      "execute COMMAND for each file using '{}' as placeholder; start COMMAND with '+' to suppress prompting")
    parser.add_argument("paths", nargs=argparse.REMAINDER)
    return parser.parse_args(cmd_line)

def main():
    """Process the command line options to set all the global variables that
    affect our processing, then call show_paths on each of the remaining
    command line arguments.
    """
    global OPTS
    cmd_line = sys.argv[1:]
    if "LSF_OPTIONS" in os.environ:
        cmd_line = os.environ["LSF_OPTIONS"].split() + cmd_line
    
    OPTS = parse_command_line(cmd_line)
                
    if OPTS.directory: OPTS.quiet = True
    if not OPTS.sort: OPTS.sort = 'n'
    
    if not OPTS.fields:
        OPTS.fields = DEFAULT_FIELD_STRING
        if OPTS.quiet or OPTS.merge:
            # Directory path will not be shown separately, so we need
            #  to use the full file path not just the file name
            OPTS.fields = OPTS.fields.replace('n','f')
        if OPTS.time:
            # Use user-specified date fields instead of default 'm'
            OPTS.fields = OPTS.fields.replace('m', OPTS.time)
        elif OPTS.sort and (OPTS.sort in "ac"):
            # if sorting by atime or ctime, display that date instead of mtime
            OPTS.fields = OPTS.fields.replace('m', OPTS.sort)
            
    if 'n' not in OPTS.sort:
        # We want otherwise matching lines to be sorted by filename
        OPTS.sort += 'n'
        
    Unixtime.display_long_times = OPTS.longtimes
       
    if not OPTS.paths:
        OPTS.paths = [os.curdir]

    show_paths(OPTS.paths)
    

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)  # allow user to break out with Ctrl-C
