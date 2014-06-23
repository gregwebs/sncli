#!/usr/bin/env python2

import os, sys, signal, time, copy, logging, json, urwid, ConfigParser, utils
from simplenote import Simplenote
from notes_db import NotesDB, SyncError, ReadError, WriteError
from logging.handlers import RotatingFileHandler

class Config:

    def __init__(self):
        self.home = os.path.abspath(os.path.expanduser('~'))
        defaults = {
                    'sn_username'    : 'edavis@insanum.com',
                    'sn_password'    : 'biteme55',
                    'db_path'        : os.path.join(self.home, '.sncli'),
                    'search_mode'    : 'gstyle',
                    'search_tags'    : '1',
                    'sort_mode'      : '1',
                    'pinned_ontop'   : '1',
                    'tabstop'        : '4',
                    'help'           : 'h',
                    'quit'           : 'q',
                    'down'           : 'j',
                    'up'             : 'k',
                    'page_down'      : ' ',
                    'page_up'        : 'b',
                    'half_page_down' : 'ctrl d',
                    'half_page_up'   : 'ctrl u',
                    'view_note'      : 'enter'
                   }

        cp = ConfigParser.SafeConfigParser(defaults)
        self.configs_read = cp.read([os.path.join(self.home, '.snclirc')])

        cfg_sec = 'sncli'

        if not cp.has_section(cfg_sec):
            cp.add_section(cfg_sec)
            self.ok = False
        else:
            self.ok = True

        self.sn_username  = cp.get(cfg_sec, 'sn_username', raw=True)
        self.sn_password  = cp.get(cfg_sec, 'sn_password', raw=True)
        self.db_path      = cp.get(cfg_sec, 'db_path')
        self.search_mode  = cp.get(cfg_sec, 'search_mode')
        self.search_tags  = cp.getint(cfg_sec, 'search_tags')
        self.sort_mode    = cp.getint(cfg_sec, 'sort_mode')
        self.pinned_ontop = cp.getint(cfg_sec, 'pinned_ontop')
        self.tabstop      = cp.getint(cfg_sec, 'tabstop')

        self.keybinds = \
            {
              'help'           : [ cp.get(cfg_sec, 'help'),           'Help' ],
              'quit'           : [ cp.get(cfg_sec, 'quit'),           'Quit' ],
              'down'           : [ cp.get(cfg_sec, 'down'),           'Scroll down one line' ],
              'up'             : [ cp.get(cfg_sec, 'up'),             'Scroll up one line' ],
              'page_down'      : [ cp.get(cfg_sec, 'page_down'),      'Page down' ],
              'page_up'        : [ cp.get(cfg_sec, 'page_up'),        'Page up' ],
              'half_page_down' : [ cp.get(cfg_sec, 'half_page_down'), 'Half page down' ],
              'half_page_up'   : [ cp.get(cfg_sec, 'half_page_up'),   'Half page up' ],
              'view_note'      : [ cp.get(cfg_sec, 'view_note'),      'View note' ]
            }

class sncli:

    def __init__(self):
        self.config = Config()

        if not os.path.exists(self.config.db_path):
            os.mkdir(self.config.db_path)

        # configure the logging module
        self.logfile = os.path.join(self.config.db_path, 'sncli.log')
        self.loghandler = RotatingFileHandler(self.logfile, maxBytes=100000, backupCount=1)
        self.loghandler.setLevel(logging.DEBUG)
        self.loghandler.setFormatter(logging.Formatter(fmt='%(asctime)s [%(levelname)s] %(message)s'))
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(self.loghandler)
        logging.debug('sncli logging initialized')

        try:
            self.ndb = NotesDB(self.config)
        except Exception, e:
            print e
            exit(1)

        self.last_view = []

        # XXX
        #self.all_notes, match_regex, self.all_notes_cnt = self.ndb.filter_notes()
        #return

        self.ndb.add_observer('synced:note', self.observer_notes_db_synced_note)
        self.ndb.add_observer('change:note-status', self.observer_notes_db_change_note_status)
        self.ndb.add_observer('progress:sync_full', self.observer_notes_db_sync_full)
        self.sync_full()

        self.all_notes, match_regex, self.all_notes_cnt = self.ndb.filter_notes()

    def do_it(self):

        def list_get_note_titles():
            note_titles = []
            for n in self.all_notes:
                note_titles.append(urwid.Text(('note_title', utils.get_note_title(n.note))))
            return note_titles

        def list_get_note_content(index):
            note_contents = []
            for l in self.all_notes[index].note['content'].split('\n'):
                note_contents.append(urwid.Text(('note_view',
                                                 l.replace('\t', ' ' * self.config.tabstop))))
            return note_contents

        def list_get_note_json(index):
            return self.all_notes[index].note

        def get_keybinds():
            return self.config.keybinds

        def push_last_view(view):
            self.last_view.append(view)

        def pop_last_view():
            return self.last_view.pop()

        class NoteTitles(urwid.ListBox):
            def __init__(self):
                body = urwid.SimpleFocusListWalker( list_get_note_titles() )
                super(NoteTitles, self).__init__(body)
                self.keybinds = get_keybinds()
                self.focus.set_text(('note_title_focus', self.focus.text))

            def keypress(self, size, key):
                key = super(NoteTitles, self).keypress(size, key)

                if key == self.keybinds['quit'][0]:
                    raise urwid.ExitMainLoop()

                if key == self.keybinds['help'][0]:
                    push_last_view(self)
                    sncli_loop.widget = Help(self)

                elif key == self.keybinds['down'][0]:
                    last = len(self.body.positions())
                    if self.focus_position == (last - 1):
                        return
                    self.focus.set_text(('note_title', self.focus.text))
                    self.focus_position = self.focus_position + 1
                    self.focus.set_text(('note_title_focus', self.focus.text))

                elif key == self.keybinds['up'][0]:
                    if self.focus_position == 0:
                        return
                    self.focus.set_text(('note_title', self.focus.text))
                    self.focus_position = self.focus_position - 1
                    self.focus.set_text(('note_title_focus', self.focus.text))

                elif key == self.keybinds['page_down'][0]:
                    last = len(self.body.positions())
                    next_focus = self.focus_position + size[1]
                    if next_focus >= last:
                        next_focus = last - 1
                    self.focus.set_text(('note_title', self.focus.text))
                    self.change_focus(size, next_focus,
                                      offset_inset=0,
                                      coming_from='above')
                    self.focus.set_text(('note_title_focus', self.focus.text))

                elif key == self.keybinds['page_up'][0]:
                    if 'bottom' in self.ends_visible(size):
                        last = len(self.body.positions())
                        next_focus = last - size[1] - size[1]
                    else:
                        next_focus = self.focus_position - size[1]
                    if next_focus < 0:
                        next_focus = 0
                    self.focus.set_text(('note_title', self.focus.text))
                    self.change_focus(size, next_focus,
                                      offset_inset=0,
                                      coming_from='below')
                    self.focus.set_text(('note_title_focus', self.focus.text))

                elif key == self.keybinds['half_page_down'][0]:
                    last = len(self.body.positions())
                    next_focus = self.focus_position + (size[1] / 2)
                    if next_focus >= last:
                        next_focus = last - 1
                    self.focus.set_text(('note_title', self.focus.text))
                    self.change_focus(size, next_focus,
                                      offset_inset=0,
                                      coming_from='above')
                    self.focus.set_text(('note_title_focus', self.focus.text))

                elif key == self.keybinds['half_page_up'][0]:
                    if 'bottom' in self.ends_visible(size):
                        last = len(self.body.positions())
                        next_focus = last - size[1] - (size[1] / 2)
                    else:
                        next_focus = self.focus_position - (size[1] / 2)
                    if next_focus < 0:
                        next_focus = 0
                    self.focus.set_text(('note_title', self.focus.text))
                    self.change_focus(size, next_focus,
                                      offset_inset=0,
                                      coming_from='below')
                    self.focus.set_text(('note_title_focus', self.focus.text))

                elif key == self.keybinds['view_note'][0]:
                    push_last_view(self)
                    sncli_loop.widget = NoteContent(self.focus_position)

        class NoteContent(urwid.ListBox):
            def __init__(self, nl_focus_index):
                body = urwid.SimpleFocusListWalker(list_get_note_content(nl_focus_index))
                self.keybinds = get_keybinds()
                self.note = list_get_note_json(nl_focus_index)
                super(NoteContent, self).__init__(body)

            def keypress(self, size, key):
                key = super(NoteContent, self).keypress(size, key)

                if key == self.keybinds['quit'][0]:
                    sncli_loop.widget = pop_last_view()

                if key == self.keybinds['help'][0]:
                    push_last_view(self)
                    sncli_loop.widget = Help(self)

                elif key == self.keybinds['down'][0]:
                    key = super(NoteContent, self).keypress(size, 'down')

                elif key == self.keybinds['up'][0]:
                    key = super(NoteContent, self).keypress(size, 'up')

                elif key == self.keybinds['page_down'][0]:
                    key = super(NoteContent, self).keypress(size, 'page down')

                elif key == self.keybinds['page_up'][0]:
                    key = super(NoteContent, self).keypress(size, 'page up')

                elif key == self.keybinds['half_page_down'][0]:
                    last = len(self.body.positions())
                    next_focus = self.focus_position + (size[1] / 2)
                    if next_focus >= last:
                        next_focus = last - 1
                    self.change_focus(size, next_focus,
                                      offset_inset=0,
                                      coming_from='above')

                elif key == self.keybinds['half_page_up'][0]:
                    if 'bottom' in self.ends_visible(size):
                        last = len(self.body.positions())
                        next_focus = last - size[1] - (size[1] / 2)
                    else:
                        next_focus = self.focus_position - (size[1] / 2)
                    if next_focus < 0:
                        next_focus = 0
                    self.change_focus(size, next_focus,
                                      offset_inset=0,
                                      coming_from='below')

        class Help(urwid.ListBox):
            def __init__(self, last_view):
                self.keybinds = get_keybinds()

                col1_txt_common = \
                  [
                    urwid.Text(('help_col1',
                                "'" + self.keybinds['quit'][0] + "'"),
                               align='right'),
                    urwid.Text(('help_col1',
                                "'" + self.keybinds['down'][0] + "'"),
                               align='right'),
                    urwid.Text(('help_col1',
                                "'" + self.keybinds['up'][0] + "'"),
                                align='right'),
                    urwid.Text(('help_col1',
                                "'" + self.keybinds['page_down'][0] + "'"),
                               align='right'),
                    urwid.Text(('help_col1',
                                "'" + self.keybinds['page_up'][0] + "'"),
                               align='right')
                  ]

                col1_txt_common2 = \
                  [
                    urwid.Text(('help_col1',
                                "'" + self.keybinds['half_page_down'][0] + "'"),
                               align='right'),
                    urwid.Text(('help_col1',
                                "'" + self.keybinds['half_page_up'][0] + "'"),
                               align='right'),
                    urwid.Text(('help_col1',
                                "'" + self.keybinds['help'][0] + "'"),
                               align='right')
                  ]

                col2_txt_common = \
                  [
                    urwid.Text(('help_col2', u'quit')),
                    urwid.Text(('help_col2', u'down')),
                    urwid.Text(('help_col2', u'up')),
                    urwid.Text(('help_col2', u'page_down')),
                    urwid.Text(('help_col2', u'page_up'))
                  ]

                col2_txt_common2 = \
                  [
                    urwid.Text(('help_col2', u'half_page_down')),
                    urwid.Text(('help_col2', u'half_page_up')),
                    urwid.Text(('help_col2', u'help'))
                  ]

                col3_txt_common = \
                  [
                    urwid.Text(('help_col3', self.keybinds['quit'][1])),
                    urwid.Text(('help_col3', self.keybinds['down'][1])),
                    urwid.Text(('help_col3', self.keybinds['up'][1])),
                    urwid.Text(('help_col3', self.keybinds['page_down'][1])),
                    urwid.Text(('help_col3', self.keybinds['page_up'][1]))
                  ]

                col3_txt_common2 = \
                  [
                    urwid.Text(('help_col3', self.keybinds['half_page_down'][1])),
                    urwid.Text(('help_col3', self.keybinds['half_page_up'][1])),
                    urwid.Text(('help_col3', self.keybinds['help'][1]))
                  ]

                space = urwid.Text(('help_hdr', u""))

                nl_hdr = urwid.Text(('help_hdr', u"Note List"))

                nl_col1_txt = copy.copy(col1_txt_common)
                nl_col1_txt.extend(copy.copy(col1_txt_common2))
                nl_col1_txt.append(urwid.Text(('help_col1',
                                               "'" + self.keybinds['view_note'][0] + "'"),
                                              align='right'))

                nl_col2_txt = copy.copy(col2_txt_common)
                nl_col2_txt.extend(copy.copy(col2_txt_common2))
                nl_col2_txt.append(urwid.Text(('help_col2', u'view_note')))

                nl_col3_txt = copy.copy(col3_txt_common)
                nl_col3_txt.extend(copy.copy(col3_txt_common2))
                nl_col3_txt.append(urwid.Text(('help_col3', self.keybinds['view_note'][1])))

                nl_col1_pile = urwid.Pile(nl_col1_txt) 
                nl_col2_pile = urwid.Pile(nl_col2_txt) 
                nl_col3_pile = urwid.Pile(nl_col3_txt) 

                nl_cols = urwid.Columns([ ('fixed', 16, nl_col1_pile),
                                          ('fixed', 16, nl_col2_pile),
                                          ('fixed', 32, nl_col3_pile) ],
                                        3, focus_column=1)

                nc_hdr = urwid.Text(('help_hdr', u"Note Content"))

                nc_col1_txt = copy.copy(col1_txt_common)
                nc_col1_txt.extend(copy.copy(col1_txt_common2))

                nc_col2_txt = copy.copy(col2_txt_common)
                nc_col2_txt.extend(copy.copy(col2_txt_common2))

                nc_col3_txt = copy.copy(col3_txt_common)
                nc_col3_txt.extend(copy.copy(col3_txt_common2))

                nc_col1_pile = urwid.Pile(nc_col1_txt) 
                nc_col2_pile = urwid.Pile(nc_col2_txt) 
                nc_col3_pile = urwid.Pile(nc_col3_txt) 

                nc_cols = urwid.Columns([ ('fixed', 16, nc_col1_pile),
                                          ('fixed', 16, nc_col2_pile),
                                          ('fixed', 32, nc_col3_pile) ],
                                        3, focus_column=1)

                help_hdr = urwid.Text(('help_hdr', u"Help"))

                help_col1_txt = copy.copy(col1_txt_common)
                help_col2_txt = copy.copy(col2_txt_common)
                help_col3_txt = copy.copy(col3_txt_common)

                help_col1_pile = urwid.Pile(help_col1_txt) 
                help_col2_pile = urwid.Pile(help_col2_txt) 
                help_col3_pile = urwid.Pile(help_col3_txt) 

                help_cols = urwid.Columns([ ('fixed', 16, help_col1_pile),
                                            ('fixed', 16, help_col2_pile),
                                            ('fixed', 32, help_col3_pile) ],
                                          3, focus_column=1)

                help_pile = urwid.Pile( [ space, nl_hdr,   nl_cols,
                                          space, nc_hdr,   nc_cols,
                                          space, help_hdr, help_cols ] )

                body = urwid.SimpleFocusListWalker([help_pile])
                super(Help, self).__init__(body)

            def keypress(self, size, key):
                key = super(Help, self).keypress(size, key)

                if key == self.keybinds['quit'][0]:
                    sncli_loop.widget = pop_last_view()

                elif key == self.keybinds['down'][0]:
                    key = super(Help, self).keypress(size, 'down')

                elif key == self.keybinds['up'][0]:
                    key = super(Help, self).keypress(size, 'up')

                elif key == self.keybinds['page_down'][0]:
                    key = super(Help, self).keypress(size, 'page down')

                elif key == self.keybinds['page_up'][0]:
                    key = super(Help, self).keypress(size, 'page up')

        palette = [
                    ('default',          'default',    'default'),
                    ('note_title_focus', 'black',      'dark red'),
                    ('note_title',       'dark red',   'default'),
                    ('note_view',        'default',    'default'),
                    ('help_hdr',         'dark blue',  'default'),
                    ('help_col1',        'default',    'default'),
                    ('help_col2',        'dark green', 'default'),
                    ('help_col3',        'default',    'default'),
                  ]

        sncli_loop = urwid.MainLoop(NoteTitles(),
                                    palette,
                                    handle_mouse=False)
        sncli_loop.run()

    def sync_full(self):
        try:
            sync_from_server_errors = self.ndb.sync_full()
        except Exception, e:
            print e
            exit(1)
        else:
            if sync_from_server_errors > 0:
                print('Error syncing %d notes from server. Please check sncli.log for details.' % (sync_from_server_errors))

    def set_note_status(self, msg):
        print(msg)

    def observer_notes_db_change_note_status(self, ndb, evt_type, evt):
        skey = self.get_selected_note_key()
        if skey == evt.key:
            # XXX
            #self.view.set_note_status(self.ndb.get_note_status(skey))
            self.set_note_status(self.ndb.get_note_status(skey))

    def set_status_text(self, msg):
        print(msg)

    def observer_notes_db_sync_full(self, ndb, evt_type, evt):
        logging.debug(evt.msg)
        # XXX
        #self.view.set_status_text(evt.msg)
        self.set_status_text(evt.msg)

    def observer_notes_db_synced_note(self, ndb, evt_type, evt):
        """This observer gets called only when a note returns from
        a sync that's more recent than our most recent mod to that note.
        """

        selected_note_o = self.notes_list_model.list[self.selected_note_idx]
        print "observer_notes_db_synced_note: " + evt.msg

        # if the note synced back matches our currently selected note,
        # we overwrite.

        # XXX
        #if selected_note_o.key == evt.lkey:
        #    if selected_note_o.note['content'] != evt.old_note['content']:
        #        self.view.mute_note_data_changes()
        #        # in this case, we want to keep the user's undo buffer so that they
        #        # can undo synced back changes if they would want to.
        #        self.view.set_note_data(selected_note_o.note, reset_undo=False)
        #        self.view.unmute_note_data_changes()


def SIGINT_handler(signum, frame):
    print('Signal caught, bye!')
    sys.exit(1)

signal.signal(signal.SIGINT, SIGINT_handler)

def main():
    sncli().do_it()

if __name__ == '__main__':
    main()

