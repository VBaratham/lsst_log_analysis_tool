from GUI import View, ScrollableView, TextField, Label, \
Application, Window, Font, Image

import GUI.Geometry as geo



class GraphView(View):
    """
    Displays an image, and cycles to the next .png file in the list when
    clicked
    """
    DUMMY_IMLIST = [Image(file = "dummy.png"),]

    def __init__(self, size, **kwargs):
        View.__init__(self, **kwargs)
        self.images = GraphView.DUMMY_IMLIST
        self.im_num = 0
        self.size = size

    def draw(self, c, r):
        if self.images == None:
            self.images = GraphView.DUMMY_IMLIST
        img = self.images[self.im_num % len(self.images)]
        img.draw(c, img.bounds, (0, 0) + self.size)

    def mouse_up(self, event):
        self.im_num += 1
        self.invalidate()


class ResponsiveTextField(TextField):
    """
    A TextField that runs a function when it goes empty and when updated
    """
    def __init__(self, emptyaction=None, action=None, **kwargs):
        if isinstance(emptyaction, tuple):
            self.emptyaction = emptyaction[0]
            self.emptyactionargs = emptyaction[1:]
        else:
            self.emptyaction = emptyaction
            self.emptyactionargs = []

        if isinstance(action, tuple):
            self.action = action[0]
            self.actionargs = action[1:]
        else:
            self.action = action
            self.actionargs = []

        TextField.__init__(self, **kwargs)

    def key_down(self, event):
        TextField.key_down(self, event)

        if not self.text:
            if self.emptyaction:
                self.emptyaction(*self.emptyactionargs)
        else:
            if self.action:
                self.action(*self.actionargs)



class TopqueryLabel(Label):
    
    VALUES_HEADER = ['count |    values', '-' * 90]

    def __init__(self, query, values, **kwargs):
        Label.__init__(self, **kwargs)
        self.query = query
        self.values = values
        self.expanded = False
        self.text = query
        self.font = Font("Courier", 13)
        self.resize()

    def resize(self):
        self.size = (self.font.width(self.text),
                     self.font.line_height * (self.text.count("\n") + 1))

    def mouse_down(self, event):
        self.expanded = not self.expanded
        if self.expanded and self.values:
            self.text = '\n\t'.join([self.query] +
                                    TopqueryLabel.VALUES_HEADER +
                                    self.values)
        else:
            self.text = self.query
        self.resize()


class TopqueryPanel(ScrollableView):

    # TODO: When values are collapsed, scroll back up to the query they were from

    def __init__(self, **kwargs):
        ScrollableView.__init__(self, **kwargs)
        
        # Each panel is a list of TopqueryLabels
        self.panels = []
        self.currently_displayed = 0
        self.font = Font("Courier", 13)

    def new_profiles(self, ftq, ptq):
        fullpanel = [TopqueryLabel(self.get_header("ALL USERS"), [])]
        maxlen = len(str(max(sum(ct for vals, ct in valcts)
                             for query, valcts in ftq)))
        maxlen = max(5, maxlen)
        for query, valcts in ftq:
            # TODO: This is stupid code, since it calculates sums twice
            # (from maxlen above)
            count = sum(ct for vals, ct in valcts)
            maxvallen = len(str(max(ct for val, ct in valcts)))
            printed_query = "{1: >{0}} | {2}".format(maxlen, count, query)
            these_values = ["{1: >{0}}    |    {2}".format(maxvallen, ct, val)
                            for val, ct in valcts] if valcts[0][0] else []
            fullpanel.append(TopqueryLabel(printed_query, these_values))

        self.panels = [fullpanel]


        # Peruser
        for user, profile in ptq:
            this_panel = [TopqueryLabel(self.get_header(user), [])]
            maxlen = len(str(max(sum(ct for vals, ct in valcts)
                                 for query, valcts in profile)))
            maxlen = max(5, maxlen)
            for query, valcts in profile:
                count = sum(ct for vals, ct in valcts)
                maxvallen = len(str(max(ct for val, ct in valcts)))
                printed_query = "{1: >{0}} | {2}".format(maxlen, count, query)
                these_values = ["{1: >{0}}    |    {2}".format(maxvallen,
                                                               ct, val)
                                for val, ct in valcts] if valcts[0][0] else []
                this_panel.append(TopqueryLabel(printed_query, these_values))
            self.panels.append(this_panel)


    def draw(self, c, r):
        # Remove all labels from this component
        for component in self.contents:
            if component not in self.panels[self.currently_displayed %
                                            len(self.panels)]:
                self.remove(component)
        
        # Place labels inside this component
        # TODO: does this double place elements?
        maxwidth = self.size[0]
        prev_comp = 0
        for label in self.panels[self.currently_displayed % len(self.panels)]:
            self.place(label, left=0, top=prev_comp)
            maxwidth = max(maxwidth, label.size[0])
            prev_comp = label

        # Set vertical extent to bottom of last query, or the size of
        # this Panel if larger
        # Set horizontal extent to the largest found
        self.extent = (maxwidth, max(prev_comp.bottom, self.size[1]))

        # Redraw the component
        self.invalidate()

    def next(self):
        self.currently_displayed += 1
        self.invalidate()

    def prev(self):
        self.currently_displayed -= 1
        self.invalidate()

    def mouse_down(self, event):
        for comp in self.contents:
            if geo.pt_in_rect(event.position, comp.bounds):
                comp.mouse_down(event)
                return

    def get_header(self, user):
        return "TOP QUERIES FOR {0}\ncount | query\n".format(user) + '=' * 100


if __name__ == '__main__':
    a = Application()
    a.window = Window(size = (500, 500))
    
    testpanel = TopqueryPanel(size = (300, 300), extent = (1000, 1000))
    testpanel.panels.append([TopqueryLabel("this is the query",
                                           ["val1 || val2",
                                            "val3 || val4"],
                                           size = (300, testpanel.font.line_height))])
    testpanel.panels[0].append(TopqueryLabel("this is another query",
                                             ["val1 || val2",
                                              "val3 || val4"],
                                             size = (300, testpanel.font.line_height)))
    testpanel.panels.append([TopqueryLabel("this is another panel",
                                           ["val1 || val2",
                                            "val3 || val4"],
                                           size = (300, testpanel.font.line_height))])

    a.window.place(testpanel, left=0, top=0)
    a.window.show()
    a.run()
