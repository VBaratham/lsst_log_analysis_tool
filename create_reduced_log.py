import sys
import os
import re

from myutils import get_conn, get_reserved_words, print_and_execute, clean, repl_constants, querytypes, define_time_functions, partition_from_str, config
from QueryReducer import QueryReducer

reducer = QueryReducer( **(config.get('reducer') or {}) )
    
reserved_words = get_reserved_words('mysql_keywords.txt')

numlist_re = re.compile(r'\([0-9, ]{20,}\)')
numlist_sub_fcn = lambda x: '<numlist len={0}>'.format(x.group(0).count(',') + 1)

# TODO: make this regex accept dots in table names
insert_re = re.compile(r"(INSERT INTO ['`]?\w+['`]?)")

values_re = re.compile(r'VALUES', re.I)

def reduce_log(tablename, cur):

    print >>sys.stderr, "Reducing general_log.{0} and storing into reduced_log".format(tablename)
    print >>sys.stderr, "Selecting results..."

    cur.execute("USE reduced_log")
    print_and_execute("SELECT user, userid FROM users", cur)
    users = dict(cur.fetchall())
    usernum = max(users.values()) + 1 if users.values() else 0 # first open usernum
    newusers = []

    print_and_execute("SELECT server, serverid FROM servers", cur)
    servers = dict(cur.fetchall())
    servernum = max(servers.values()) + 1 if servers.values() else 0 # first open servernum
    newservers = []

    cur.execute('USE general_log')
    print_and_execute("""SELECT * FROM {0} WHERE command_type IN ('Execute', 'Query')""".format(tablename), cur)

    print >>sys.stderr, "Selected results, cleaning queries and writing temp file..."

    temp_filename = '{0}_reduced.tmp'.format(tablename)
    outfile = open(temp_filename, 'w')

    for event_time, user_host, thread_id, server_id, command_type, query in cur:

        cleaned_query = clean(query, reserved_words)
        # Clean the query some more: remove numlists, replace constants
        cleaned_query = numlist_re.sub(numlist_sub_fcn, cleaned_query)
        cleaned_query, vals = repl_constants(cleaned_query)
        vals = ' ~ '.join(vals)
        try:
            user, server, query = reducer.accept(user_host, cleaned_query)
        except TypeError:
            continue

        if user not in users:
            users[user] = usernum
            newusers.append(user)
            usernum += 1
        if server not in servers:
            servers[server] = servernum
            newservers.append(server)
            servernum += 1
            
        if cleaned_query.startswith('INSERT INTO'):
            query_type = 'INSERT'
            if values_re.search(cleaned_query):
                #TODO: count number of rows inserted. Nontrivial because of parens, commas, quotes, etc.
                cleaned_query = insert_re.match(cleaned_query).group(0) + ' <values>'
                vals = ''
        elif cleaned_query.startswith('SELECT'):
            query_type = 'SELECT'
        elif cleaned_query.startswith('CREATE TABLE'):
            # Replacing schemas with length + hash doesn't help much.
            # There aren't many create table statements (~1%)
            # cleaned_query = re.sub(r'\(.*\)',
            #                        lambda x: '<schema len={0}, hash={1}>'.format(x.group().count(',')+1, x.group().__hash__()),
            #                        cleaned_query)
            query_type = 'CREATE_TABLE'
        elif cleaned_query.startswith('SET'):
            query_type = 'SET'
        elif cleaned_query.startswith('LOAD DATA'):
            query_type = 'LOAD'
        elif cleaned_query.startswith('ALTER'):
            query_type = 'ALTER'
        else:
            query_type = 'OTHER'

        #we ignore server_id because it's always 0...
        cleaned_query = repr(cleaned_query)[1:-1] #deal with \n and others
        final = event_time, users[user], servers[server], thread_id, query_type, cleaned_query, vals
        print >>outfile, '\t'.join(str(s) for s in final)
        
    outfile.close()

    print >>sys.stderr, "Wrote temp file, loading data into {0} table...".format(tablename)

    cur.execute("USE reduced_log")
    cur.execute("""CREATE TABLE {0} (event_time DATETIME,
                                     userid INT,
                                     serverid INT,
                                     thread_id INT(11),
                                     query_type ENUM{1},
                                     query MEDIUMTEXT,
                                     vals MEDIUMTEXT,
                                     INDEX (userid),
                                     INDEX (serverid),
                                     INDEX (event_time)
                                    )""".format(tablename, querytypes))

    cur.execute("LOAD DATA LOCAL INFILE '{0}' INTO TABLE {1}".format(temp_filename, tablename))
    os.remove(temp_filename)

    print >>sys.stderr, "Loaded data and removed temp file. Adding into users table..."

    for user in newusers:
        cur.execute("INSERT INTO users VALUES ('{0}', {1})".format(user, users[user]))
    
    print >>sys.stderr, "Added into users table, adding into servers table..."

    for server in newservers:
        cur.execute("INSERT INTO servers VALUES ('{0}', {1})".format(server, servers[server]))

    db.commit()

    print >>sys.stderr, "Added into servers table. Defining time functions..."

    # This redefines the time fcns for every table reduced, but that's a small cost
    define_time_functions(cur)

    print >>sys.stderr, "Defined time functions. Reduction complete"


def create_schema(cur):
    """
    Create the reduced_log db and the 'users' and 'servers' tables within
    (initially empty)
    """

    cur.execute("CREATE DATABASE reduced_log")
    cur.execute("USE reduced_log")
    cur.execute("CREATE TABLE users (user MEDIUMTEXT, userid INT)")
    cur.execute("CREATE TABLE servers (server MEDIUMTEXT, serverid INT)")


def create_unified(cur):
    """
    When the reduced_log.unified table does not exist, or when the schema
    changes, run this function to regenerate it.

    @Precondition: all the tables in @initial_tables must be in the reduced log
    """

    cur.execute("USE reduced_log")

    # Get list of 2 initial tables
    cur.execute("SHOW TABLES")
    initial_tables = [x for x, in cur.fetchall()][:2]

    print_and_execute("CREATE TABLE unified {0}".format(" UNION ALL ".join("SELECT * FROM {0}".format(t) for t in initial_tables)), cur)
    print_and_execute("ALTER TABLE unified ADD INDEX (userid)", cur)
    print_and_execute("ALTER TABLE unified ADD INDEX (serverid)", cur)
    print_and_execute("ALTER TABLE unified ADD INDEX (event_time)", cur)

    
    print_and_execute("ALTER TABLE unified PARTITION BY RANGE( TO_DAYS(event_time) ) ( " + 
                      ", ".join(partition_from_str(t) for t in initial_tables) + 
                      ", PARTITION other VALUES LESS THAN MAXVALUE" + ")", cur)

def unify(cur):
    """
    When a new table comes in, reduce it using reduce_log() and then run this function
    to incorporate it into the unified table, along with partitioning
    """
    
    cur.execute("USE reduced_log")
    cur.execute('SHOW TABLES')
    tables = set(x for x, in cur.fetchall())
    
    cur.execute("""SELECT PARTITION_NAME
                   FROM INFORMATION_SCHEMA.PARTITIONS
                   WHERE TABLE_SCHEMA = 'reduced_log'
                         AND TABLE_NAME = 'unified'""")
    partitions = set(x for x, in cur.fetchall())

    tables_to_add = sorted(tables - partitions - set(['unified', 'users', 'servers', 'unified_users', 'unified_servers']))
    
    for table in tables_to_add:
        print_and_execute("""ALTER TABLE unified REORGANIZE PARTITION other INTO ({0},
                  PARTITION other VALUES LESS THAN MAXVALUE)""".format(partition_from_str(table)), cur)
        print_and_execute("INSERT INTO unified SELECT * FROM {0}".format(table), cur)




if __name__ == '__main__':
    if len(sys.argv) != 2:
        print "Usage: python create_reduced_log.py [operation]. Operations:"
        print "--initialize: Create the reduced_log db and 'users' and 'servers' tables, initially empty"
        print "--reduce: take all tables from general_log and create equivalent reduced tables in the reduced_log db by the rules in config.json"
        print "--create_unified: Create the unified table in the reduced_log db"
        print "--unify: add new tables (already redyced) into the unified table"
        print "ONLY SPECIFY ONE OPTION"
        sys.exit(1)

    db = get_conn(dbname = 'general_log')
    cur = db.cursor()
        
    if sys.argv[-1] == '--initialize':
        print "Creating reduced_log db"
        create_schema(cur)
    elif sys.argv[-1] == '--reduce':
        print "Reducing the general_log and storing in reduced_log"

        cur.execute("SHOW TABLES")
        gen_log_tables = set(x for x, in cur.fetchall())

        cur.execute("USE reduced_log")
        cur.execute("SHOW TABLES")
        red_log_tables = set(x for x, in cur.fetchall())
        
        to_reduce = gen_log_tables - red_log_tables

        for tablename in sorted(to_reduce):
            reduce_log(tablename, cur)
    elif sys.argv[-1] == '--create_unified':
        print "Creating the 'unified' table"
        create_unified(cur)
    elif sys.argv[-1] == '--unify':
        print "Unifying all reduced data"
        unify(cur)

    cur.close()
    db.close()
