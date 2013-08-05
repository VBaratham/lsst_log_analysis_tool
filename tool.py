from GUI import Application, Window, ScrollableView, CheckBox, Frame, \
TextField, RadioButton, RadioGroup, Button, Image, Label

from myutils import querytypes, clean_list, print_and_execute, get_conn, config
from Filter import Filter, query_profile, gnuplot, SearchStringList
from MyComponents import TopqueryPanel, TopqueryLabel, GraphView, \
ResponsiveTextField

import os
import sys
from datetime import datetime
from glob import glob

DATEFORMAT = "%m/%d/%Y"

DEFAULT_BEGIN_DATE_TEXT = "Begin (mm/dd/yyyy)"
DEFAULT_END_DATE_TEXT = "End (mm/dd/yyyy)"
DEFAULT_USER_SEARCH_STRING = "User Search String"
DEFAULT_SERVER_SEARCH_STRING = "Server Search String"

top = 530 # Location of filter components

horiz_sp = 10 # Horizontal spacing of major panel elements
        

class Tool(Application):
    def __init__(self):
        Application.__init__(self, title = "Log Analysis Tool")
        print >>sys.stderr, "app init'd"

        self.window = Window(size = (1200, 750), title = "Log Analysis Tool")
        print >>sys.stderr, "made window"

        # Create db cursor
        db = get_conn(dbname = 'reduced_log')
        self.cur = db.cursor()
        print >>sys.stderr, "made db cursor"

        self.current_table_suffix = None
        
        # Load the dummy image for now
        self.image = GraphView(size = (640, 460), position = (10, 10))
        self.graph_panel = Frame()
        self.graph_panel.add(self.image)
        print >>sys.stderr, "loaded dummy image"

        # Declare other image lists
        self.full_ = None
        self.peruser_alltime_ = None
        self.peruser_divided_total_ = None
        self.peruser_divided_ = None

        # Create the display selection radio
        self.display_select_radiogroup = RadioGroup(action = 
                                                    self.change_images)
        height, startx = 495, 20
        sp = 10
        r1 = RadioButton("All users",
                         group = self.display_select_radiogroup,
                         value = 'all_users')
        r2 = RadioButton("Per user, query type",
                         group = self.display_select_radiogroup,
                         value = 'peruser_querytype')
        r3 = RadioButton("Per user, time",
                         group = self.display_select_radiogroup,
                         value = 'peruser_time')
        r4 = RadioButton("Per user, query type and time",
                         group = self.display_select_radiogroup,
                         value = 'peruser_querytype_time')
        
        self.graph_panel.place(r1, top = self.image + 10, left = sp)
        self.graph_panel.place(r2, top = self.image + 10, left = r1 + sp)
        self.graph_panel.place(r3, top = self.image + 10, left = r2 + sp)
        self.graph_panel.place(r4, top = self.image + 10, left = r3 + sp)
        self.window.place(self.graph_panel, top=0, left=0)
        self.display_select_radiogroup.value = 'all_users'
        
        # Create the top queries textbox
        self.topqueries = TopqueryPanel(size = (500, 460),
                                        extent = (500, 1000))
        self.topqueries.panels = [[TopqueryLabel("This is a placeholder until you select a filter",
                                                ["This is where", "the values", "will go"])]]
        self.window.place(self.topqueries, top=10, left=680)

        topqueries_next_button = Button("Next", action = self.topqueries.next)
        topqueries_prev_button = Button("Prev", action = self.topqueries.prev)
        self.window.place(topqueries_next_button, left = 930, top = top - 50)
        self.window.place(topqueries_prev_button, left = 830, top = top - 50)
        print >>sys.stderr, "made top queries text box"

        # Declare the filter and last updated filter pointers
        self.fil = None
        self.last_used_fil = None
        
        #
        # *************************
        # FILTER PANEL
        # *************************
        #

        # **CREATE DATE PANEL**
        field_width = 140
        self.date_panel = Frame()
        self.begin_date_field = TextField(size = (field_width, 30),
                                          position = (0, 5),
                                          text = DEFAULT_BEGIN_DATE_TEXT)
        self.end_date_field = TextField(size = (field_width, 30),
                                        position = (0, 35),
                                        text = DEFAULT_END_DATE_TEXT)
        self.date_panel.size = (field_width, 0)

        # Time division radios
        self.time_division_radiogroup = RadioGroup()
        left, right = 5, 70
        row1, rowspace = 95, 25

        group_by_label = Label("Group by:",
                               position = (5, 70))
        hour = RadioButton("Hour",
                           position = (left, row1),
                           group = self.time_division_radiogroup,
                           value = 'hour')
        day = RadioButton("Day",
                          position = (right, row1),
                          group = self.time_division_radiogroup,
                          value = 'day')
        week = RadioButton('Week',
                           position = (left, row1 + rowspace),
                           group = self.time_division_radiogroup,
                           value = 'week')
        month = RadioButton("Month",
                            position = (right, row1 + rowspace),
                            group = self.time_division_radiogroup,
                            value = 'month')
        year = RadioButton("Year", 
                           position = (left, row1 + 2*rowspace),
                           group = self.time_division_radiogroup,
                           value = 'year')
        self.time_division_radiogroup.value = 'day'
        self.last_grouped_by = None

        # Add all to date panel
        self.date_panel.add([self.begin_date_field, self.end_date_field])
        self.date_panel.add([group_by_label, hour, day, week, month, year])
        self.window.place(self.date_panel, top=top, left=10)
        print >>sys.stderr, "made date panel"

        # **CREATE QUERY TYPE FILTER CHECKBOXES**
        x_pos = 0
        y_pos = 0
        y_spacing = 20
        self.query_type_checkboxes = {}
        for qtype in querytypes:
            self.query_type_checkboxes[qtype] = CheckBox(qtype.replace('_',
                                                                       '_ '),
                                                         position = (x_pos,
                                                                     y_pos),
                                                         value = True)
            y_pos += y_spacing


        # Add the query type checkboxes and buttons to a Frame
        self.query_type_panel = Frame()
        maxw = 0
        for cbox in self.query_type_checkboxes.values():
            self.query_type_panel.add(cbox)
            maxw = max(cbox.size[0], maxw)
        self.query_type_panel.size = (maxw, 0)

        # Create all/none/invert buttons for query types
        buttonsize = (55, 25)
        self.query_type_panel.add(Button("All",
                                         action = (self.select_all,
                                                   'query_type'),
                                         size = buttonsize,
                                         position = (20, y_pos)))
        y_pos += 25
        self.query_type_panel.add(Button("None",
                                         action = (self.deselect_all,
                                                   'query_type'),
                                         size = buttonsize,
                                         position = (20, y_pos)))
        y_pos += 25
        self.query_type_panel.add(Button("Invert",
                                         action = (self.invert_all,
                                                   'query_type'),
                                         size = buttonsize,
                                         position = (20, y_pos)))

        # Add query_type_panel to the window
        self.window.place(self.query_type_panel, top = top,
                          left=self.date_panel + horiz_sp)
        print >>sys.stderr, "made query type cboxes"


        # **CREATE USER AND SERVER CHECKBOX LISTS**
        self.user_panel = None
        self.server_panel = None
        self.create_checkbox_lists(initial=True)

        self.cur.execute("SELECT user, userid FROM users")
        self.userids = dict(self.cur.fetchall())
        self.cur.execute("SELECT server, serverid FROM servers")
        self.serverids = dict(self.cur.fetchall())

        print >>sys.stderr, "made user, server cboxes"


        # **CREATE QUERY SEARCH STRING PANEL**
        num_search_strings = 5
        spacing = 30
        field_width = 250
        self.search_string_panel = Frame()
        self.search_string_panel.size = (field_width, 0)
        self.search_string_fields = [TextField(size = (field_width, 30),
                                               position = (0, spacing * i),
                                               text = "Query Search String {0}".format(i + 1))
                                     for i in range(num_search_strings)]
        self.search_string_panel.add(self.search_string_fields)

        self.any_all_radiogroup = RadioGroup()
        any_string_radio = RadioButton("Any",
                                       position = (40, 10 + spacing * \
                                                   num_search_strings),
                                       group = self.any_all_radiogroup,
                                       value = 'any')
        all_strings_radio = RadioButton("All",
                                        position = (130, 10 + spacing * \
                                                    num_search_strings),
                                        group = self.any_all_radiogroup,
                                        value = 'all')
        no_string_radio = RadioButton("None",
                                      position = (40, 30 + spacing * \
                                                  num_search_strings),
                                      group = self.any_all_radiogroup,
                                      value = 'none')
        not_all_string_radio = RadioButton("Not All",
                                           position = (130, 30 + spacing * \
                                                       num_search_strings),
                                           group = self.any_all_radiogroup,
                                           value = 'not all')
        self.any_all_radiogroup.value = 'any'
        self.search_string_panel.add(any_string_radio)
        self.search_string_panel.add(all_strings_radio)
        self.search_string_panel.add(no_string_radio)
        self.search_string_panel.add(not_all_string_radio)
        self.window.place(self.search_string_panel, top = top,
                          left = self.server_panel + 10)
        print >>sys.stderr, "made search string panel"


        # SELECT ALL/NONE, INVERT USERS
        # TODO: create user, server panels? atm only the cboxes are in
        # a ScrollableView
        buttonsize = (55, 25)
        invertbuttonsize = (60, 25)
        userstart = 295
        serverstart = 565
        self.window.place(Button("All",
                                 action = (self.select_all,
                                           'user'),
                                 size = buttonsize),
                          top = top + 155, left = userstart)
        self.window.place(Button("None",
                                 action = (self.deselect_all,
                                           'user'),
                                 size = buttonsize),
                          top = top + 155, left = userstart + 55 + 5)
        self.window.place(Button("Invert",
                                 action = (self.invert_all,
                                           'user'),
                                 size = invertbuttonsize),
                          top = top + 155, left = userstart + 55 + 5 + 55 + 5)
    
        # user search string textbox
        # TODO: the action is always one keystroke behind the text field.
        # This is a PyGUI 'bug',but it may only happen on windows (not sure
        # how the X server works).
        # See http://mail.python.org/pipermail/pygui/2010-November/000102.html
        self.user_search_string = ResponsiveTextField(emptyaction = None,
                                                      action = (self.select_all_matching,
                                                                'user'),
                                                      size = (180, 30),
                                                      text = DEFAULT_USER_SEARCH_STRING)
        self.window.place(self.user_search_string,
                          top = top + 155 + 25 + 5,
                          left = userstart)

        # SELECT ALL/NONE, INVERT SERVERS
        self.window.place(Button("All",
                                 action = (self.select_all,
                                           'server'),
                                 size = buttonsize),
                          top = top + 155, left = serverstart)
        self.window.place(Button("None",
                                 action = (self.deselect_all,
                                           'server'),
                                 size = buttonsize),
                          top = top + 155, left = serverstart + 55 + 5)
        self.window.place(Button("Invert",
                                 action = (self.invert_all,
                                           'server'),
                                 size = invertbuttonsize),
                          top = top + 155,
                          left = serverstart + 55 + 5 + 55 + 5)

        # server search string textbox
        self.server_search_string = ResponsiveTextField(emptyaction = None,
                                                        action = (self.select_all_matching,
                                                                  'server'),
                                                        size = (180, 30),
                                                        text = DEFAULT_SERVER_SEARCH_STRING)
        self.window.place(self.server_search_string,
                          top = top + 155 + 25 + 5, left=serverstart)

        self.window.show()


        # **CREATE BUTTONS**
        self.negate = CheckBox("Negate Filter", position=(0, 0), value=False)
        self.refresh_button = Button("Refresh",
                                     position = (0, 25),
                                     action=self.refresh)
        self.update_button = Button("Update",
                                    position = (0, 60),
                                    action = self.update)
    
        # Add buttons to a panel
        self.button_panel = Frame()
        self.button_panel.add([self.negate,
                               self.refresh_button,
                               self.update_button])
        self.window.place(self.button_panel, top = top,
                          left=self.search_string_panel + horiz_sp)
        print >>sys.stderr, "made button panel"


    def create_checkbox_lists(self, initial=False):
        """
        Removes the current user and server checkbox panels from the window,
        if they exist (if they don't, they will be None, from __init__())
        creates new ones with data from the current table, then adds them
        to the window again. If @initial is True, only the last partition
        (month) of the 'unified' table will be used for counts, but all
        users and servers will still be shown
        """

        # Remove current user and server checkbox panels from the window
        if self.user_panel:
            self.window.remove(self.user_panel)
        if self.server_panel:
            self.window.remove(self.server_panel)

        # Create user filter checkboxes
        if initial:
            print_and_execute("""SELECT PARTITION_NAME
                                 FROM INFORMATION_SCHEMA.PARTITIONS
                                 WHERE TABLE_SCHEMA = 'reduced_log'
                                       AND TABLE_NAME = 'unified'""", self.cur)
            # there will be each month, then the 'other' partition, so we want to
            # select from the 2nd to last partition
            last_partition = [x for x, in self.cur.fetchall()][-2]
            table_to_use = "unified PARTITION({0})".format(last_partition)
        else:
            table_to_use = self.current_table_name()

        print_and_execute("""SELECT userid, user, count
                             FROM (SELECT userid, COUNT(*) AS count
                                   FROM {0} GROUP BY userid
                                  ) AS sth
                               NATURAL JOIN users
                             ORDER BY count DESC
                          """.format(table_to_use), self.cur)
        userlist = [x for x in self.cur.fetchall()]

        x_pos = 0
        y_pos = 0
        y_spacing = 20
        self.user_checkboxes = {}
        size_width = 220
        extent_width = size_width
        for userid, user, count in userlist:
            self.user_checkboxes[user] = CheckBox("{0} ({1})".format(user.replace('_', '_ '), count),
                                                  position = (x_pos, y_pos),
                                                  value = True)
            extent_width = max(self.user_checkboxes[user].size[0], extent_width)
            y_pos += y_spacing

        # Get users that didn't appear in the last partition, if @initial
        if initial:
            self.cur.execute("SELECT user, userid FROM users")
            for user, userid in self.cur.fetchall():
                if user in self.user_checkboxes:
                    continue
                self.user_checkboxes[user] = CheckBox(user.replace('_', '_ ') + " (0)",
                                                      position = (x_pos, y_pos),
                                                      value = True)
                extent_width = max(self.user_checkboxes[user].size[0], extent_width)
                y_pos += y_spacing

        # Add the user checkboxes to a ScrollableView:
        self.user_panel = ScrollableView(size = (size_width, 150),
                                         extent = (extent_width,
                                                   max(150, y_pos)),
                                         scrolling = 'v' if extent_width <= size_width else 'hv')
        for cbox in self.user_checkboxes.values():
            self.user_panel.add(cbox)
        # Add the panel to the window
        self.window.place(self.user_panel, top = top,
                          left = self.query_type_panel + horiz_sp)

        # Create server filter checkboxes
        print_and_execute("""SELECT serverid, server, count
                             FROM (SELECT serverid, COUNT(*) AS count
                                   FROM {0} GROUP BY serverid
                                  ) as sth
                               NATURAL JOIN servers
                             ORDER BY count DESC
                         """.format(table_to_use), self.cur)
        serverlist = [x for x in self.cur.fetchall()]

        x_pos = 0
        y_pos = 0
        y_spacing = 20
        self.server_checkboxes = {}
        size_width = 300
        extent_width = size_width
        for serverid, server, count in serverlist:
            self.server_checkboxes[server] = CheckBox("{0} ({1})".format(server, count),
                                                      position = (x_pos, y_pos),
                                                      value = True)
            extent_width = max(self.server_checkboxes[server].size[0], extent_width)
            y_pos += y_spacing

        if initial:
            self.cur.execute("SELECT server FROM servers")
            for server, in self.cur.fetchall():
                if server in self.server_checkboxes:
                    continue
                self.server_checkboxes[server] = CheckBox(server.replace('_', '_ ') + " (0)",
                                                          position = (x_pos, y_pos),
                                                          value = True)
                extent_width = max(self.server_checkboxes[server].size[0], extent_width)
                y_pos += y_spacing

        # Add the server checkboxes to a ScrollableView
        self.server_panel = ScrollableView(size = (size_width, 150),
                                           extent = (extent_width,
                                                     max(150, y_pos)),
                                           scrolling = 'v' if extent_width <= size_width else 'hv')
        for cbox in self.server_checkboxes.values():
            self.server_panel.add(cbox)
        # Add the server panel to the window
        self.window.place(self.server_panel, top = top,
                          left=self.user_panel + 10)


    def get_new_filter(self):
        """
        Set self.fil to a new Filter reflecting the current status of the
        GUI elements
        """

        # Get the status of GUI elements
        # TODO: support for one date field but not the other
        # (should be done mostly in Filter class)
        if self.begin_date_field.text \
           and self.begin_date_field.text != DEFAULT_BEGIN_DATE_TEXT \
           and self.end_date_field.text \
           and self.end_date_field.text != DEFAULT_END_DATE_TEXT:
            daterange = (datetime.strptime(self.begin_date_field.text,
                                           DATEFORMAT),
                         datetime.strptime(self.end_date_field.text,
                                           DATEFORMAT))
        else:
            daterange = None

        # User
        user = [self.userids[u] for u, cb in self.user_checkboxes.iteritems() \
                if cb.value]
        if len(user) == len(self.user_checkboxes): #all users selected
            user = None

        # Server
        server = [self.serverids[s] for s, cb in self.server_checkboxes.iteritems() \
                  if cb.value]
        if len(server) == len(self.server_checkboxes):
            server = None

        # Search String List
        search_string = SearchStringList(self.any_all_radiogroup.value)
        search_string.extend([fld.text for fld in self.search_string_fields \
                              if fld.text and not fld.text.startswith('Query Search String ')])

        # Query types
        query_type = [qtype for qtype, cb in self.query_type_checkboxes.iteritems() if cb.value]
        query_type = clean_list(query_type)
        if not query_type or len(query_type) == len(querytypes):
            #all types selected
            query_type = None

        # Create the filter object
        self.fil = Filter(daterange = daterange,
                          user = user,
                          server = server,
                          search_string = search_string,
                          query_type = query_type,
                          negate = self.negate.value)


    def refresh(self):
        """
        Regenerate the graphs/top query lists without changing the table that
        the tool pulls from
        """
        # Get the status of GUI elements
        self.get_new_filter()

        # Don't repeat the query if self.filter hasn't changed since the last
        # update
        if self.fil != self.last_used_fil:
            self.create_new_temp_table()
            self.create_new_graphs_and_topqueries()
        elif self.last_grouped_by != self.time_division_radiogroup.value:
            self.create_new_graphs_and_topqueries()
            

    def create_new_temp_table(self):
        # Create a temp table
        lasttable = self.current_table_name()
        nexttable = self.next_table_name()

        # Create main table
        self.cur.execute("DROP TABLE IF EXISTS {0}".format(nexttable))
        print_and_execute("CREATE TEMPORARY TABLE {0} AS {1}".format(nexttable,
                                                                     self.fil.sql(lasttable)),
                          self.cur)
        print_and_execute("ALTER TABLE {0} ADD INDEX (userid)".format(nexttable), self.cur)
        print_and_execute("ALTER TABLE {0} ADD INDEX (serverid)".format(nexttable), self.cur)

        self.last_used_fil = self.fil

    def create_new_graphs_and_topqueries(self):
        # Get profiles of the created table
        nexttable = self.next_table_name()
        
        # TODO: support for numtop?
        profiles = query_profile(nexttable,
                                 config.get("numtop") or 200, #numtop
                                 self.time_division_radiogroup.value,
                                 self.cur)
        peruser_divided, peruser_alltime, full_divided, full_alltime, full_topqueries, peruser_topqueries = profiles

        # Remove previous .dat, .gnu, .png files and run the gnuplot scripts
        os.system("ls *.png | fgrep -v dummy | xargs rm")
        os.system("rm *.{gnu,dat}")
        gnuplot(profiles, time_axis_label=self.time_division_radiogroup.value)
        os.system("for x in *.gnu; do gnuplot $x; done")

        # Load the new image lists
        self.full_ = [Image(file=x) for x in glob('full_*.png')]
        self.peruser_alltime_ = [Image(file=x) for x in \
                                 glob('peruser_alltime_*.png')]
        self.peruser_divided_ = [Image(file=x) for x in \
                                 glob('peruser_divided_*.png') if '_total_' not in x]
        self.peruser_divided_total_ = [Image(file=x) for x in \
                                       glob('peruser_divided_total_*.png')]

        # Set self.image.images = whatever's selected in the radio
        # (we got new lists)
        self.change_images()

        # Generate the new topquery panel text
        self.topqueries.new_profiles(full_topqueries, peruser_topqueries)

        self.last_grouped_by = self.time_division_radiogroup.value


    def update(self):
        """
        Regenerate the graphs/top query lists, then change the table that the
        tool pulls from to the newly generated table. Update the lists of
        checkboxes.
        """

        self.refresh()

        if self.current_table_suffix:
            self.current_table_suffix += 1
        else:
            self.current_table_suffix = 1
        
        # update lists of checkboxes
        self.create_checkbox_lists()
        
        # reset status of GUI elements that weren't just recreated
        # self.begin_date_field.text = DEFAULT_BEGIN_DATE_TEXT
        # self.end_date_field.text = DEFAULT_END_DATE_TEXT
        # for cbox in self.query_type_checkboxes.values():
        #     cbox.value = True
        # for i, fld in enumerate(self.search_string_fields):
        #     fld.text = "Query Search String {0}".format(i + 1)


    def change_images(self):
        string = self.display_select_radiogroup.value
        if string == 'all_users':
            self.image.images = self.full_
        elif string == 'peruser_querytype':
            self.image.images = self.peruser_alltime_
        elif string == 'peruser_time':
            self.image.images = self.peruser_divided_total_
        elif string == 'peruser_querytype_time':
            self.image.images = self.peruser_divided_
        else:
            print >>sys.stderr, "Unrecognized display_select_radiogroup value %s" % string
        
        if not self.image.images:
            print >>sys.stderr, "image list assigned to self.image.images is None, using dummy"
            self.image.images = GraphView.DUMMY_IMLIST
        self.image.im_num = 0
        self.image.invalidate()

    def current_table_name(self):
        """
        Return the name of the table we are currently pulling from
        """
        if self.current_table_suffix:
            return "analysis_tool_temp" + str(self.current_table_suffix)
        return 'unified'


    def next_table_name(self):
        """
        Return the name of the table we should insert into
        """
        if self.current_table_suffix:
            return "analysis_tool_temp" + str(self.current_table_suffix + 1)
        else:
            return "analysis_tool_temp1"
        

    def select_all(self, what):
        """
        Set the value property of all checkboxes in the list to True

        @what must be one of 'user' or 'server'
        """
        if what == 'user':
            cboxes = self.user_checkboxes.values()
        elif what == 'server':
            cboxes = self.server_checkboxes.values()
        elif what == 'query_type':
            cboxes = self.query_type_checkboxes.values()
        else:
            print >>sys.stderr, "unrecognized thing to select all: %s" % what
            return

        for cbox in cboxes:
            cbox.value = True

    def deselect_all(self, what):
        """
        Set the value property of all checkboxes in the list to False

        @what must be one of 'user' or 'server'
        """
        if what == 'user':
            cboxes = self.user_checkboxes.values()
        elif what == 'server':
            cboxes = self.server_checkboxes.values()
        elif what == 'query_type':
            cboxes = self.query_type_checkboxes.values()
        else:
            print >>sys.stderr, "unrecognized thing to deselect all: %s" % what
            return

        for cbox in cboxes:
            cbox.value = False

    def invert_all(self, what):
        """
        Set the value property of all checkboxes in the list to its inverse

        @what must be one of 'user' or 'server'
        """
        if what == 'user':
            cboxes = self.user_checkboxes.values()
        elif what == 'server':
            cboxes = self.server_checkboxes.values()
        elif what == 'query_type':
            cboxes = self.query_type_checkboxes.values()
        else:
            print >>sys.stderr, "unrecognized thing to select all: %s" % what
            return

        for cbox in cboxes:
            cbox.value = not cbox.value


    def enable_all(self, what):
        """
        Enable all elements in the list
        
        @what must be one of 'user' or 'server' and the relevant
        checkboxes will be enabled
        """
        if what == 'user':
            elements = self.user_checkboxes.values()
        elif what == 'server':
            elements = self.server_checkboxes.values()
        elif what == 'query_type':
            elements = self.query_type_checkboxes.values()
        else:
            print >>sys.stderr, "unrecognized thing to enable all: %s" % what
            return

        for elem in elements:
            elem.enabled = True


    def disable_all(self, what):
        """
        Disable all elements inthe list

        @what must be one of 'user' or 'server' and the relevant
        checkboxes will be disabled
        """
        if what == 'user':
            elements = self.user_checkboxes.values()
        elif what == 'server':
            elements = self.server_checkboxes.values()
        elif what == 'query_type':
            elements = self.query_type_checkboxes.values()
        else:
            print >>sys.stderr, "unrecognized thing to disable all: %s" % what
            return

        for elem in elements:
            elem.enabled = False

    def select_all_matching(self, where):
        if where == 'user':
            elements = self.user_checkboxes
            search_string = self.user_search_string.text
        elif where == 'server':
            elements = self.server_checkboxes
            search_string = self.server_search_string.text
        else:
            print >>sys.stderr, "unrecognized thing select all matching: %s" % where
            return

        for user, cbox in elements.iteritems():
            if search_string in user:
                cbox.value = True
            else:
                cbox.value = False
            

    def change_topquery_ptr(self, how_much):
        """
        Changes the variable indicating which topquery view is to be selected
        And then updates self.topqueries.text
        """
        self.topquery_ptr += how_much
        self.topqueries.text = self.topquery_texts[self.topquery_ptr % len(self.topquery_texts)]


    def open_app(self):
        # Everything done in __init__()
        pass


if __name__ == '__main__':
    x = Tool() #two lines for easier debugging with "python -i tool.py"
    x.run()
