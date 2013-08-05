import re

from myutils import parse_user_host

class QueryReducer:
    
    def __init__(self, **kwargs):
        self.ignore_queries = set(kwargs.get('ignore_queries') or [])
        self.ignore_users = set(kwargs.get('ignore_users') or [])
        self.unwanted_terms_re = re.compile('|'.join(kwargs.get('unwanted_terms') or []))
        self.unwanted_starts_re = re.compile('|'.join('{0}.*'.format(x)
                                                      for x in (kwargs.get('unwanted_starts')
                                                                or [])))

    def accept(self, user_host, query):
        """
        @user_host - an entry from the 'user_host' column of the MySQL general_log
        @query     - an entry from the 'argument' column of the MySQL general_log
                     in a row where 'command_type' in ('Execute', 'Query'). Should
                     already be cleaned

        Returns a tuple of (user, server, query) if the query should be stored
        according to the rules of this QueryReducer, False otherwise
        """

        user, server = parse_user_host(user_host)
        if user in self.ignore_users  or query in self.ignore_queries \
           or self.unwanted_terms_re.search(query) or self.unwanted_starts_re.match(query):
            return False

        return user, server, query
        
