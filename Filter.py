from datetime import datetime, timedelta
import sys
from collections import defaultdict
from operator import itemgetter
from myutils import querytypes, print_and_execute

order = querytypes

class Filter:
    def __init__(self, daterange=None, user=None, server=None,
                 search_string=None, query_type=None, negate=False):
        """
        Create a filter to select data from a table. The filter criteria are
        passed to this ctor. Any or all of the following criteria can be
        passed:
        
        @daterange -     a 2-tuple or 2 element list of datetime objects
                         bounding the time to select

        @user -          a list or tuple of userids to accept

        @server -        a list of tuple of serverids to accept

        @search_string - a SearchStringList object. Contains the strings to
                         search in the query text (using mysql's LIKE) and
                         the way to combine multiple searches (any/all/etc.)

        @query_type -    a.) a list or tuple of query types to accept

                         OR

                         b.) a single query type to accept

        @negate -        optional, inverts the selection criteria if True.
                         Defaults to False. Careful with this one.
        """
        self.daterange = daterange
        self.user = user
        self.server = server
        self.search_string = search_string
        self.query_type = query_type
        self.negate = negate


    # returns a sql query to select data matching this filter in @tablename
    def sql(self, tablename, fields=['*']):
        if self.daterange is not None:
            time_condition = "(event_time > '{0}' AND event_time < '{1}')".format(
                self.daterange[0].isoformat(), (self.daterange[1] + timedelta(days=1)).isoformat())
        else:
            time_condition = None

        if (isinstance(self.user, list) or isinstance(self.user, tuple)) and len(self.user) > 1:
            user_condition = "userid IN ({0})".format(", ".join(str(x) for x in self.user))
        elif self.user and len(self.user) == 1:
            user_condition = "userid = {0}".format(self.user[0])
        else:
            user_condition = None

        if (isinstance(self.server, list) or isinstance(self.server, tuple)) and len(self.server) > 1:
            server_condition = "serverid IN ({0})".format(", ".join(str(x) for x in self.server))
        elif self.server and len(self.server) == 1:
            server_condition = "serverid = {0}".format(self.server[0])
        else:
            server_condition = None

        search_condition = self.search_string.to_sql() if self.search_string else None

        if (isinstance(self.query_type, list) or isinstance(self.query_type, tuple)) and len(self.query_type) > 0:
            query_condition = "query_type IN ({0})".format(", ".join("'" + x + "'" for x in self.query_type))
        elif self.query_type:
            query_condition = "query_type = '{0}'".format(self.query_type)
        else:
            query_condition = None

        where_clause = ('NOT ' if self.negate else '') + '(' + (' OR ' if self.negate else ' AND ').join(
            filter(lambda x: x is not None, (time_condition, user_condition,
                                             server_condition, search_condition,
                                             query_condition))
        ) + ')'
        
        if where_clause in ('()', 'NOT ()'):
            query = "SELECT {0} FROM {1}".format(', '.join(fields), tablename)
        else:
            query = "SELECT {0} FROM {1} WHERE {2}".format(", ".join(fields),
                                                           tablename, where_clause)
        return query


    def __eq__(self, other):
        if not isinstance(other, Filter):
            return False
        return self.daterange == other.daterange and self.user == other.user and \
                self.server == other.server and self.search_string == other.search_string \
                and self.query_type == other.query_type and self.negate == other.negate

    def __ne__(self, other):
        return not self.__eq__(other)


class SearchStringList(list):
    """
    This class is a list with a combiner attribute which is one of
    'any' (the default), 'all', 'none', 'not all', and has a method
    for converting to a sql condition
    """
    def __init__(self, combiner = 'any', *args, **kwargs):
        super(SearchStringList, self).__init__(*args, **kwargs)
        if combiner.lower() not in ('any', 'all', 'none', 'not all'):
            print >>sys.stderr, "Unrecognized combiner type: {0}. Using 'any'".format(combiner)
            self.combiner = 'any'
        else:
            self.combiner = combiner.lower()
    
    def to_sql(self):
        """
        Returns a representation of this search string list suitable for use
        in the "WHERE" clause of a sql statement.
        """
        if len(self) == 0:
            return None
        if self.combiner == 'any':
            return "(" + " OR ".join("query LIKE '{0}'".format(x) for x in self) + ")"
        if self.combiner == 'all':
            return "(" + " AND ".join("query LIKE '{0}'".format(x) for x in self) + ")"
        if self.combiner == 'none':
            return "(" + " AND ".join("query NOT LIKE '{0}'".format(x) for x in self) + ")"
        if self.combiner == 'not all':
            return "(" + " OR ".join("query NOT LIKE '{0}'".format(x) for x in self) + ")"
        return None



def query_profile(tablename, numtop, period, cur):
    """
    Generate profiles of the queries in @tablename
    """

    # We are assuming the db already has the time functions defined.
    # This is one of the actions in the create reduced log table
    # define_time_functions(cur)

    print_and_execute("""SELECT user, time, query_type, count
                         FROM (SELECT userid, my_{1}(event_time) AS time,
                                      query_type, count(*) AS count
                               FROM {0}
                               GROUP BY userid, time, query_type
                              ) AS sth
                            NATURAL JOIN users
                      """.format(tablename, period), cur)

    peruser_divided = defaultdict(dict)
    peruser_alltime = dict()
    full_divided = dict()
    full_alltime = defaultdict(int)

    for user, time, query_type, count in cur.fetchall():
        # print user, time, query_type, count

        if time not in peruser_divided[user]:
            peruser_divided[user][time] = defaultdict(int)
        peruser_divided[user][time][query_type] = count
        
        if user not in peruser_alltime:
            peruser_alltime[user] = defaultdict(int)
        peruser_alltime[user][query_type] += count
        
        if time not in full_divided:
            full_divided[time] = defaultdict(int)
        full_divided[time][query_type] += count

        full_alltime[query_type] += count
    
    #sort them by time and make into (ordered) list of tuples
    full_divided = sorted([(k, v) for (k, v) in full_divided.iteritems()], key=itemgetter(0))
    for user in peruser_divided.keys():
        peruser_divided[user] = sorted([(k, v) for (k, v) in peruser_divided[user].iteritems()],
                                       key=itemgetter(0))

    print_and_execute("""SELECT user, query, vals FROM {0} NATURAL JOIN users
                      """.format(tablename), cur)

    full_topqueries = defaultdict(dict)
    peruser_topqueries = defaultdict(dict)
    for user, query, vals in cur.fetchall():
        full_query = full_topqueries[query]
        if vals not in full_query:
            full_query[vals] = 0
        full_query[vals] += 1

        peruser_user = peruser_topqueries[user]
        if query not in peruser_user:
            peruser_user[query] = {}
        if vals not in peruser_user[query]:
            peruser_user[query][vals] = 0
        peruser_user[query][vals] += 1

    print "stored queries"

    for user in peruser_topqueries: #takes forever
        peruser_topqueries[user] = map(lambda x: (x[0], sorted(x[1].iteritems(),
                                                               key=itemgetter(1),
                                                               reverse=True)),
                                       sorted(peruser_topqueries[user].iteritems(),
                                              key=lambda x: sum(ct for val, ct in x[1].iteritems()),
                                              reverse=True)
                                   )[:numtop]
    print "sorted each user"
    #takes no time:
    peruser_topqueries = sorted(peruser_topqueries.iteritems(),
                                key = lambda x: sum( sum(ct for val, ct in valcts) 
                                                    for query, valcts in x[1] ),
                                reverse = True)

    print "sorted peruser_topqueries"
    #takes a long time:
    full_topqueries = map(lambda x: (x[0], sorted(x[1].iteritems(), key=itemgetter(1), reverse=True)),
                          sorted([(q, c) for (q, c) in full_topqueries.iteritems()],
                                 key = lambda x: sum(count for vals, count in x[1].iteritems()),
                                 reverse=True))[:numtop]

    print "sorted full_topqueries"
    return peruser_divided, peruser_alltime, full_divided, full_alltime, full_topqueries, peruser_topqueries

### Functions for converting time arguments to date strings for gnuplot
time_str_fcns = {'hour': lambda hour: datetime.fromtimestamp(hour * 60 * 60).isoformat(),
                 'day': lambda day: datetime.fromtimestamp(day * 24 * 60 * 60).isoformat(),
                 'week': lambda wk: wk, #TODO: implement
                 'month': lambda t: datetime((t+1)%12, t/12, 1).isoformat(),
                 'year': lambda year: datetime(year, 1, 1).isoformat()}

# Writes gnuplot scripts and data files for plotting query profiles in the cwd
def gnuplot(profiles, time_axis_label='time'):
    peruser_divided, peruser_alltime, full_divided, full_alltime, ftq, putq = profiles
    time_fcn = time_str_fcns[time_axis_label]

    #full_alltime (bar graph of all queries by type)
    with open('full_alltime.dat', 'w') as datafile:
        for num, cmd in enumerate(order):
            print >>datafile, '\t'.join(str(s) for s in [num, cmd, full_alltime[cmd]])
    
    with open('full_alltime_script.gnu', 'w') as scriptfile:
        print >>scriptfile, "set term png size 640,460"
        print >>scriptfile, "set output \"full_alltime.png\""
        print >>scriptfile, """set title "Total queries by type" """
        print >>scriptfile, """set ylabel "queries" """
        print >>scriptfile, "set xtics rotate"
        print >>scriptfile, "set bmargin at screen 0.3"
        print >>scriptfile, "set boxwidth 0.5"
        print >>scriptfile, "set style fill solid"
        print >>scriptfile, "set nokey"
        print >>scriptfile, """plot "full_alltime.dat" using 1:3:xtic(2) with boxes"""


    #full_divided (line graph of each type over time, also line graph of all over time)
    full_divided_data = open('full_divided.dat', 'w')
    full_divided_script = open('full_divided_script.gnu', 'w')
    print >>full_divided_script, "set term png size 640,460"

    lastTime = None
    for time, counts in full_divided:
        total_this_week = sum(counts.values())
        if lastTime:
            for missed_time in [x + lastTime + 1 for x in range(time - lastTime - 1)]:
                print >>full_divided_data, '\t'.join(str(s) for s in [time_fcn(missed_time),] +
                                                     [0,] * (len(order) + 1))
        print >>full_divided_data, '\t'.join(str(s) for s in [time_fcn(time),] +
                                             [counts[x]for x in order] +
                                             [total_this_week,])
        lastTime = time
    usings = ', '.join(""""full_divided.dat" using 1:{0} title '{1}' with lines""".format(num + 2, qtype)
                       for (num, qtype) in enumerate(order))
    print >>full_divided_script, """set output "full_divided.png" """
    print >>full_divided_script, """set title "Queries over time" """
    print >>full_divided_script, """set xlabel "{0}" """.format(time_axis_label)
    print >>full_divided_script, """set ylabel "queries" """
    print >>full_divided_script, """set xdata time"""
    print >>full_divided_script, """set xtics rotate"""
    print >>full_divided_script, """set timefmt "%Y-%m-%dT%H:%M:%S" """
    print >>full_divided_script, """plot """ + usings
    print >>full_divided_script, """set output "full_divided_total.png" """
    print >>full_divided_script, """set title "Total queries over time" """
    print >>full_divided_script, """set nokey"""
    print >>full_divided_script, """plot "full_divided.dat" using 1:{0} with lines""".format(len(order) + 2)
    full_divided_data.close()
    full_divided_script.close()


    #peruser_alltime (bar graphs of all queries from each user by type)
    with open('peruser_alltime.gnu', 'w') as scriptfile:
        print >>scriptfile, "set term png size 640,460"
        print >>scriptfile, "set xtics rotate"
        print >>scriptfile, "set bmargin at screen 0.3"
        print >>scriptfile, "set boxwidth 0.5"
        print >>scriptfile, "set nokey"
        print >>scriptfile, "set style fill solid"
        print >>scriptfile, """set ylabel "queries" """

        # data file of total queries by user
        with open('peruser_total.dat', 'w') as datafile:
            for num, user in enumerate(peruser_alltime):
                print >>datafile, '\t'.join(str(s) for s in [num, user, sum(peruser_alltime[user].values())])

        for user, queries in peruser_alltime.iteritems():
            with open('peruser_alltime_{0}.dat'.format(user), 'w') as datafile:
                for num, cmd in enumerate(order):
                    print >>datafile, '\t'.join(str(s) for s in [num, cmd, queries[cmd]])
            print >>scriptfile, """set output "peruser_alltime_{0}.png" """.format(user)
            print >>scriptfile, """set title "{0}" """.format(user)
            print >>scriptfile, """plot "peruser_alltime_{0}.dat" using 1:3:xtic(2) with boxes""".format(user)

        print >>scriptfile, 'set output "full_peruser.png"'
        print >>scriptfile, 'set xlabel "user"'
        print >>scriptfile, 'set title "Total queries by user"'
        print >>scriptfile, 'plot "peruser_total.dat" using 1:3:xtic(2) with boxes'


    #peruser_divided (line graphs of each type and total #, over time, for each user)
    with open('peruser_divided.gnu', 'w') as scriptfile:
        print >>scriptfile, "set term png size 640,460"
        print >>scriptfile, """set xlabel "{0}" """.format(time_axis_label)
        print >>scriptfile, """set ylabel "queries" """
        for user, times in peruser_divided.iteritems():
            with open('peruser_divided_{0}.dat'.format(user), 'w') as datafile:
                lastTime = None
                for time, counts in times:
                    if lastTime:
                        for missed_time in [x + lastTime + 1 for x in range(time - lastTime - 1)]:
                            print >>datafile, '\t'.join(str(s) for s in
                                                        [missed_time,] + [0,] * (len(order) + 1))

                    total_this_week = sum(counts.values())
                    # print >>datafile, '\t'.join(str(s) for s in [time,] + [float(counts[x])/total_this_week for x in order] + [total_this_week,])
                    print >>datafile, '\t'.join(str(s) for s in [time,] +
                                                [counts[x] for x in order] +
                                                [total_this_week,])
                    lastTime = time
            usings = ', '.join(""""peruser_divided_{user}.dat" using 1:{colnum} title '{qtype}' with lines""".format(user=user, colnum=num+2, qtype=qtype)
                               for (num, qtype) in enumerate(order))
            print >>scriptfile, """set output "peruser_divided_{0}.png" """.format(user)
            print >>scriptfile, """set title "{0}" """.format(user)
            print >>scriptfile, "set key on"
            print >>scriptfile, """plot """ + usings
            print >>scriptfile, """set output "peruser_divided_total_{0}.png" """.format(user)
            print >>scriptfile, """set title "Total queries by {0}" """.format(user)
            print >>scriptfile, """set key off"""
            print >>scriptfile, """plot "peruser_divided_{0}.dat" using 1:{1} with lines""".format(user, len(order) + 2)
