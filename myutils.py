import MySQLdb as mysql
from MySQLdb.cursors import Cursor, SSCursor
import re
import sys
import string
import json
import time

# it is important that this order be maintained throughout all code
querytypes = ('INSERT', 'SELECT', 'CREATE_TABLE', 'SET', 'LOAD', 'ALTER', 'OTHER')

with open('config.json') as configfile:
    config = json.load(configfile)
    
    # Ugly hack to allow cursorclass to be specified in the config file
    if 'db_conn_params' in config and 'cursorclass' in config['db_conn_params']:
        config['db_conn_params']['cursorclass'] = getattr(sys.modules[__name__],
                                                          config['db_conn_params']['cursorclass'])

def define_time_functions(cur):
    cur.execute("DROP FUNCTION IF EXISTS my_year")
    cur.execute("""CREATE FUNCTION my_year (e DATETIME)
                   RETURNS INT DETERMINISTIC
                   RETURN YEAR(e)""")

    cur.execute("DROP FUNCTION IF EXISTS my_month")
    cur.execute("""CREATE FUNCTION my_month (e DATETIME)
                   RETURNS INT DETERMINISTIC
                   RETURN YEAR(e) * 12 + MONTH(e) - 1""")

    cur.execute("DROP FUNCTION IF EXISTS my_week")
    cur.execute("""CREATE FUNCTION my_week (e DATETIME)
                   RETURNS INT DETERMINISTIC
                   RETURN YEAR(e) * 53 + WEEKOFYEAR(e)""")

    cur.execute("DROP FUNCTION IF EXISTS my_day")
    cur.execute("""CREATE FUNCTION my_day (e DATETIME)
                   RETURNS INT DETERMINISTIC
                   RETURN FLOOR( UNIX_TIMESTAMP(e) / (24 * 60 * 60) )""")

    cur.execute("DROP FUNCTION IF EXISTS my_hour")
    cur.execute("""CREATE FUNCTION my_hour (e DATETIME)
                   RETURNS INT DETERMINISTIC
                   RETURN FLOOR( UNIX_TIMESTAMP(e) / (60 * 60) )""")

def get_conn(dbname=None):
    kwargs = config.get('db_conn_params') or {}
    if dbname:
        kwargs['db'] = dbname

    return mysql.connect(**kwargs)

def printlist(lst, skiplines=False):
    """convenience fcn for printing a list (helpful from command line)"""
    for l in lst:
        print l
        if skiplines: print "\n"

def print_and_execute(query, cur):
    print "Executing:"
    print query
    starttime = time.time()
    cur.execute(query)
    print "Query executed in {0} sec".format(time.time() - starttime)


def get_reserved_words(filename):
    """
    Generate a set of words from a file, one word per line
    Whitespace around the word is stripped
    Used for getting the list of mysql keywords from a text file
    """
    with open(filename) as infile:
        return set(line.strip() for line in infile.readlines())


def clean(query, reserved_words=None):
    """
    Transform queries into a standard format:

    1. Capitalize all keywords, as defined by @reserved_words
    2. replace all runs of whitespace with a single space character
    """

    if not reserved_words:
        reserved_words = get_reserved_words('mysql_keywords.txt')

    cleaned_query = query.strip()
    cleaned_query = ' '.join([
        (word.upper() if word.upper() in reserved_words else word)
        for word in re.split('\s+', query)
    ])
    
    return cleaned_query

user_host_re = re.compile(r".*\[(?P<uname>.*)\] @ (?P<server>.*) \[(?P<ip>.*)\]")
def parse_user_host(user_host):
    """
    Extracts the username and server from a user_host log entry string:

    parse_user_host("abecker[abecker] @ darkstar.astro.washington.edu [128.95.99.45]")
    returns ('abecker', 'darkstar.astro.washington.edu')
    """

    m = user_host_re.match(user_host)
    if not m:
        print >>sys.stderr, "username not found in: {0}".format(user_host)
        return user_host
    try:
        return m.group('uname'), m.group('server')
    except ValueError:
        print "ERROR parsing {0}".format(user_host)
        return '', ''


const_re = re.compile(r'[<>=]+ *([-0-9.e]+)')
def replace_constants(query, replchar='?'):
    return const_re.sub(lambda x: x.group().replace(x.group(2), replchar), query)

def repl_constants(query, replchar = '?'):
    vals = []
    for m in const_re.finditer(query):
        vals.append(m.group(1))
        # This would be a problem if the constant appeared elsewhere in the query:
        # query = query.replace(m.group(2), replchar)
        query = query.replace(m.group(), m.group().replace(m.group(1), replchar))

    return query, vals

def alpha_sequence():
    """
    Returns a, b, c, ..., aa, bb, cc, ..., aaa, bbb, ccc, ...
    Useful for naming temp tables
    """

    repeats = 1
    while True:
        for letter in string.ascii_lowercase:
            yield letter * repeats
        repeats += 1


def clean_list(l):
    """
    If @l is empty, return None
    If len(l) == 1, return the single element
    Else return l
    """

    if not l:
        return None
    if len(l) == 1:
        return l[0]
    return l


def parse_query(query, cat_str = ' || '):
    """
    Returns a tuple of:
    (type of query (an element of self.querytypes),
    query with constants replaced by @replchar,
    the constant values catted together joined by @cat_str)
    """

    parsed = parse(query)[0]

    final, literals = parse_statement(parsed)

    return parsed.get_type(), final, cat_str.join(literals)


def parse_statement(statement):
    """
    Take a sqlparse.sql.Statement object and return a statement object with all
    literals replaced by a tokens.Literal object of value '?', and the same
    thing done recursively on Statement tokens. Also return the list of literals
    in the statement
    """
    literals = []
    final = ''
    for part in statement.flatten():
        if part.ttype in tokens.Literal:
            literals.append(unicode(part))
            # final_parsed.append(sql.Token(tokens.Literal, '?'))
            final += '?'
        # elif part.is_group():
        #     stmnt, lits = parse_statement(part)
        #     literals.extend(lits)
        #     final_parsed.append(stmnt)
        elif part.is_whitespace():
            final += ' '
        elif part.ttype in tokens.Keyword:
            final += unicode(part).upper()
        else:
            final += unicode(part)

    return final, literals

def partition_from_str(tablename):
    """
    Given a table name (eg '2010_04'), return the MySQL partition_definition
    string for the partition containing the data from that table. The name
    of the partition is the same as the name of the table, and the range is
    'VALUES LESS THAN <that month +1 day>'

    partition_from_str('2010_04') returns "PARTITION 2010_04 VALUES LESS THAN (TO_DAYS(2010-05-01))"
    partition_from_str('2010_12') returns "PARTITION 2010_12 VALUES LESS THAN (TO_DAYS(2011-1-01))"
    """
    
    year, month = [int(x) for x in tablename.split('_')]
    if month == 12:
        yr = str(year + 1)
        mo = "1"
    else:
        yr = str(year)
        mo = str(month + 1)
    return "PARTITION {name} VALUES LESS THAN (TO_DAYS('{yr}-{mo}-01'))".format(name = tablename,
                                                                                yr = yr,
                                                                                mo = mo)
