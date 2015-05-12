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

# our stuff
from kpopcharts import kpopcharts
from kpopcharts import youtube

# third-party
import bottle

@bottle.route('/')
def index():
    charts = list()

    with youtube.Session(config.get('youtube', 'api_key')):
        charts.append(kpopcharts.IChart(chart_type=kpopcharts.ChartType.Week))

    charts.append(kpopcharts.MelonChart(chart_type=kpopcharts.ChartType.Week))
    charts.append(kpopcharts.GaonChart(chart_type=kpopcharts.ChartType.Week))
    charts.append(kpopcharts.GaonChart(chart_type=kpopcharts.ChartType.AlbumWeek))

    normalized = kpopcharts.NormalizedChartList(*charts)

    reddit = str(kpopcharts.RedditChartsTable(normalized))

    reddit += '\n\nURLs used:'

    for chart in charts:
        reddit += '\n' + chart.url

    return '<pre>{0}</pre>'.format(reddit)

if __name__ == '__main__':
    config = configparser.RawConfigParser()
    config.read('config.ini')

    bottle.run(host=config.get('weekreportapp', 'host'), port=config.getint('weekreportapp', 'port'))
