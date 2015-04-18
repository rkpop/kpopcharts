#!/usr/bin/env python3
#
# Copyright (C) 2015 by NewbieSone <newbiesone@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# stdlib
import configparser
import datetime
import re
import sys
import smtplib
import traceback

# our stuff
from kpopcharts import kpopcharts

# third-party
import praw

def error(text):
    message = 'From: KPop Charts Bot <{0}>\n'.format(config.get('sidebarbot', 'error_sender_address'))
    message += 'To: {0} <{1}>\n'.format(config.get('sidebarbot', 'error_recipient_name'),
        config.get('sidebarbot', 'error_recipient_address'))
    message += 'Subject: Error uploading sidebar charts!\n'
    message += text
    message += '\n'

    try:
        smtpObj = smtplib.SMTP('localhost')
        smtpObj.sendmail(config.get('sidebarbot', 'error_sender_address'),
            [config.get('sidebarbot', 'error_recipient_address'),], message)
    except (smtplib.SMTPException, ConnectionRefusedError):
        pass

    sys.exit()

if __name__ == '__main__':
    config = configparser.RawConfigParser()
    config.read('config.ini')

    version = '0.1'
    user_agent = 'linux:org.rkpop.sidebarcharts:v{0}'.format(version)

    header = ' | Realtime iChart ([Source](http://ichart.instiz.net/))'
    replace_anchors = ['CHARTS_HOOK', header]

    try:
        charts = list()
        charts.append(kpopcharts.IChart())
        charts.append(kpopcharts.MelonChart())
        charts.append(kpopcharts.GaonChart())

        normalized = kpopcharts.NormalizedChartList(*charts)

        sidebar = kpopcharts.RedditChartsTable(normalized, columns=1, limit=10)
        sidebar._header = header
        sidebar = str(sidebar)

        # FIXME TODO: Fix messy date mangling.
        sidebar += '\n^Every ^30m ^• ^Last: ^{0} ^UTC\n\n'.format(str(datetime.datetime.utcnow()).split('.', 1)[0].rsplit(':', 1)[0].replace(' ',' ^'))

        reddit = praw.Reddit(user_agent=user_agent, decode_html_entities='yes')

        reddit.login(config.get('sidebarbot', 'username'), config.get('sidebarbot', 'password'))

        sub = reddit.get_subreddit(config.get('sidebarbot', 'subreddit'))

        settings = sub.get_settings()

        replaced = False

        for anchor in replace_anchors:
            escaped = re.escape(anchor)
            pattern = re.compile('{0}.*?\n\n'.format(escaped), flags=re.DOTALL)
            results = pattern.search(settings['description'])

            if results is not None:
                sidebar = pattern.sub(sidebar, settings['description'], 1)
                replaced = True
                break

        if len(sidebar) > 5120:
            error('Sidebar too long!')

        if replaced:
            update = dict(description=sidebar)
            settings.update(update)
            del settings['subreddit_id']
            sub.set_settings(**settings)
        else:
            error("No anchors found in sidebar.")
    except Exception:
        error(traceback.format_exc())
