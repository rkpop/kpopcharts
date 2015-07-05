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
import abc
import collections
import datetime
import difflib
import enum
import functools
import re
import socket
import string
import urllib.parse
import urllib.request

# our stuff
from . import youtube

# third-party
import ftfy
import lxml.etree
import lxml.html

class ChartError(Exception):
    pass

class ChartBuildError(ChartError):
    pass

class ChartFetchError(ChartError):
    pass

class ChartType(enum.Enum):
    Realtime = 1
    Week = 2
    AlbumWeek = 3

# FIXME TODO: Enumify ChartEntry.change.
class ChartEntry(dict):
    def __init__(self):
        super(ChartEntry, self).__init__(rank='', artists=ArtistsList(), title='', video='', change='', change_diff=0)
        self.__dict__ = self

    @staticmethod
    def _similar(a, b):
        return (difflib.SequenceMatcher(None, str(a), str(b)).ratio() > 0.8)

# FIXME TODO: Clean up ugly bullshit magic coupling between this and
# NormalizedChartList.__normalize to hash on extracted artist but render
# from substitution cache, which __normalize also inserts into.
@functools.total_ordering
class Artist:
    def __init__(self, name):
        name = ftfy.fix_encoding(name)
        self._name = self._english_artist(name)

    _substitution_cache = dict()

    @property
    def name(self):
        if self._name in self._substitution_cache:
            return self._substitution_cache[self._name]
        else:
            return self._name

    def __str__(self):
        return self.name

    def __hash__(self):
        return self._name.__hash__()

    def __lt__(self, other):
        return self.name.__lt__(str(other))

    @staticmethod
    def _english_artist(text):
        pattern = re.compile('(.+)\((.+)\)')
        matches = pattern.search(text)

        if matches is None:
            return text
        else:
            compare = Artist._english_cmp(matches.groups()[0], matches.groups()[1])

            if compare == 0:
                return text.strip()
            else:
                if compare == 1:
                    Artist._substitution_cache[matches.groups()[1].strip()] = matches.groups()[0].strip()
                    return matches.groups()[0].strip()
                else:
                    return matches.groups()[1].strip()
                    Artist._substitution_cache[matches.groups()[0].strip()] = matches.groups()[1].strip()

    @staticmethod
    def _english_score(text):
        text = str(text)
        count = len(text)
        ascii = 0

        for char in text:
            if char in string.ascii_letters:
                ascii += 1

        if ascii == 0:
            return 0
        else:
            return float(count) / float(ascii)

    @staticmethod
    def _english_cmp(x, y):
        x_score = Artist._english_score(x)
        y_score = Artist._english_score(y)

        if x_score < y_score:
            return -1
        if x_score > y_score:
            return 1

        return 0

class ArtistsList(list):
    def __str__(self):
        return ', '.join(sorted(map(str, self)))

class ArtistsSet(set):
    def __str__(self):
        return ', '.join(sorted(map(str, self)))

class Chart(list):
    def __init__(self, chart_type=None, limit=50):
        self.chart_type = chart_type if chart_type is not None else self._default_chart_type

        if (self.chart_type not in self.supported_chart_types):
            raise ChartBuildError('Chart {0} does not support this chart type!'.format(self.name))

        self.limit = limit
        self.url = self._url_from_chart_type()

        try:
            self._fetch_chart()
        except Exception as e:
            raise ChartFetchError('Error fetching {0} chart. Try again!'.format(self.name))

    @property
    @abc.abstractmethod
    def name(self):
        pass

    @property
    @abc.abstractmethod
    def supported_chart_types(self):
        pass

    @property
    @abc.abstractmethod
    def _default_chart_type(self):
        pass

    @abc.abstractmethod
    def _url_from_chart_type(self):
        pass

    @abc.abstractmethod
    def _fetch_chart(self):
        pass

class NormalizedChartList(collections.MutableSequence):
    def __init__(self, *args):
        self.__list = list()

        if len(args):
            self.__list.extend(args)
            self.__normalize()

    def __str__(self):
        return self.__list.__str__()

    def insert(self, i, value):
        self.__list.insert(i, value)
        self.__normalize()

    def append(self, value):
        self.__list.append(value)
        self.__normalize()

    def __getitem__(self, key):
        return self.__list[key]

    def __setitem__(self, key, value):
        self.__list[key] = value
        self.__normalize()

    def __delitem__(self, key):
        self.__list.remove(key)

    def __len__(self):
        return len(self.__list)

    __english_sort_key = functools.cmp_to_key(Artist._english_cmp)

    def __normalize(self):
        normalized_titles = dict()

        for chart in self.__list:
            for entry in chart:
                entry.title = re.sub(r'\((?!Korean|Chinese|Japanese)[^)]*?\)', '',
                    entry.title, flags=re.IGNORECASE).strip()
                entry.title = re.sub(r'\((?!Korean|Chinese|Japanese)[^)]*?\)', '',
                    entry.title, flags=re.IGNORECASE).strip()

        for chart in self.__list:
            for entry in chart:
                if not entry.title in normalized_titles:
                    normalized_titles[entry.title] = set()
                    normalized_titles[entry.title].add(entry.title)

        for outer_title in normalized_titles:
            for inner_title, mapping in normalized_titles.items():
                if ChartEntry._similar(outer_title, inner_title):
                    mapping.add(outer_title)
                    normalized_titles[outer_title].add(inner_title)

        for key, value in normalized_titles.items():
            sorted_titles = sorted(sorted(value), key=self.__english_sort_key)
            normalized_titles[key] = sorted_titles[0]

        for chart in self.__list:
            for entry in chart:
                entry.title = normalized_titles[entry.title]

        normalized_artists = dict()

        for outer_chart in self.__list:
            for outer_entry in outer_chart:
                for inner_chart in self.__list:
                    for inner_entry in inner_chart:
                        if ChartEntry._similar(outer_entry.title, inner_entry.title):
                            inner_score = sum(Artist._english_score(artist) for artist in inner_entry.artists)
                            outer_score = sum(Artist._english_score(artist) for artist in outer_entry.artists)

                            if inner_score > outer_score:
                                if len(outer_entry.artists) == 1 and len(inner_entry.artists) == 1:
                                    Artist._substitution_cache[outer_entry.artists[0].name] = inner_entry.artists[0].name

                                outer_entry.artists = inner_entry.artists
                            elif outer_score > inner_score:
                                if len(outer_entry.artists) == 1 and len(inner_entry.artists) == 1:
                                    Artist._substitution_cache[inner_entry.artists[0].name] = outer_entry.artists[0].name

                                inner_entry.artists = outer_entry.artists

        for chart in self.__list:
            for entry in chart:
                for artist in entry.artists:
                    if not artist in normalized_artists:
                        normalized_artists[artist] = ArtistsSet()
                        normalized_artists[artist].add(artist)

        for outer_artist in normalized_artists:
            for inner_artist, mapping in normalized_artists.items():
                if ChartEntry._similar(outer_artist, inner_artist):
                    mapping.add(outer_artist)
                    normalized_artists[outer_artist].add(inner_artist)

        for key, value in normalized_artists.items():
            sorted_artists = sorted(value, key=self.__english_sort_key)
            normalized_artists[key] = sorted_artists[0]

        for chart in self.__list:
            for entry in chart:
                artists = ArtistsSet()

                for artist in entry.artists:
                    normalized_artist = normalized_artists[artist]
                    artists.add(Artist._substitution_cache[normalized_artist] if normalized_artist
                        in Artist._substitution_cache else normalized_artist)

                entry.artists = artists

        for chart in self.__list[1:]:
            for outer_entry in chart:
                for inner_entry in self.__list[0]:
                    if outer_entry.title == inner_entry.title:
                        outer_entry.video = inner_entry.video

class IChart(Chart):
    _cls_regex = re.compile('^ichart_score([0-9]*)_song1$')
    _artist_regex = re.compile('^ichart_score([0-9]*)_artist1$')
    _change_regex = re.compile('^ichart_score([0-9]*)_change')
    _change_classes = dict(arrow1='up', arrow2='down', arrow3='none', arrow4='new', arrow5='new')

    @property
    def name(self):
        return 'iChart'

    @property
    def supported_chart_types(self):
        return (ChartType.Realtime, ChartType.Week)

    @property
    def _default_chart_type(self):
        return ChartType.Realtime

    def _url_from_chart_type(self):
        urls = { ChartType.Realtime : 'http://www.instiz.net/iframe_ichart_score.htm',
                 ChartType.Week     : 'http://www.instiz.net/iframe_ichart_score.htm?week=1&selyear=2015&sel={0}'.format(datetime.date.today().isocalendar()[1] - 1) }

        return urls[self.chart_type]

    def _fetch_chart(self):
        req = urllib.request.Request(self.url)
        req.add_header('Referer', 'http://ichart.instiz.net/')
        page = urllib.request.urlopen(req, data=None, timeout=15)

        root = lxml.html.parse(page)

        rank = 1
        entry = None

        for element in root.iter(tag=lxml.etree.Element):
            cls = element.get('class')

            if cls is None:
                continue

            if self._change_regex.match(cls):
                entry = ChartEntry()

                entry.rank = rank

                if rank > self.limit:
                    break
                else:
                    self.append(entry)
                    rank += 1

                entry.change = self._change_classes[element[0].get('class').split()[1]]

                diff = element.text_content().strip()

                if diff:
                    entry.change_diff = diff

            if self._cls_regex.match(cls):
                title = element.text_content().strip()

                opar = title.rfind('(')
                cpar = title.rfind(')')

                if opar != -1 and cpar == -1 or cpar < opar:
                    title = title[:opar]

                entry.title = ftfy.fix_encoding(title.strip())

            if self._artist_regex.match(cls):
                for artist in element.text_content().replace(' & ', ',').split(','):
                    entry.artists.append(Artist(artist.strip()))

            if cls == 'ichart_mv' and len(element):
                entry.video = 'https://youtu.be/' + element[0].get('href').split(',')[1][1:-2]

        for entry in self:
            if not entry.video:
                try:
                    artists = '{0} - {1}'.format(str(entry.artists), entry.title)
                    entry.video = youtube.Video(artists).url
                except youtube.YouTubeError:
                    pass

class MelonChart(Chart):
    @property
    def name(self):
        return 'Melon'

    @property
    def supported_chart_types(self):
        return (ChartType.Realtime, ChartType.Week)

    @property
    def _default_chart_type(self):
        return ChartType.Realtime

    def _url_from_chart_type(self):
        urls = { ChartType.Realtime : 'http://www.melon.com/chart/index.htm',
                 ChartType.Week     : 'http://www.melon.com/chart/week/index.htm' }

        return urls[self.chart_type]

    def _fetch_chart(self):
        req = urllib.request.Request(self.url)
        page = urllib.request.urlopen(req, data=None, timeout=15)

        root = lxml.html.parse(page)

        rank = 1
        entry = None

        for element in root.iter(tag=lxml.etree.Element):
            cls = element.get('class')

            if cls is None:
                continue

            if cls == 'wrap_rank':
                entry = ChartEntry()

                entry.rank = rank

                if rank > self.limit:
                    break
                else:
                    self.append(entry)
                    rank += 1

                entry.change = element[0].get('class').replace('icon_', '').replace('static', 'none').replace('rank_', '')

                if entry.change is not 'new' and len(element) >= 2:
                    entry.change_diff = element[1].text_content().strip()

            if cls == 'wrap_song_info' and entry is not None:
                next = False
                for a in element.iter(tag='a'):
                    if not next:
                        entry.title = ftfy.fix_encoding(a.text_content().strip())
                        next = True
                    else:
                        for artist in a.text_content().split('|')[0].replace(' & ', ',').split(','):
                            entry.artists.append(Artist(artist.strip()))

                        break

class GaonChart(Chart):
    @property
    def name(self):
        return 'Gaon'

    @property
    def supported_chart_types(self):
        return (ChartType.Week, ChartType.AlbumWeek)

    @property
    def _default_chart_type(self):
        return ChartType.Week

    def _url_from_chart_type(self):
        urls = { ChartType.Week      : 'http://gaonchart.co.kr/main/section/chart/online.gaon?serviceGbn=ALL&termGbn=week&hitYear=2015&targetTime=&nationGbn=K',
                 ChartType.AlbumWeek : 'http://gaonchart.co.kr/main/section/chart/album.gaon?termGbn=week&hitYear=2015&nationGbn=T' }

        return urls[self.chart_type]

    def _fetch_chart(self):
        req = urllib.request.Request(self.url)
        page = urllib.request.urlopen(req, data=None, timeout=15)

        root = lxml.html.parse(page)

        rank = 1
        entry = None

        for element in root.iter(tag=lxml.etree.Element):
            cls = element.get('class')

            if cls is None:
                continue

            if cls == 'ranking':
                entry = ChartEntry()

                entry.rank = element.text_content().strip()

                if rank > self.limit:
                    break
                else:
                    self.append(entry)
                    rank += 1

            if cls == 'change':
                change = element[0].get('class')
                change = change if change else 'none'
                entry.change = change

                change_diff = element.text_content().strip()

                if (change == 'up' or change == 'down') and change_diff != 'HOT':
                    entry.change_diff = change_diff

            if cls == 'subject':
                entry.title = ftfy.fix_encoding(element[0].text_content().strip())

                for artist in element[1].text_content().split('|')[0].replace(' & ', ',').split(','):
                    entry.artists.append(Artist(artist.strip()))

class RedditChartsTable:
    def __init__(self, charts, columns=None, limit=20):
        self._charts = charts
        self._columns = columns if columns is not None else len(charts)
        self.limit = limit
        self._header = ''

    def _make_link(self, url, title):
        title = title.replace('`', '\'')

        if url:
            return '[{0}]({1})'.format(title, url)
        else:
            return title

    def _make_change(self, change, diff):
        if not diff or int(diff) == 0:
            return '–'

        if change == 'new':
            return '^NEW'

        pretty = dict()
        pretty['up'] = '↑'
        pretty['down'] = '↓'

        return '^{0}{1}'.format(pretty[change], diff)

    def __str__(self):
        table = list()

        if not self._header:
            columns = ['*{0} Top {1}*'.format(chart.name, self.limit) for chart in self._charts[0:self._columns]]
            columns.insert(0, '')
            self._header = ' | '.join(columns)

        table.append(self._header)

        columns = range(self._columns + 1)

        cont = ['---',] * len(columns)
        cont[0] = '---:'
        table.append('|'.join(cont))

        for i in range(self.limit):
            entries = [chart[i] for chart in self._charts[0:self._columns]]

            table.append('{0}. | {1}'.format(i + 1, ' | '.join('{0} {1}'.format(self._make_link(entry.video,
                '{0} - {1}'.format(str(entry.artists), entry.title)),
                self._make_change(entry.change, entry.change_diff)) for entry in entries)))

        return '\n'.join(table)
